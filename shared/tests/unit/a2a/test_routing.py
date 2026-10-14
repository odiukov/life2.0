import pytest
from shared.a2a.routing import MANDATORY_CONSULTS, resolve_skill
from shared.ports.llm import LLMInvalidOutput, LLMUnavailable
from shared.testing.fakes import FakeLLM

SKILLS = ["log_meal", "analyze_nutrition", "get_nutrition_recommendations", "set_body_profile"]
PEERS = ["workout", "body", "sleep", "mood", "medication"]


async def route(llm: FakeLLM, **overrides: object):
    args: dict[str, object] = {
        "llm": llm,
        "message": "как питание?",
        "skills": SKILLS,
        "candidate_peers": PEERS,
        "requested_skill": None,
        "focus_sources": None,
    }
    args.update(overrides)
    return await resolve_skill(**args)  # type: ignore[arg-type]


async def test_requested_skill_short_circuits_and_adds_mandatory_consults() -> None:
    llm = FakeLLM()
    choice = await route(llm, requested_skill="get_nutrition_recommendations")
    assert choice is not None
    assert choice.skill_id == "get_nutrition_recommendations"
    assert choice.consult == ("workout",)
    assert llm.calls == []


async def test_focus_sources_override_and_are_filtered() -> None:
    choice = await route(
        FakeLLM(), requested_skill="analyze_nutrition", focus_sources=("sleep", "bogus")
    )
    assert choice is not None
    assert choice.consult == ("sleep",)


async def test_llm_decision_is_filtered_to_candidates() -> None:
    llm = FakeLLM()
    llm.queue_structured({"skill": "analyze_nutrition", "consult": ["sleep", "finance"]})
    choice = await route(llm)
    assert choice is not None
    assert (choice.skill_id, choice.consult) == ("analyze_nutrition", ("sleep",))
    assert "analyze_nutrition" in llm.calls[0].system


async def test_mandatory_consults_join_the_llm_choice() -> None:
    llm = FakeLLM()
    llm.queue_structured({"skill": "get_nutrition_recommendations", "consult": []})
    choice = await route(llm)
    assert choice is not None
    assert choice.consult == ("workout",)


@pytest.mark.parametrize(
    "answer",
    [{"skill": "dance", "consult": []}, LLMInvalidOutput("x", "bad"), LLMUnavailable("down")],
)
async def test_unusable_answers_give_none(answer: object) -> None:
    llm = FakeLLM()
    llm.queue_structured(answer)
    assert await route(llm) is None


def test_legacy_module_shares_the_same_table() -> None:
    from shared import intent

    assert intent.MANDATORY_CONSULTS is MANDATORY_CONSULTS


async def test_empty_focus_overrides_mandatory_consults() -> None:
    llm = FakeLLM()
    choice = await route(llm, requested_skill="get_nutrition_recommendations", focus_sources=())
    assert choice is not None
    assert choice.consult == ()
    assert not llm.calls


async def test_unknown_explicit_skill_falls_back_to_structured_fast_routing() -> None:
    from shared.a2a.routing import IntentDecision
    from shared.ports.llm import LLMTask

    llm = FakeLLM()
    llm.queue_structured({"skill": "log_meal"})
    choice = await route(llm, requested_skill="unknown")
    assert choice is not None
    assert choice.skill_id == "log_meal"
    assert choice.consult == ()
    assert llm.calls[0].task is LLMTask.FAST
    assert llm.calls[0].schema is IntentDecision
    assert llm.calls[0].user == "как питание?"


async def test_mandatory_consults_are_filtered_and_deduplicated() -> None:
    llm = FakeLLM()
    llm.queue_structured(
        {"skill": "get_workout_recommendations", "consult": ["sleep", "sleep", "bogus"]}
    )
    choice = await route(llm, skills=["get_workout_recommendations"], candidate_peers=["sleep"])
    assert choice is not None
    assert choice.consult == ("sleep",)


async def test_llm_focus_overrides_both_llm_and_mandatory_peers() -> None:
    llm = FakeLLM()
    llm.queue_structured({"skill": "get_nutrition_recommendations", "consult": ["body"]})
    choice = await route(llm, focus_sources=("sleep", "invalid"))
    assert choice is not None
    assert choice.consult == ("sleep",)


@pytest.mark.parametrize(
    "answer", [{"consult": []}, {"skill": 1}, {"skill": "log_meal", "consult": [1]}, "text"]
)
async def test_malformed_structured_answers_give_none(answer: object) -> None:
    llm = FakeLLM()
    llm.queue_structured(answer)
    assert await route(llm) is None
