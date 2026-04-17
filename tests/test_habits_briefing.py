import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo


_TZ = ZoneInfo("Europe/Kyiv")


def _log_row(habit_id, name, recorded_at, value=None, unit=None, completed=True):
    data = {
        "habit_id": habit_id, "name": name,
        "completed": completed, "raw_text": f"/habit {name}",
        "source_skill": "log_habit_check",
    }
    if value is not None: data["value"] = value
    if unit: data["unit"] = unit
    return {
        "type": "habit", "source": "telegram",
        "recorded_at": recorded_at, "data": data,
    }


@pytest.mark.asyncio
async def test_metrics_includes_habits_block_when_active_habits_exist():
    now = datetime.now(_TZ)
    yesterday = now - timedelta(days=1)

    active = [
        {"id": "h-1", "name": "meditation", "kind": "quantitative",
         "cadence_type": "daily", "cadence_days": None,
         "target_value": 20, "unit": "min",
         "created_at": now - timedelta(days=30)},
        {"id": "h-2", "name": "cold-shower", "kind": "boolean",
         "cadence_type": "daily", "cadence_days": None,
         "target_value": None, "unit": None,
         "created_at": now - timedelta(days=30)},
    ]
    logs = [
        _log_row("h-1", "meditation", yesterday.replace(hour=8), value=25, unit="min"),
        _log_row("h-2", "cold-shower", yesterday.replace(hour=7)),
    ]

    mock_pool = AsyncMock()
    mock_pool.fetchrow = AsyncMock(return_value=None)

    from orchestrator.app import db as odb
    with patch.object(odb, "get_pool", return_value=mock_pool), \
         patch.object(odb, "fetch_active_habits", new=AsyncMock(return_value=active)), \
         patch.object(odb, "fetch_habit_logs", new=AsyncMock(return_value=logs)):
        metrics = await odb.get_yesterday_metrics()

    habits_metrics = metrics.get("habits")
    assert habits_metrics is not None
    assert habits_metrics["expected_yesterday"] == 2
    assert habits_metrics["completed_yesterday"] == 2
    assert "meditation" in habits_metrics["today_names"]


@pytest.mark.asyncio
async def test_metrics_no_habits_block_when_registry_empty():
    mock_pool = AsyncMock()
    mock_pool.fetchrow = AsyncMock(return_value=None)

    from orchestrator.app import db as odb
    with patch.object(odb, "get_pool", return_value=mock_pool), \
         patch.object(odb, "fetch_active_habits", new=AsyncMock(return_value=[])), \
         patch.object(odb, "fetch_habit_logs", new=AsyncMock(return_value=[])):
        metrics = await odb.get_yesterday_metrics()
    assert metrics.get("habits") is None


def test_format_message_renders_two_lines_for_habits():
    from orchestrator.app.briefing import format_message
    metrics = {
        "date": "2026-04-16",
        "habits": {
            "expected_yesterday": 3,
            "completed_yesterday": 2,
            "missed_names": ["cold-shower"],
            "top_streaks": [{"name": "meditation", "streak": 12}],
            "today_items": [
                {"name": "meditation", "done": False},
                {"name": "cold-shower", "done": False},
            ],
            "today_names": ["meditation", "cold-shower"],
        },
    }
    out = format_message(metrics, insight=None)
    assert "Habits yesterday: ✅ 2/3" in out
    assert "meditation 12d" in out
    assert "missed: cold-shower" in out
    assert "Today:" in out
    assert "⬜ meditation" in out
    assert "⬜ cold-shower" in out


def test_format_message_omits_habits_when_absent():
    from orchestrator.app.briefing import format_message
    metrics = {"date": "2026-04-16"}
    out = format_message(metrics, insight=None)
    assert "Habits" not in out
    assert "Today:" not in out
