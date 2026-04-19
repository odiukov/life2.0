from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.asyncio


async def test_cmd_dashboard_calls_orchestrator_dashboard():
    from telegram_bot.app import main as bot_main

    update = MagicMock()
    update.effective_chat.id = 42
    update.message.reply_text = AsyncMock(return_value=MagicMock(edit_text=AsyncMock()))

    context = MagicMock()

    async def fake_fetch():
        return "📊 Dashboard — 2026-04-18\n• Sleep: 7h 0m"

    bot_main.fetch_dashboard = fake_fetch
    await bot_main.cmd_dashboard(update, context)

    update.message.reply_text.assert_awaited()
