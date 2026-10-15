from recovery.application.dashboard import card, detail
from shared.skill_ids import Dashboard
from shared.testing import dashboard_golden as g


async def test_card_matches_the_golden() -> None:
    assert await g.golden_call(card, Dashboard.CARD) == g.expected_card("recovery")


async def test_detail_matches_the_golden() -> None:
    assert await g.golden_call(detail, Dashboard.DETAIL) == g.expected_detail("recovery")
