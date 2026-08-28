import pytest
from orchestrator.app.file_router import _classify_text


def test_classify_vihealth_body_fat_rate():
    text = "Body fat rate 26.5%\nBMI 27.5\nBody Mass Index"
    assert _classify_text(text) == "vihealth"


def test_classify_vihealth_lepulse():
    text = "LePulse Body Composition Report\nWeight 79.6 kg"
    assert _classify_text(text) == "vihealth"


def test_classify_payoneer():
    text = "Account Statement\nPayoneer Inc.\nPeriod: Mar 2026"
    assert _classify_text(text) == "payoneer"


def test_classify_unknown():
    text = "Hello World nothing relevant here at all"
    assert _classify_text(text) == "unknown"


from datetime import datetime, timezone
from orchestrator.app.file_router import _map_body_rows, _vihealth_summary


def test_map_body_rows_single_measurement():
    payload = {
        "data": [
            {"date": "2026-04-14 09:37:16 +0000", "qty": 79.6, "name": "Body Mass", "units": "kg"},
            {"date": "2026-04-14 09:37:16 +0000", "qty": 26.5, "name": "Body Fat Percentage", "units": "%"},
        ]
    }
    rows = _map_body_rows(payload)
    assert len(rows) == 1
    assert rows[0]["type"] == "body_composition"
    assert rows[0]["source"] == "vihealth"
    assert rows[0]["agent"] == "body"
    assert rows[0]["data"]["weight_kg"] == 79.6
    assert rows[0]["data"]["body_fat_pct"] == 26.5


def test_map_body_rows_groups_by_day():
    payload = {
        "data": [
            {"date": "2026-04-14 09:37:16 +0000", "qty": 79.6, "name": "Body Mass", "units": "kg"},
            {"date": "2026-04-15 08:00:00 +0000", "qty": 79.4, "name": "Body Mass", "units": "kg"},
        ]
    }
    rows = _map_body_rows(payload)
    assert len(rows) == 2


def test_vihealth_summary_single():
    rows = [{
        "recorded_at": datetime(2026, 4, 14, 9, 37, tzinfo=timezone.utc),
        "data": {"weight_kg": 79.6, "body_fat_pct": 26.5, "bmi": 27.5},
    }]
    summary = _vihealth_summary(rows, written=1, unchanged=0)
    assert "1 измерение" in summary
    assert "79.6" in summary
    assert "26.5%" in summary


def test_vihealth_summary_all_unchanged():
    rows = [
        {
            "recorded_at": datetime(2026, 4, 13, 8, 0, tzinfo=timezone.utc),
            "data": {"weight_kg": 80.0, "body_fat_pct": 27.0, "bmi": 28.0},
        },
        {
            "recorded_at": datetime(2026, 4, 14, 9, 37, tzinfo=timezone.utc),
            "data": {"weight_kg": 79.6, "body_fat_pct": 26.5, "bmi": 27.5},
        },
    ]
    summary = _vihealth_summary(rows, written=0, unchanged=2)
    assert "Данные уже в базе" in summary
    assert "пропущено: 2" in summary
    assert "79.6" in summary


def test_classify_payoneer_single_keyword_is_unknown():
    text = "Payoneer only"
    assert _classify_text(text) == "unknown"


@pytest.mark.asyncio
async def test_insert_body_rows_empty_list_returns_zero():
    from orchestrator.app.db import insert_body_rows
    written, unchanged = await insert_body_rows([], None)
    assert written == 0
    assert unchanged == 0
