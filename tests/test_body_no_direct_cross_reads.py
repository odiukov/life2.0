"""Body agent must consult nutrition + workout via A2A peer-consult, not by
reading their tables directly. fetch_recent_logs in body/app/prompt.py is a
red flag for cross-domain reads — see spec §5 + §10."""
from __future__ import annotations

from pathlib import Path

import pytest


def _read_body_prompt() -> str:
    return Path("agents/body/app/prompt.py").read_text(encoding="utf-8")


def test_body_prompt_does_not_fetch_nutrition_logs():
    src = _read_body_prompt()
    # Tolerate a comment in the file but not an actual call.
    assert 'fetch_recent_logs(user_id, "nutrition"' not in src
    assert "fetch_recent_logs(user_id, 'nutrition'" not in src


def test_body_prompt_does_not_fetch_workout_logs():
    src = _read_body_prompt()
    assert 'fetch_recent_logs(user_id, "workout"' not in src
    assert "fetch_recent_logs(user_id, 'workout'" not in src


def test_body_prompt_imports_peer_chip_rules():
    src = _read_body_prompt()
    assert "from shared.peer_chip_rules import" in src \
        or "from shared.peer_chip_rules" in src
