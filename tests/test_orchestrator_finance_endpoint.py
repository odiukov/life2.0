"""POST /finance/upload — FastAPI TestClient end-to-end.

Uses a temporary TestClient over orchestrator.app.main without starting
the full lifespan (no graph, no checkpointer) — the endpoint itself only
touches DB helpers + parser + ingest.
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.asyncio


def _has_db() -> bool:
    return bool(os.environ.get("POSTGRES_DSN"))


FIXTURE = Path(__file__).parent / "fixtures" / "payoneer_sample.csv"


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
        await conn.execute("DELETE FROM finance_transactions WHERE txn_id LIKE 'TXN%'")
        await conn.execute("DELETE FROM finance_category_cache WHERE 1=1")
    finally:
        await conn.close()
    yield
    conn = await asyncpg.connect(os.environ["POSTGRES_DSN"])
    try:
        await conn.execute("DELETE FROM finance_transactions WHERE txn_id LIKE 'TXN%'")
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

    with patch(
        "orchestrator.app.finance_ingest.categorize_new",
        new=AsyncMock(return_value=None),
    ):
        client = TestClient(main.app)
        files = {"csv": ("payoneer.csv", FIXTURE.read_bytes(), "text/csv")}
        resp = client.post("/finance/upload", files=files)

    assert resp.status_code == 200
    data = resp.json()
    assert data["inserted"] == 6
    assert data["skipped"] >= 0
    assert isinstance(data["summary"], str)
    assert "новых" in data["summary"]


async def test_upload_rejects_bad_header():
    if not _has_db():
        pytest.skip("POSTGRES_DSN not set")
    from orchestrator.app import main

    bad = b"NotPayoneer,AtAll\n1,2\n"
    with patch(
        "orchestrator.app.finance_ingest.categorize_new",
        new=AsyncMock(return_value=None),
    ):
        client = TestClient(main.app)
        resp = client.post(
            "/finance/upload",
            files={"csv": ("junk.csv", bad, "text/csv")},
        )
    assert resp.status_code == 422
    assert "header" in resp.text.lower()


async def test_upload_rejects_non_csv_content_type():
    if not _has_db():
        pytest.skip("POSTGRES_DSN not set")
    from orchestrator.app import main

    client = TestClient(main.app)
    resp = client.post(
        "/finance/upload",
        files={"csv": ("doc.pdf", b"%PDF-1.4\n", "application/pdf")},
    )
    assert resp.status_code == 415
