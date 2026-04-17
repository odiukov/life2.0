import pytest
from unittest.mock import AsyncMock, patch


def test_parse_habit_command_name_only():
    from telegram_bot.app.main import parse_habit_args
    parsed = parse_habit_args(["meditation"])
    assert parsed == {"name": "meditation"}


def test_parse_habit_command_with_value_and_unit():
    from telegram_bot.app.main import parse_habit_args
    parsed = parse_habit_args(["meditation", "15min"])
    assert parsed == {"name": "meditation", "value": 15.0, "unit": "min"}


def test_parse_habit_command_with_space_separated_value():
    from telegram_bot.app.main import parse_habit_args
    parsed = parse_habit_args(["meditation", "15", "min", "morning session"])
    assert parsed["name"] == "meditation"
    assert parsed["value"] == 15.0
    assert parsed["unit"] == "min"
    assert parsed["note"] == "morning session"


def test_parse_habit_command_decimal():
    from telegram_bot.app.main import parse_habit_args
    parsed = parse_habit_args(["run", "5.5km"])
    assert parsed == {"name": "run", "value": 5.5, "unit": "km"}


def test_parse_habit_new_keyword_reserved():
    from telegram_bot.app.main import parse_habit_args
    parsed = parse_habit_args(["new", "meditation", "20min", "daily"])
    assert parsed == {"action": "new", "text": "meditation 20min daily"}


def test_parse_habit_stop_keyword_reserved():
    from telegram_bot.app.main import parse_habit_args
    parsed = parse_habit_args(["stop", "meditation"])
    assert parsed == {"action": "stop", "name": "meditation"}


@pytest.mark.asyncio
async def test_cmd_habit_calls_direct_a2a_on_new():
    from telegram_bot.app.main import cmd_habit

    class _Msg:
        async def reply_text(self, t):
            self.sent = t
    class _Update:
        message = _Msg()
    class _Ctx:
        args = ["new", "meditation", "20min", "daily"]

    upd = _Update()
    with patch("telegram_bot.app.main.habits_a2a_call",
               new=AsyncMock(return_value="tracking 'meditation'")) as m:
        await cmd_habit(upd, _Ctx())
    m.assert_called_once()
    assert m.call_args.kwargs["skill"] == "define_habit" or m.call_args.args[0] == "define_habit"


@pytest.mark.asyncio
async def test_on_habit_callback_logs_via_a2a(monkeypatch):
    from telegram_bot.app import habits_ui

    class _Query:
        data = "h:abc-123"
        async def answer(self): self.answered = True
        async def edit_message_reply_markup(self, reply_markup): self.edited = reply_markup
        async def edit_message_text(self, t): self.edited_text = t
    class _Update:
        callback_query = _Query()
    class _Ctx: pass

    called = {}

    async def fake_a2a(skill, message, params):
        called["skill"] = skill
        called["params"] = params
        return "checked"

    async def fake_build():
        return None, "empty"

    monkeypatch.setattr(habits_ui, "habits_a2a_call", fake_a2a)
    monkeypatch.setattr(habits_ui, "build_habits_keyboard", fake_build)

    await habits_ui.on_habit_callback(_Update(), _Ctx())
    assert called["skill"] == "log_habit_check"
    assert called["params"]["habit_id"] == "abc-123"
