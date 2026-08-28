"""Sanity-check the personas module: identity present for all 8 agents, contains
the mandatory phrases that downstream tests rely on (domain-expert role,
'redirect', 'calm authority'), and vocabulary anchors are non-empty."""
from __future__ import annotations

import pytest

AGENTS = [
    "sleep", "workout", "nutrition", "body",
    "mood", "habits", "recovery", "medication",
]


def test_identity_keys_match_eight_agents():
    from shared.personas import IDENTITY
    assert set(IDENTITY.keys()) == set(AGENTS)


def test_vocab_keys_match_eight_agents():
    from shared.personas import VOCAB
    assert set(VOCAB.keys()) == set(AGENTS)


@pytest.mark.parametrize("agent", AGENTS)
def test_identity_contains_required_phrases(agent):
    from shared.personas import IDENTITY
    block = IDENTITY[agent]
    # Domain-isolation language — every identity must redirect, not advise.
    assert "redirect" in block.lower()
    # Calm authority language is the persona signature.
    assert "calm authority" in block.lower()
    # Bilingual instruction must be present.
    assert "russian" in block.lower() or "ru" in block.lower()


@pytest.mark.parametrize("agent", AGENTS)
def test_vocab_block_is_nonempty_paragraph(agent):
    from shared.personas import VOCAB
    text = VOCAB[agent]
    assert len(text) > 50
    # Must reference at least one concrete anchor (rough sanity).
    assert "\n" in text or "," in text or ";" in text
