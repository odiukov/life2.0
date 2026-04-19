"""Unit tests for the Telegram PDF dispatcher (Payoneer vs ViHealth).

Exercises `_looks_like_payoneer` and `handle_document` sniffing + routing
logic — no Telegram network, no orchestrator, no LLM. All downstream
calls (`upload_finance_pdf`, `build_sync_payload`, `sync_body_pdf`) are
mocked.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.asyncio


def _make_pdf(text: str) -> bytes:
    import pymupdf
    doc = pymupdf.open()
    p = doc.new_page(width=595, height=842)
    p.insert_text((50, 50), text, fontsize=10)
    out = doc.tobytes()
    doc.close()
    return out


def _make_image_only_pdf() -> bytes:
    """A valid PDF whose first page has NO text layer (mimics Lescale)."""
    import pymupdf
    doc = pymupdf.open()
    doc.new_page(width=595, height=842)  # blank page, no insert_text
    out = doc.tobytes()
    doc.close()
    return out


def test_looks_like_payoneer_detects_account_statement():
    from telegram_bot.app.main import _looks_like_payoneer
    pdf = _make_pdf("Account Statement\nPayoneer footer")
    assert _looks_like_payoneer(pdf) is True


def test_looks_like_payoneer_rejects_image_only_pdf():
    from telegram_bot.app.main import _looks_like_payoneer
    assert _looks_like_payoneer(_make_image_only_pdf()) is False


def test_looks_like_payoneer_rejects_random_pdf():
    from telegram_bot.app.main import _looks_like_payoneer
    pdf = _make_pdf("Random document with no banking markers")
    assert _looks_like_payoneer(pdf) is False


def test_looks_like_payoneer_rejects_non_pdf_bytes():
    from telegram_bot.app.main import _looks_like_payoneer
    assert _looks_like_payoneer(b"not a pdf at all") is False


async def _invoke_handle_document(pdf_bytes: bytes, filename: str = "x.pdf"):
    """Build a minimal Telegram Update + Context and run handle_document.
    Returns the mock of `reply_text.edit_text` so tests can inspect the reply.
    """
    from telegram_bot.app import main as bot_main

    thinking = MagicMock()
    thinking.edit_text = AsyncMock()

    reply = AsyncMock(return_value=thinking)
    tg_file = MagicMock()
    tg_file.download_as_bytearray = AsyncMock(return_value=bytearray(pdf_bytes))
    doc = MagicMock(file_name=filename)
    doc.get_file = AsyncMock(return_value=tg_file)

    update = MagicMock()
    update.message.document = doc
    update.message.reply_text = reply

    await bot_main.handle_document(update, MagicMock())
    return thinking.edit_text


async def test_handle_document_routes_payoneer_pdf_to_finance():
    pdf = _make_pdf("Account Statement\nPeriod ...\nPayoneer")

    with patch(
        "telegram_bot.app.main.upload_finance_pdf",
        new=AsyncMock(return_value={"summary": "✓ done", "inserted": 1, "skipped": 0}),
    ) as m_upload, patch(
        "telegram_bot.app.main.build_sync_payload"
    ) as m_build, patch(
        "telegram_bot.app.main.sync_body_pdf"
    ) as m_sync_body:
        edit = await _invoke_handle_document(pdf)

    m_upload.assert_awaited_once()
    m_build.assert_not_called()
    m_sync_body.assert_not_called()
    edit.assert_awaited_with("✓ done")


async def test_handle_document_routes_non_payoneer_pdf_to_vihealth():
    pdf = _make_image_only_pdf()

    with patch(
        "telegram_bot.app.main.upload_finance_pdf"
    ) as m_upload, patch(
        "telegram_bot.app.main.build_sync_payload",
        return_value={"data": []},
    ) as m_build, patch(
        "telegram_bot.app.main.sync_body_pdf",
        new=AsyncMock(return_value="Saved 1 body composition measurement(s)"),
    ) as m_sync:
        edit = await _invoke_handle_document(pdf)

    m_upload.assert_not_called()
    m_build.assert_called_once()
    m_sync.assert_awaited_once()
    edit.assert_awaited_with("Saved 1 body composition measurement(s)")


async def test_handle_document_surfaces_finance_error():
    pdf = _make_pdf("Account Statement")

    with patch(
        "telegram_bot.app.main.upload_finance_pdf",
        new=AsyncMock(return_value={"error": "Upload failed (422): bad pdf"}),
    ):
        edit = await _invoke_handle_document(pdf)

    edit.assert_awaited_with("Upload failed (422): bad pdf")
