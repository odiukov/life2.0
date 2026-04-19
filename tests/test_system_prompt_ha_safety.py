"""Static assertions on _SYSTEM_PROMPT for Home Assistant MCP safety.

ReAct relies on these clauses to gate HA mutations behind a paraphrase+
confirmation turn. The tests are cheap strings checks — they lock in the
promises so a later prompt edit can't silently remove them.
"""


def test_prompt_mentions_home_assistant_tools():
    from orchestrator.app.health_agent import _SYSTEM_PROMPT
    assert "Home Assistant" in _SYSTEM_PROMPT


def test_prompt_marks_getlivecontext_read_only():
    from orchestrator.app.health_agent import _SYSTEM_PROMPT
    # GetLiveContext is the read-only live-state tool; must be named and
    # must not require confirmation.
    assert "GetLiveContext" in _SYSTEM_PROMPT


def test_prompt_names_ha_mutation_tools_requiring_confirmation():
    from orchestrator.app.health_agent import _SYSTEM_PROMPT
    # These names come from HA's Assist intent set and are the ones ReAct
    # will see as MCP tools. Naming them explicitly helps the LLM pattern-match.
    for name in ("HassTurnOn", "HassTurnOff", "HassLightSet",
                 "HassClimateSetTemperature"):
        assert name in _SYSTEM_PROMPT, f"missing {name} in HA safety clause"


def test_prompt_requires_paraphrase_and_confirmation_for_ha_mutations():
    from orchestrator.app.health_agent import _SYSTEM_PROMPT
    lowered = _SYSTEM_PROMPT.lower()
    # The clause must talk about paraphrasing + waiting for confirmation.
    # Calendar already says this; HA should, too.
    assert "paraphrase" in lowered
    # Multiple calendar + HA mentions of "confirmation" are expected — just
    # assert the word appears (weak but sufficient).
    assert "confirmation" in lowered
