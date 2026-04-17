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
