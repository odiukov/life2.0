"""Sanity-check the grounding module: required clauses are present so the
constant is robust against accidental rewrites."""
from __future__ import annotations


def test_grounding_rules_is_string():
    from shared.grounding import GROUNDING_RULES
    assert isinstance(GROUNDING_RULES, str)
    assert len(GROUNDING_RULES) > 200


def test_grounding_rules_forbids_citations():
    from shared.grounding import GROUNDING_RULES
    text = GROUNDING_RULES.lower()
    assert "citations" in text or "according to" in text
    assert "studies show" in text or "meta-analyses" in text


def test_grounding_rules_forbids_phantom_metrics():
    from shared.grounding import GROUNDING_RULES
    text = GROUNDING_RULES.lower()
    assert "cortisol" in text
    assert "glucose" in text


def test_grounding_rules_allows_general_mechanisms():
    from shared.grounding import GROUNDING_RULES
    text = GROUNDING_RULES.lower()
    assert "general physiological mechanism" in text \
        or "mechanism" in text


def test_grounding_rules_requires_confidence_honesty():
    from shared.grounding import GROUNDING_RULES
    text = GROUNDING_RULES.lower()
    assert "confidence" in text or "sparse" in text
