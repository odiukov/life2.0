from typing import Any

import pytest
from mood.application.dashboard import card, detail
from shared.a2a.request import SkillRequest
from shared.dashboard import DashboardSkill
from shared.ports.health_logs import HealthLogRepository
from shared.ports.users import UserSettingsRepository
from shared.skill_ids import Dashboard
from shared.testing import dashboard_golden as g
from shared.testing.fakes import FixedClock, InMemoryUnitOfWorkFactory

AGENT = "mood"


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


async def test_mood_ring_is_part_of_the_card() -> None:
    skill = DashboardSkill(uow=uow(), clock=FixedClock(g.FROZEN_NOW), build=card, name="card")
    data = (
        await skill(SkillRequest("t", "c", "", g.USER_ID, Dashboard.CARD, None, False), ())
    ).data
    assert set(data["rings"]) == {"moodPct"}
