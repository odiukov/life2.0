"""POST /finance/upload — FastAPI TestClient end-to-end (PDF variant).

Uses a temporary TestClient over orchestrator.app.main without starting
the full lifespan (no graph, no checkpointer) — the endpoint itself only
touches DB helpers + PDF parser + ingest.
"""
from __future__ import annotations

import os
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.asyncio


_PAGE = """\
Account Statement
Jane Doe
Account
EUR balance
Some Street 1
Period
03/01/2026 - 03/31/2026
Somewhere
Issuing Date
04/01/2026
380000000000
Date
Description
Amount
Currency
Running Balance
31 Mar, 2026
Card charge (MERCHANT A)
-44.00
EUR
445.89
30 Mar, 2026
Card charge (MERCHANT B)
-6.95
EUR
489.89
28 Mar, 2026
Transfer between balances - to EUR from USD
572.44
EUR
764.29
© 2005-2026 Payoneer, All Rights Reserved   |   www.payoneer.com
"""


def _has_db() -> bool:
    return bool(os.environ.get("POSTGRES_DSN"))


def _fake_pdf_bytes() -> bytes:
    """Build a minimal single-page PDF with the Payoneer-shaped text."""
    import pymupdf
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((50, 50), _PAGE, fontsize=8, fontname="helv")
    out = doc.tobytes()
    doc.close()
    return out


@pytest.fixture(autouse=True)
async def _cleanup():
    if not _has_db():
        yield
        return
    import shared.db as _sdb
    if _sdb._pool is not None:
        await _sdb._pool.close()
        _sdb._pool = None
    import asyncpg
    conn = await asyncpg.connect(os.environ["POSTGRES_DSN"])
    try:
        await conn.execute("DELETE FROM finance_transactions WHERE txn_id LIKE 'pyn-pdf-%'")
        await conn.execute("DELETE FROM finance_category_cache WHERE 1=1")
    finally:
        await conn.close()
    yield
    conn = await asyncpg.connect(os.environ["POSTGRES_DSN"])
    try:
        await conn.execute("DELETE FROM finance_transactions WHERE txn_id LIKE 'pyn-pdf-%'")
        await conn.execute("DELETE FROM finance_category_cache WHERE 1=1")
    finally:
        await conn.close()
    if _sdb._pool is not None:
        await _sdb._pool.close()
        _sdb._pool = None


async def test_upload_happy_path():
    if not _has_db():
        pytest.skip("POSTGRES_DSN not set")
    from orchestrator.app import main

    pdf = _fake_pdf_bytes()
    with patch(
        "orchestrator.app.finance_ingest.categorize_new",
        new=AsyncMock(return_value=None),
    ):
        client = TestClient(main.app)
        files = {"csv": ("payoneer.pdf", pdf, "application/pdf")}
        resp = client.post("/finance/upload", files=files)

    assert resp.status_code == 200
    data = resp.json()
    assert data["inserted"] == 3
    assert data["skipped"] == 0
    assert isinstance(data["summary"], str)
    assert "новых" in data["summary"]


async def test_upload_rejects_non_payoneer_pdf():
    if not _has_db():
        pytest.skip("POSTGRES_DSN not set")
    from orchestrator.app import main

    # A valid PDF byte stream, but without Payoneer markers.
    import pymupdf
    doc = pymupdf.open()
    p = doc.new_page(width=595, height=842)
    p.insert_text((50, 50), "Random unrelated doc", fontsize=10)
    bad = doc.tobytes()
    doc.close()

    with patch(
        "orchestrator.app.finance_ingest.categorize_new",
        new=AsyncMock(return_value=None),
    ):
        client = TestClient(main.app)
        resp = client.post(
            "/finance/upload",
            files={"csv": ("junk.pdf", bad, "application/pdf")},
        )
    assert resp.status_code == 422
    assert "payoneer" in resp.text.lower() or "account statement" in resp.text.lower()


async def test_upload_rejects_non_pdf_content_type():
    if not _has_db():
        pytest.skip("POSTGRES_DSN not set")
    from orchestrator.app import main

    client = TestClient(main.app)
    resp = client.post(
        "/finance/upload",
        files={"csv": ("statement.csv", b"Date,Amount\n2026-01-01,1.00\n", "text/csv")},
    )
    assert resp.status_code == 415
