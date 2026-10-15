"""Unit tests for the orchestrator focus_sources auto-detector + peer-registry helper."""

from __future__ import annotations

from orchestrator.domain.focus import (
    autodetect_focus_sources,
    merge_focus_sources,
)


def _state(text: str) -> str:
    return text


# ----------------------------- autodetect -----------------------------


def test_autodetect_cue_word_plus_two_domains_ru():
    """The exact failure case from the bug report."""
    state = _state("Как я спал учитывая мое питание и занятия спортом?")
    out = autodetect_focus_sources(state, "sleep", ("workout", "nutrition"))
    assert sorted(out) == ["nutrition", "workout"]


def test_autodetect_no_cue_no_other_domains_returns_empty():
    state = _state("Как я спал?")
    assert autodetect_focus_sources(state, "sleep", ("workout", "nutrition")) == []


def test_autodetect_skips_primary_domain():
    """Primary's own keywords must never appear in focus_sources."""
    state = _state("Посоветуй тренировку учитывая мой сон")
    out = autodetect_focus_sources(state, "workout", ("sleep", "nutrition"))
    assert out == ["sleep"]


def test_autodetect_english_based_on():
    state = _state("How did I sleep based on my workouts and food intake")
    out = autodetect_focus_sources(state, "sleep", ("workout", "nutrition"))
    assert sorted(out) == ["nutrition", "workout"]


def test_autodetect_enumeration_without_cue_word_triggers_when_primary_referenced():
    """Mentioning sleep and nutrition together fans out."""
    state = _state("Как мой сон и питание сегодня?")
    out = autodetect_focus_sources(state, "sleep", ("workout", "nutrition"))
    assert out == ["nutrition"]


def test_autodetect_returns_only_candidates():
    """Recovery mentioned but not in candidate list → ignored."""
    state = _state("Как я спал учитывая восстановление и питание")
    out = autodetect_focus_sources(state, "sleep", ("workout", "nutrition"))
    assert out == ["nutrition"]


def test_autodetect_no_user_message_returns_empty():
    assert autodetect_focus_sources("", "sleep", ("workout",)) == []


def test_autodetect_state_none_returns_empty():
    assert autodetect_focus_sources("", "sleep", ("workout",)) == []


def test_autodetect_uses_latest_human_message():
    state = "как я спал учитывая питание"
    out = autodetect_focus_sources(state, "sleep", ("workout", "nutrition"))
    assert out == ["nutrition"]


# ----------------------------- merge ----------------------------------


def test_merge_dedups_and_preserves_order():
    out = merge_focus_sources(["nutrition"], ["nutrition", "workout"])
    assert out == ["nutrition", "workout"]


def test_merge_both_empty_returns_none():
    assert merge_focus_sources(None, []) is None
    assert merge_focus_sources([], []) is None


def test_merge_explicit_only():
    assert merge_focus_sources(["workout"], []) == ["workout"]


def test_merge_auto_only():
    assert merge_focus_sources(None, ["nutrition"]) == ["nutrition"]
