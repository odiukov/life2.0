"""One fixed week of one user's data and the outputs the legacy dashboard produced from it.

Task 1 of sub-project 3c recorded `golden/*.json` by running the legacy orchestrator on this data
at FROZEN_NOW. The agents' dashboard skills and the gateway must reproduce them exactly. Change the
seed only together with re-recording (`tests/golden_master`, `--update-snapshots`) while the legacy
code still exists.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.ports.health_logs import HealthLogRow
from shared.schema.tables import finance_transactions, habits, health_logs, medications, users

FROZEN_NOW = datetime(2026, 10, 14, 6, 30, tzinfo=UTC)  # 09:30 in Kyiv (UTC+3 in October)
USER_ID = UUID("00000000-0000-4000-8000-00000000c3c0")
TIMEZONE = "Europe/Kyiv"
PROFILE: dict[str, object] = {
    "height_cm": 180,
    "age": 35,
    "sex": "male",
    "activity_level": "moderate",
}
READ_HABIT = UUID("00000000-0000-4000-8000-0000000000a1")
WATER_HABIT = UUID("00000000-0000-4000-8000-0000000000a2")
VITAMIN_D = UUID("00000000-0000-4000-8000-0000000000b1")
MAGNESIUM = UUID("00000000-0000-4000-8000-0000000000b2")
GOLDEN_DIR = Path(__file__).parent / "golden"

# The order of agents[] in the legacy /dashboard/summary (main.py builds them in this order).
TILE_ORDER = (
    "sleep",
    "recovery",
    "workout",
    "nutrition",
    "mood",
    "habits",
    "medication",
    "calendar",
    "body",
)
# Which agent's card supplies each ring and each featured block of the summary.
RING_OWNERS = {
    "readyPct": "recovery",
    "hrvPct": "sleep",
    "hrvMs": "sleep",
    "moodPct": "mood",
    "stepsPct": "workout",
}
FEATURED_OWNERS = {
    "featured_sleep": "sleep",
    "featured_workout": "workout",
    "featured_nutrition": "nutrition",
    "featured_body": "body",
}
DETAIL_AGENTS = (
    "sleep",
    "workout",
    "nutrition",
    "mood",
    "habits",
    "recovery",
    "medication",
    "finance",
    "calendar",
)


def _at(day: int, hour: int, minute: int = 0, *, month: int = 10) -> datetime:
    return datetime(2026, month, day, hour, minute, tzinfo=UTC)


def _row(agent: str, type_: str, source: str, when: datetime, data: dict[str, Any]) -> HealthLogRow:
    return HealthLogRow(type=type_, recorded_at=when, data=data, source=source, agent=agent)


def health_log_rows() -> list[HealthLogRow]:
    rows: list[HealthLogRow] = []
    for d in range(2, 14):  # nights ending 3..14 Oct; recorded 00:30 Kyiv
        rows.append(
            _row(
                "sleep",
                "sleep_session",
                "garmin",
                _at(d, 21, 30),
                {
                    "duration_seconds": 25200 + (d % 3) * 1800,
                    "deep_sleep_seconds": 5400 + (d % 2) * 600,
                    "rem_sleep_seconds": 5000,
                    "light_sleep_seconds": 13000,
                    "awake_seconds": 1200,
                    "hrv_weekly_avg": 50 + d,
                    "avg_hr": 52 + d % 4,
                    "score": 70 + d,
                },
            )
        )
    for d in range(6, 14):
        rows.append(
            _row(
                "sleep",
                "hrv_status",
                "garmin",
                _at(d, 5),
                {
                    "hrv_rmssd": 48 + d,
                    "status": "BALANCED",
                    "baseline_low": 45,
                    "baseline_high": 65,
                },
            )
        )
    for d in range(5, 14):
        rows.append(
            _row(
                "sleep",
                "daily_stats",
                "garmin",
                _at(d, 20),
                {
                    "steps": 8000 + d * 100,
                    "calories_active": 500,
                    "stress_avg": 30 + d % 5,
                    "body_battery_min": 20 + d % 3,
                    "body_battery_max": 80 + d % 4,
                    "resting_hr": 50 + d % 3,
                },
            )
        )
    for when, name, kind, meters, kcal, seconds, hr in (
        (_at(13, 15), "Evening run", "running", 8000, 600, 2700, 150),
        (_at(11, 7), "Strength", "strength_training", 0, 300, 3000, 120),
        (_at(9, 16, 30), "Easy ride", "cycling", 20000, 500, 3600, 135),
    ):
        rows.append(
            _row(
                "workout",
                "activity",
                "garmin",
                when,
                {
                    "activity_type": kind,
                    "name": name,
                    "duration_seconds": seconds,
                    "distance_meters": meters,
                    "calories": kcal,
                    "avg_hr": hr,
                },
            )
        )
    meals = (
        ("breakfast", 5, 500, 30, 60, 15, "Oats"),
        ("lunch", 9, 700, 40, 80, 25, "Chicken bowl"),
        ("dinner", 16, 800, 45, 70, 30, "Salmon"),
    )
    for d in range(8, 14):
        for slot, hour, kcal, protein, carbs, fat, item in meals:
            rows.append(
                _row(
                    "nutrition",
                    "meal",
                    "yazio",
                    _at(d, hour),
                    {
                        "meal_type": slot,
                        "items": [{"name": item}],
                        "totals": {
                            "kcal": kcal,
                            "protein_g": protein,
                            "carbs_g": carbs,
                            "fat_g": fat,
                        },
                    },
                )
            )
    rows.append(
        _row(
            "nutrition",
            "meal",
            "yazio",
            _at(14, 5),
            {
                "meal_type": "breakfast",
                "items": [{"name": "Yogurt"}],
                "totals": {"kcal": 450, "protein_g": 25, "carbs_g": 55, "fat_g": 14},
            },
        )
    )
    for d in range(8, 14):
        rows.append(
            _row(
                "mood",
                "mood",
                "chat",
                _at(d, 7),
                {
                    "mood_score": 5 + d % 4,
                    "stress": 4,
                    "energy": 6,
                    "valence": "positive" if d % 2 else "neutral",
                    "tags": ["work"],
                },
            )
        )
    rows.append(
        _row(
            "mood",
            "mood",
            "chat",
            _at(13, 17),
            {
                "mood_score": 8,
                "stress": 3,
                "energy": 7,
                "valence": "positive",
                "tags": ["family", "walk"],
            },
        )
    )
    for d in (9, 10, 11, 12, 13):
        rows.append(
            _row(
                "habits",
                "habit",
                "chat",
                _at(d, 18),
                {"habit_id": str(READ_HABIT), "completed": True},
            )
        )
    for d, value in ((10, 5), (11, 8), (12, 8), (13, 8)):
        rows.append(
            _row(
                "habits",
                "habit",
                "chat",
                _at(d, 12),
                {"habit_id": str(WATER_HABIT), "value": value},
            )
        )
    for d in range(8, 14):
        rows.append(
            _row("medication", "medication_taken", "chat", _at(d, 6), {"name": "Vitamin D"})
        )
    for d in (8, 9, 10):
        rows.append(
            _row("medication", "medication_taken", "chat", _at(d, 18), {"name": "Magnesium"})
        )
    for when, weight, body_fat, muscle, lean in (
        (_at(12, 6), 81.4, 18.2, 63.1, 66.6),
        (_at(13, 6, month=9), 82.6, 19.0, 62.7, 66.9),
        (_at(1, 6, month=9), 83.0, 19.4, 62.5, 66.9),
    ):
        rows.append(
            _row(
                "body",
                "body_composition",
                "vihealth",
                when,
                {
                    "weight_kg": weight,
                    "body_fat_pct": body_fat,
                    "muscle_kg": muscle,
                    "lean_mass_kg": lean,
                    "skeletal_muscle_kg": 37.0,
                    "bmr_kcal": 1780,
                    "visceral_fat_grade": 8,
                    "body_age": 33,
                    "body_score": 84,
                    "bmi": 25.1,
                },
            )
        )
    return rows


def habit_rows() -> list[dict[str, object]]:
    created = _at(1, 8, month=9)
    return [
        {
            "id": READ_HABIT,
            "user_id": USER_ID,
            "name": "Read",
            "kind": "boolean",
            "cadence_type": "daily",
            "created_at": created,
        },
        {
            "id": WATER_HABIT,
            "user_id": USER_ID,
            "name": "Water",
            "kind": "quantitative",
            "cadence_type": "daily",
            "target_value": Decimal(8),
            "unit": "glasses",
            "created_at": _at(1, 9, month=9),
        },
    ]


def medication_rows() -> list[dict[str, object]]:
    return [
        {
            "id": VITAMIN_D,
            "user_id": USER_ID,
            "name": "Vitamin D",
            "dose": "2000 IU",
            "schedule": "daily",
            "created_at": _at(1, 8, month=9),
        },
        {
            "id": MAGNESIUM,
            "user_id": USER_ID,
            "name": "Magnesium",
            "dose": "400 mg",
            "schedule": "evening",
            "created_at": _at(1, 9, month=9),
        },
    ]


def transaction_rows() -> list[dict[str, object]]:
    items = (
        ("t-0920", _at(20, 10, month=9), "OUT", "300.00", "Lisbon flight", "travel"),
        ("t-1001", _at(1, 10), "IN", "4000.00", "Client payment ACME", "income"),
        ("t-1003", _at(3, 10), "OUT", "1200.00", "Rent October", "housing"),
        ("t-1008", _at(8, 10), "OUT", "45.50", "Pingo Doce", "food"),
        ("t-1010", _at(10, 10), "OUT", "15.99", "Netflix", "subscriptions"),
        ("t-1011", _at(11, 10), "OUT", "60.00", "Uber", "transport"),
        ("t-1012", _at(12, 10), "OUT", "32.40", "Continente", "food"),
        ("t-1013", _at(13, 10), "OUT", "120.00", "Pharmacy", "health"),
    )
    return [
        {
            "user_id": USER_ID,
            "txn_id": txn,
            "ts": when,
            "direction": direction,
            "amount": Decimal(amount),
            "currency": "USD",
            "description": description,
            "category": category,
            "source": "payoneer_pdf",
        }
        for txn, when, direction, amount, description, category in items
    ]


GOOGLE_EVENTS: list[dict[str, object]] = [
    {
        "id": "ev-standup",
        "etag": '"3001"',
        "summary": "Standup",
        "start": {"dateTime": "2026-10-14T10:00:00+03:00"},
        "end": {"dateTime": "2026-10-14T10:30:00+03:00"},
    },
    {
        "id": "ev-review",
        "etag": '"3002"',
        "summary": "Design review",
        "start": {"dateTime": "2026-10-14T14:00:00+03:00"},
        "end": {"dateTime": "2026-10-14T15:30:00+03:00"},
    },
    {
        "id": "ev-gym",
        "etag": '"3003"',
        "summary": "Gym",
        "start": {"dateTime": "2026-10-14T19:00:00+03:00"},
        "end": {"dateTime": "2026-10-14T20:00:00+03:00"},
    },
    {
        "id": "ev-birthday",
        "etag": '"3004"',
        "summary": "Mom's birthday",
        "start": {"date": "2026-10-14"},
        "end": {"date": "2026-10-15"},
    },
]


def google_events_for(day: date) -> list[dict[str, object]]:
    return [dict(e) for e in GOOGLE_EVENTS] if day == date(2026, 10, 14) else []


async def seed_postgres(conn: AsyncConnection) -> None:
    """Insert the week as a superuser (bypasses RLS). The tables must be empty for USER_ID."""
    await conn.execute(
        insert(users).values(
            id=USER_ID, name="Golden", timezone=TIMEZONE, preferences={"body_profile": PROFILE}
        )
    )
    await conn.execute(
        insert(health_logs),
        [
            {
                "user_id": USER_ID,
                "agent": r.agent,
                "type": r.type,
                "source": r.source,
                "recorded_at": r.recorded_at,
                "data": dict(r.data),
            }
            for r in health_log_rows()
        ],
    )
    for habit in habit_rows():
        await conn.execute(insert(habits).values(**habit))
    await conn.execute(insert(medications), medication_rows())
    await conn.execute(insert(finance_transactions), transaction_rows())


def golden(name: str) -> Any:
    return json.loads((GOLDEN_DIR / f"{name}.json").read_text("utf-8"))


def expected_card(agent: str) -> dict[str, object]:
    summary = golden("dashboard_summary")
    tile = next((t for t in summary["agents"] if t["agent"] == agent), None)
    featured_key = next((k for k, owner in FEATURED_OWNERS.items() if owner == agent), None)
    rings = {k: v for k, v in summary["rings"].items() if RING_OWNERS[k] == agent}
    return {
        "tile": tile,
        "featured": summary[featured_key] if featured_key else None,
        "rings": rings,
    }


def expected_detail(agent: str) -> dict[str, object]:
    return dict(golden(f"detail_{agent}"))


from shared.testing.fakes import InMemoryHealthLogs, InMemoryUserSettings


def memory_logs() -> InMemoryHealthLogs:
    logs = InMemoryHealthLogs()
    for row in health_log_rows():
        logs.seed(USER_ID, row)
    return logs


def memory_settings() -> InMemoryUserSettings:
    settings = InMemoryUserSettings()
    settings.seed(USER_ID, timezone=TIMEZONE)
    return settings


def as_json(value: Any) -> Any:
    """What the gateway would send: the same normalization the goldens went through."""
    return json.loads(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str))
