from typing import Any

import pytest
from nutrition.application.dashboard import card, detail
from shared.a2a.request import SkillRequest
from shared.dashboard import DashboardSkill
from shared.ports.health_logs import HealthLogRepository
from shared.ports.profile import BodyProfileRepository
from shared.ports.users import UserSettingsRepository
from shared.skill_ids import Dashboard
from shared.testing import dashboard_golden as g
from shared.testing.fakes import FixedClock, InMemoryBodyProfiles, InMemoryUnitOfWorkFactory

AGENT = "nutrition"


def uow(**extra: Any) -> InMemoryUnitOfWorkFactory:
    profiles = InMemoryBodyProfiles()
    profiles.rows[g.USER_ID] = dict(g.PROFILE)
    return InMemoryUnitOfWorkFactory(
        {
            HealthLogRepository: g.memory_logs(),
            UserSettingsRepository: g.memory_settings(),
            BodyProfileRepository: profiles,
            **extra,
        }
    )


@pytest.mark.parametrize(
    ("skill_id", "build", "expected"),
    [(Dashboard.CARD, card, g.expected_card), (Dashboard.DETAIL, detail, g.expected_detail)],
)
async def test_matches_the_legacy_golden(skill_id, build, expected) -> None:
    skill = DashboardSkill(uow=uow(), clock=FixedClock(g.FROZEN_NOW), build=build, name=skill_id)
    result = await skill(SkillRequest("t", "c", "", g.USER_ID, skill_id, None, False), ())
    assert g.as_json(result.data) == expected(AGENT)
