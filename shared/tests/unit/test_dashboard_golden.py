from shared.testing import dashboard_golden as g


def test_every_card_part_has_one_owner() -> None:
    summary = g.golden("dashboard_summary")
    assert set(summary["rings"]) == set(g.RING_OWNERS)
    cards = {agent: g.expected_card(agent) for agent in g.TILE_ORDER}
    assert all(card["tile"] is not None for card in cards.values())
    rings = {k for card in cards.values() for k in card["rings"]}  # type: ignore[union-attr]
    assert rings == set(g.RING_OWNERS)


def test_details_exist_for_every_detail_agent() -> None:
    for agent in g.DETAIL_AGENTS:
        assert g.expected_detail(agent)["agent"] == agent


def test_seed_rows_belong_to_known_agents() -> None:
    agents = {r.agent for r in g.health_log_rows()}
    assert agents == {"sleep", "workout", "nutrition", "mood", "habits", "medication", "body"}
    assert all(r.recorded_at.tzinfo is not None for r in g.health_log_rows())
