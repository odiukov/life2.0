from body.application.dashboard import card
from shared.skill_ids import Dashboard
from shared.testing import dashboard_golden as g


async def test_card_matches_the_golden() -> None:
    assert await g.golden_call(card, Dashboard.CARD) == g.expected_card("body")
