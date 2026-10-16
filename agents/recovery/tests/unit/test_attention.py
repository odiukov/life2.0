from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import patch
from uuid import uuid4

from recovery.application import attention
from shared.a2a.request import SkillRequest
from shared.adapters.i18n import JsonTranslator
from shared.attention import AttentionSkill
from shared.ports.health_logs import HealthLogRepository, HealthLogRow
from shared.ports.users import UserSettingsRepository
from shared.skill_ids import Attention
from shared.testing.attention_contract import assert_attention_contract
from shared.testing.fakes import (
    FixedClock,
    InMemoryHealthLogs,
    InMemoryUnitOfWorkFactory,
    InMemoryUserSettings,
)

TR = JsonTranslator.from_dir(Path(__file__).resolve().parents[4] / "packages" / "i18n" / "locales")
NOW = datetime(2026, 10, 16, 9, 0, tzinfo=UTC)
USER = uuid4()


async def run(*rows: HealthLogRow) -> list[dict]:  # type: ignore[type-arg]
    logs, settings = InMemoryHealthLogs(), InMemoryUserSettings()
    settings.seed(USER, timezone="Europe/Kyiv")
    for row in rows:
        logs.seed(USER, row)
    skill = AttentionSkill(
        uow=InMemoryUnitOfWorkFactory(
            {HealthLogRepository: logs, UserSettingsRepository: settings}
        ),
        clock=FixedClock(NOW),
        translator=TR,
        default_locale="en",
        collect=attention.collect,
    )
    result = await skill(SkillRequest("t", "c", "", USER, Attention.ITEMS, None, False, {}), ())
    assert_attention_contract(result.data)
    return result.data["items"]  # type: ignore[index, return-value]


async def run_shaped(bucket: str | None) -> list[dict]:  # type: ignore[type-arg]
    async def fake_shape(tx: Any, ctx: Any, target: Any) -> dict[str, Any] | None:
        return None if bucket is None else {"bucket": bucket, "top3": []}

    with patch.object(attention, "shape", fake_shape):
        return await run()


async def test_depleted_gives_an_easy_day_item() -> None:
    [item] = await run_shaped("depleted")
    assert (item["id"], item["level"], item["text"]) == (
        "recovery:depleted:2026-10-16",
        "normal",
        "Take it easy today",
    )


async def test_other_buckets_or_no_data_give_nothing() -> None:
    assert await run_shaped("recovered") == []
    assert await run_shaped(None) == []


def _metrics(days_ago: int, *, hrv: float, rhr: int, hours: float) -> list[HealthLogRow]:
    at = NOW.replace(hour=4) - timedelta(days=days_ago)
    return [
        HealthLogRow(
            "sleep_session",
            at,
            {"duration_seconds": int(hours * 3600), "awake_seconds": 600, "hrv_weekly_avg": hrv},
            "garmin",
            "sleep",
        ),
        HealthLogRow("daily_stats", at, {"resting_hr": rhr}, "garmin", "sleep"),
    ]


async def test_real_shape_reports_a_depleted_day() -> None:
    baseline = [row for d in range(1, 8) for row in _metrics(d, hrv=60, rhr=50, hours=8)]
    today = _metrics(0, hrv=40, rhr=65, hours=5)
    [item] = await run(*baseline, *today)
    assert item["id"] == "recovery:depleted:2026-10-16"


async def test_real_shape_stays_quiet_on_a_normal_day() -> None:
    rows = [row for d in range(0, 8) for row in _metrics(d, hrv=60, rhr=50, hours=8)]
    assert await run(*rows) == []
