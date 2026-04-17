import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_cmd_mood_prefixes_mood_keyword():
    from telegram_bot.app.main import cmd_mood

    update = MagicMock()
    update.message.reply_text = AsyncMock(return_value=MagicMock(edit_text=AsyncMock()))
    context = MagicMock()
    context.args = ["устал", "но", "продуктивный"]

    fake_ask = AsyncMock(return_value="recorded")
    with patch("telegram_bot.app.main.ask_orchestrator", new=fake_ask):
        await cmd_mood(update, context)

    assert fake_ask.call_args.args[0].startswith("mood ")
    assert "устал" in fake_ask.call_args.args[0]


@pytest.mark.asyncio
async def test_cmd_mood_empty_args_has_default():
    from telegram_bot.app.main import cmd_mood

    update = MagicMock()
    update.message.reply_text = AsyncMock(return_value=MagicMock(edit_text=AsyncMock()))
    context = MagicMock()
    context.args = []

    fake_ask = AsyncMock(return_value="ok")
    with patch("telegram_bot.app.main.ask_orchestrator", new=fake_ask):
        await cmd_mood(update, context)

    assert fake_ask.call_args.args[0].startswith("mood ")


@pytest.mark.asyncio
async def test_cmd_journal_prefixes_mood_keyword():
    from telegram_bot.app.main import cmd_journal

    update = MagicMock()
    update.message.reply_text = AsyncMock(return_value=MagicMock(edit_text=AsyncMock()))
    context = MagicMock()
    context.args = ["сегодня", "был", "трудный", "день"]

    fake_ask = AsyncMock(return_value="noted")
    with patch("telegram_bot.app.main.ask_orchestrator", new=fake_ask):
        await cmd_journal(update, context)

    # /journal is an alias of /mood — both prefix "mood "
    assert fake_ask.call_args.args[0].startswith("mood ")
