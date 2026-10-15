from datetime import UTC, datetime
from typing import Any

import pytest
from shared.a2a.request import SkillRequest
from shared.dashboard import DashboardSkill
from shared.ports.health_logs import HealthLogRepository, HealthLogRow
from shared.ports.users import UserSettingsRepository
from shared.skill_ids import Dashboard
from shared.testing import dashboard_golden as g
from shared.testing.fakes import FixedClock, InMemoryHealthLogs, InMemoryUnitOfWorkFactory
from workout.application.dashboard import card, detail

AGENT = "workout"


def uow(**extra: Any) -> InMemoryUnitOfWorkFactory:
    return InMemoryUnitOfWorkFactory(
        {HealthLogRepository: g.memory_logs(), UserSettingsRepository: g.memory_settings(), **extra}
    )


@pytest.mark.parametrize(
    ("skill_id", "build", "expected"),
    [(Dashboard.CARD, card, g.expected_card), (Dashboard.DETAIL, detail, g.expected_detail)],
)
async def test_matches_the_legacy_golden(skill_id, build, expected) -> None:
    skill = DashboardSkill(uow=uow(), clock=FixedClock(g.FROZEN_NOW), build=build, name=skill_id)
    result = await skill(SkillRequest("t", "c", "", g.USER_ID, skill_id, None, False), ())
    assert g.as_json(result.data) == expected(AGENT)


async def test_cards_use_the_users_zone() -> None:
    """At 03:00 UTC on 14 Oct it is still 13 Oct in New York: the 13 Oct run is today's workout."""
    settings = g.memory_settings()
    settings.seed(g.USER_ID, timezone="America/New_York")
    skill = DashboardSkill(
        uow=InMemoryUnitOfWorkFactory(
            {HealthLogRepository: g.memory_logs(), UserSettingsRepository: settings}
        ),
        clock=FixedClock(datetime(2026, 10, 14, 3, 0, tzinfo=UTC)),
        build=card,
        name="card",
    )
    data = (
        await skill(SkillRequest("t", "c", "", g.USER_ID, Dashboard.CARD, None, False), ())
    ).data
    assert data["featured"]["workoutDate"] == "today"
    assert data["featured"]["sessionName"] == "Evening run"


@pytest.mark.parametrize(("seconds", "minutes"), [(150, 2), (210, 4)])
async def test_half_minutes_round_to_even_in_card_and_detail(seconds: int, minutes: int) -> None:
    logs = InMemoryHealthLogs()
    logs.seed(
        g.USER_ID,
        HealthLogRow(
            type="activity",
            recorded_at=g.FROZEN_NOW,
            data={"duration_seconds": seconds},
            source="garmin",
            agent="workout",
        ),
    )
    factory = InMemoryUnitOfWorkFactory(
        {
            HealthLogRepository: logs,
            UserSettingsRepository: g.memory_settings(),
        }
    )
    results = []
    for skill_id, build in [(Dashboard.CARD, card), (Dashboard.DETAIL, detail)]:
        skill = DashboardSkill(
            uow=factory, clock=FixedClock(g.FROZEN_NOW), build=build, name=skill_id
        )
        results.append(
            (await skill(SkillRequest("t", "c", "", g.USER_ID, skill_id, None, False), ())).data
        )
    assert results[0]["featured"]["loadHistory"][-1] == minutes
    assert results[1]["history"][-1]["value"] == float(minutes)
    assert results[1]["history"][-1]["label"] == f"{minutes} min"
