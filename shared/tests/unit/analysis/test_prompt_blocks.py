import pytest

"""Sanity-check the grounding module: required clauses are present so the
constant is robust against accidental rewrites."""


def test_grounding_rules_is_string():
    from shared.analysis.grounding import GROUNDING_RULES

    assert isinstance(GROUNDING_RULES, str)
    assert len(GROUNDING_RULES) > 200


def test_grounding_rules_forbids_citations():
    from shared.analysis.grounding import GROUNDING_RULES

    text = GROUNDING_RULES.lower()
    assert "citations" in text or "according to" in text
    assert "studies show" in text or "meta-analyses" in text


def test_grounding_rules_forbids_phantom_metrics():
    from shared.analysis.grounding import GROUNDING_RULES

    text = GROUNDING_RULES.lower()
    assert "cortisol" in text
    assert "glucose" in text


def test_grounding_rules_allows_general_mechanisms():
    from shared.analysis.grounding import GROUNDING_RULES

    text = GROUNDING_RULES.lower()
    assert "general physiological mechanism" in text or "mechanism" in text


def test_grounding_rules_requires_confidence_honesty():
    from shared.analysis.grounding import GROUNDING_RULES

    text = GROUNDING_RULES.lower()
    assert "confidence" in text or "sparse" in text


"""Sanity-check the personas module: identity present for all 9 agents, contains
the mandatory phrases that downstream tests rely on (domain-expert role,
'redirect', 'calm authority'), and vocabulary anchors are non-empty."""


AGENTS = [
    "sleep",
    "workout",
    "nutrition",
    "body",
    "mood",
    "habits",
    "recovery",
    "medication",
]


def test_identity_keys_match_nine_agents():
    from shared.analysis.personas import IDENTITY

    assert set(IDENTITY.keys()) == {*AGENTS, "finance"}


def test_vocab_keys_match_nine_agents():
    from shared.analysis.personas import VOCAB

    assert set(VOCAB.keys()) == {*AGENTS, "finance"}


@pytest.mark.parametrize("agent", AGENTS)
def test_identity_contains_required_phrases(agent):
    from shared.analysis.personas import IDENTITY

    block = IDENTITY[agent]
    # Domain-isolation language — every identity must redirect, not advise.
    assert "redirect" in block.lower()
    # Calm authority language is the persona signature.
    assert "calm authority" in block.lower()
    # Bilingual instruction must be present.
    assert "russian" in block.lower() or "ru" in block.lower()


@pytest.mark.parametrize("agent", AGENTS)
def test_vocab_block_is_nonempty_paragraph(agent):
    from shared.analysis.personas import VOCAB

    text = VOCAB[agent]
    assert len(text) > 50
    # Must reference at least one concrete anchor (rough sanity).
    assert "\n" in text or "," in text or ";" in text


"""Sanity-check the peer-chip-rules module."""


def test_peer_chip_rules_is_string():
    from shared.analysis.chip_rules import PEER_CHIP_RULES

    assert isinstance(PEER_CHIP_RULES, str)
    assert len(PEER_CHIP_RULES) > 100


def test_peer_chip_rules_lists_only_known_agent_names():
    from shared.analysis.chip_rules import PEER_CHIP_RULES

    # All 8 known agent names must be referenced as the canonical list.
    for name in [
        "sleep",
        "workout",
        "nutrition",
        "body",
        "mood",
        "habits",
        "recovery",
        "medication",
    ]:
        assert name in PEER_CHIP_RULES


def test_peer_chip_rules_disallows_self_mention():
    from shared.analysis.chip_rules import PEER_CHIP_RULES

    text = PEER_CHIP_RULES.lower()
    assert "do not mention your own agent" in text or "not mention your own" in text


def test_peer_chip_rules_shows_chip_example():
    from shared.analysis.chip_rules import PEER_CHIP_RULES

    # The constant should give the LLM at least one concrete example to copy.
    assert "/nutrition" in PEER_CHIP_RULES or "/recovery" in PEER_CHIP_RULES


@pytest.mark.parametrize("agent", AGENTS)
@pytest.mark.parametrize("with_peers", [False, True])
def test_migrated_analysis_modes_include_prompt_blocks(agent, with_peers):
    """Every registered analysis tail uses the shared identity and grounding layout."""
    import importlib

    from shared.analysis.chip_rules import PEER_CHIP_RULES
    from shared.analysis.grounding import GROUNDING_RULES
    from shared.analysis.personas import IDENTITY
    from shared.analysis.prompt import PromptInputs, compose_prompt

    module = importlib.import_module(
        "nutrition.application.analyze" if agent == "nutrition" else f"{agent}.composition"
    )
    spec = getattr(module, f"{agent.upper()}_SPEC")
    assert spec.tails
    for mode, tail in spec.tails.items():
        peer = spec.peer_order[0]
        system, user = compose_prompt(
            PromptInputs(
                agent=agent,
                mode=mode,
                sections=[],
                peers={peer: "Peer summary"} if with_peers else {},
                peer_order=spec.peer_order,
                memories=[],
                message="Analyze",
                tail=tail,
            )
        )
        assert IDENTITY[agent] in system
        assert GROUNDING_RULES in system
        assert (PEER_CHIP_RULES in user) is with_peers
        assert tail in user
