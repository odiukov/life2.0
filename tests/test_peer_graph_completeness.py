"""Verify each agent's PEER_SKILLS map declares the cross-domain graph
defined in 2026-05-01-agent-personas-and-isolation-design.md §1, and that
every peer + skill name is real."""
from __future__ import annotations

import pytest

VALID_AGENTS = {
    "sleep", "workout", "nutrition", "body",
    "mood", "habits", "recovery", "medication",
}

# Source of truth: spec §1.
EXPECTED_PEERS: dict[str, set[str]] = {
    "sleep": {"workout", "nutrition", "recovery", "mood", "medication"},
    "workout": {"recovery", "sleep", "nutrition", "body", "habits", "medication"},
    "nutrition": {"workout", "body", "sleep", "mood", "medication"},
    "body": {"nutrition", "workout", "recovery"},
    "mood": {"sleep", "recovery", "workout", "habits", "medication"},
    "habits": {"mood", "sleep", "workout"},
    "recovery": {"sleep", "workout", "nutrition", "mood"},
    "medication": {"mood", "sleep", "recovery"},
}


@pytest.mark.parametrize("agent", sorted(EXPECTED_PEERS.keys()))
def test_peer_skills_matches_design(agent):
    mod = __import__(f"agents.{agent}.app.skills", fromlist=["PEER_SKILLS"])
    peer_skills = getattr(mod, "PEER_SKILLS")
    assert set(peer_skills.keys()) == EXPECTED_PEERS[agent], \
        f"{agent}: PEER_SKILLS keys differ from spec"


@pytest.mark.parametrize("agent", sorted(EXPECTED_PEERS.keys()))
def test_peer_skills_target_real_agents(agent):
    mod = __import__(f"agents.{agent}.app.skills", fromlist=["PEER_SKILLS"])
    peer_skills = getattr(mod, "PEER_SKILLS")
    for peer in peer_skills.keys():
        assert peer in VALID_AGENTS, f"{agent} → unknown peer {peer!r}"


@pytest.mark.parametrize("agent", sorted(EXPECTED_PEERS.keys()))
def test_peer_skills_target_real_skill_ids(agent):
    """Every PEER_SKILLS value must be an A2A skill ID declared by the target peer."""
    mod = __import__(f"agents.{agent}.app.skills", fromlist=["PEER_SKILLS"])
    peer_skills = getattr(mod, "PEER_SKILLS")
    for peer, skill_id in peer_skills.items():
        peer_mod = __import__(f"agents.{peer}.app.skills", fromlist=["SKILLS"])
        peer_skill_ids = {s.id for s in getattr(peer_mod, "SKILLS")}
        assert skill_id in peer_skill_ids, \
            f"{agent} → {peer}.{skill_id} but peer doesn't declare it"
