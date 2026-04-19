import pytest

pytestmark = pytest.mark.asyncio

from telegram_bot.app.main import parse_med_args


def test_parse_empty():
    assert parse_med_args([]) == {}


def test_parse_name_only():
    assert parse_med_args(["magnesium"]) == {"name": "magnesium"}


def test_parse_new_freeform():
    out = parse_med_args(["new", "магний", "200мг", "каждый", "вечер"])
    assert out == {"action": "new", "text": "магний 200мг каждый вечер"}


def test_parse_stop():
    assert parse_med_args(["stop", "magnesium"]) == {"action": "stop", "name": "magnesium"}


def test_parse_list():
    assert parse_med_args(["list"]) == {"action": "list"}


def test_parse_name_with_dose_override():
    out = parse_med_args(["magnesium", "300mg"])
    assert out == {"name": "magnesium", "dose_override": "300mg"}


def test_parse_name_with_note():
    out = parse_med_args(["magnesium", "300mg", "late", "tonight"])
    assert out == {"name": "magnesium", "dose_override": "300mg", "note": "late tonight"}
