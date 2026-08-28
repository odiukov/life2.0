"""Verify body executor uses the shared infer_skill_and_consults path
(same as sleep/workout/nutrition) and that the depth-1 cap helper is
imported."""
from __future__ import annotations


import pytest


def test_body_executor_imports_intent_router():
    from agents.body.app import executor as body_exec
    assert hasattr(body_exec, "infer_skill_and_consults")


def test_body_executor_imports_peer_fetch():
    from agents.body.app import executor as body_exec
    assert hasattr(body_exec, "fetch_peer_artifacts")
    assert hasattr(body_exec, "default_peer_registry")


def test_body_executor_imports_depth_cap_helper():
    from agents.body.app import executor as body_exec
    assert hasattr(body_exec, "is_peer_call_from_metadata")


def test_body_skills_declares_peer_skills():
    from agents.body.app import skills as body_skills
    peers = getattr(body_skills, "PEER_SKILLS", None)
    assert isinstance(peers, dict)
    assert set(peers.keys()) == {"nutrition", "workout", "recovery"}
