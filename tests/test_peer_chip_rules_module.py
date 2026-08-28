"""Sanity-check the peer-chip-rules module."""
from __future__ import annotations


def test_peer_chip_rules_is_string():
    from shared.peer_chip_rules import PEER_CHIP_RULES
    assert isinstance(PEER_CHIP_RULES, str)
    assert len(PEER_CHIP_RULES) > 100


def test_peer_chip_rules_lists_only_known_agent_names():
    from shared.peer_chip_rules import PEER_CHIP_RULES
    # All 8 known agent names must be referenced as the canonical list.
    for name in [
        "sleep", "workout", "nutrition", "body",
        "mood", "habits", "recovery", "medication",
    ]:
        assert name in PEER_CHIP_RULES


def test_peer_chip_rules_disallows_self_mention():
    from shared.peer_chip_rules import PEER_CHIP_RULES
    text = PEER_CHIP_RULES.lower()
    assert "do not mention your own agent" in text \
        or "not mention your own" in text


def test_peer_chip_rules_shows_chip_example():
    from shared.peer_chip_rules import PEER_CHIP_RULES
    # The constant should give the LLM at least one concrete example to copy.
    assert "/nutrition" in PEER_CHIP_RULES \
        or "/recovery" in PEER_CHIP_RULES
