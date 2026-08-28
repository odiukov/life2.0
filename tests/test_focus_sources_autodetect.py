"""Unit tests for the orchestrator focus_sources auto-detector + peer-registry helper."""
from __future__ import annotations


from langchain_core.messages import AIMessage, HumanMessage  # noqa: E402

from orchestrator.app.health_agent import (  # noqa: E402
    _autodetect_focus_sources,
    _merge_focus_sources,
)


def _state(text: str) -> dict:
    return {"messages": [HumanMessage(content=text)]}


# ----------------------------- autodetect -----------------------------


def test_autodetect_cue_word_plus_two_domains_ru():
    """The exact failure case from the bug report."""
    state = _state("Как я спал учитывая мое питание и занятия спортом?")
    out = _autodetect_focus_sources(state, "sleep", ("workout", "nutrition"))
    assert sorted(out) == ["nutrition", "workout"]


def test_autodetect_no_cue_no_other_domains_returns_empty():
    state = _state("Как я спал?")
    assert _autodetect_focus_sources(state, "sleep", ("workout", "nutrition")) == []


def test_autodetect_skips_primary_domain():
    """Primary's own keywords must never appear in focus_sources."""
    state = _state("Посоветуй тренировку учитывая мой сон")
    out = _autodetect_focus_sources(state, "workout", ("sleep", "nutrition"))
    assert out == ["sleep"]


def test_autodetect_english_based_on():
    state = _state("How did I sleep based on my workouts and food intake")
    out = _autodetect_focus_sources(state, "sleep", ("workout", "nutrition"))
    assert sorted(out) == ["nutrition", "workout"]


def test_autodetect_enumeration_without_cue_word_triggers_when_primary_referenced():
    """Free-form 'мой сон и питание' (sleep is primary, питание mentioned) → fan out."""
    state = _state("Как мой сон и питание сегодня?")
    out = _autodetect_focus_sources(state, "sleep", ("workout", "nutrition"))
    assert out == ["nutrition"]


def test_autodetect_returns_only_candidates():
    """Recovery mentioned but not in candidate list → ignored."""
    state = _state("Как я спал учитывая восстановление и питание")
    out = _autodetect_focus_sources(state, "sleep", ("workout", "nutrition"))
    assert out == ["nutrition"]


def test_autodetect_no_user_message_returns_empty():
    assert _autodetect_focus_sources({"messages": []}, "sleep", ("workout",)) == []


def test_autodetect_state_none_returns_empty():
    assert _autodetect_focus_sources(None, "sleep", ("workout",)) == []


def test_autodetect_uses_latest_human_message():
    state = {"messages": [
        HumanMessage(content="random hello"),
        AIMessage(content="hi"),
        HumanMessage(content="как я спал учитывая питание"),
    ]}
    out = _autodetect_focus_sources(state, "sleep", ("workout", "nutrition"))
    assert out == ["nutrition"]


# ----------------------------- merge ----------------------------------


def test_merge_dedups_and_preserves_order():
    out = _merge_focus_sources(["nutrition"], ["nutrition", "workout"])
    assert out == ["nutrition", "workout"]


def test_merge_both_empty_returns_none():
    assert _merge_focus_sources(None, []) is None
    assert _merge_focus_sources([], []) is None


def test_merge_explicit_only():
    assert _merge_focus_sources(["workout"], []) == ["workout"]


def test_merge_auto_only():
    assert _merge_focus_sources(None, ["nutrition"]) == ["nutrition"]


# ----------------------------- peer registry --------------------------


def test_default_peer_registry_includes_all_eight_peers():
    from shared.peer import default_peer_registry
    reg = default_peer_registry()
    assert set(reg.keys()) == {
        "sleep", "workout", "nutrition", "body",
        "mood", "habits", "recovery", "medication",
    }
    for name, info in reg.items():
        assert info["url"].startswith("http://")


def test_default_peer_registry_respects_env_override(monkeypatch):
    from shared.peer import default_peer_registry
    monkeypatch.setenv("WORKOUT_AGENT_URL", "http://override-workout:9999/")
    reg = default_peer_registry()
    assert reg["workout"]["url"] == "http://override-workout:9999/"
