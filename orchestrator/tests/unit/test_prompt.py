from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from orchestrator.prompts import system_prompt

NOW = datetime(2026, 10, 14, 6, 30, tzinfo=UTC)


def test_without_lead(snapshot) -> None:  # type: ignore[no-untyped-def]
    snapshot(
        "system_prompt_plain", system_prompt(now=NOW, zone=ZoneInfo("Europe/Kyiv"), lead_agent=None)
    )


def test_with_lead(snapshot) -> None:  # type: ignore[no-untyped-def]
    snapshot(
        "system_prompt_lead_kitchen",
        system_prompt(now=NOW, zone=ZoneInfo("Europe/Kyiv"), lead_agent="kitchen"),
    )


def test_guards_that_must_not_be_edited_away() -> None:
    text = system_prompt(now=NOW, zone=ZoneInfo("Europe/Kyiv"), lead_agent="sleep")
    assert "Current date: 2026-10-14 (Europe/Kyiv)" in text
    assert "never say a change is done" in text.lower()
    assert "log_habit_check" in text
    assert "/habit" in text
    assert "ask_recovery_agent first" in text
    assert "This task is led by sleep" in text


def test_runtime_date_uses_the_users_timezone() -> None:
    now = datetime(2026, 5, 5, 21, 30, tzinfo=UTC)
    text = system_prompt(now=now, zone=ZoneInfo("Europe/Lisbon"), lead_agent=None)
    assert "Current date: 2026-05-05 (Europe/Lisbon)" in text
