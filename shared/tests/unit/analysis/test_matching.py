import pytest
from shared.analysis.matching import resolve_name, slug
from shared.testing.fakes import FakeLLM

NAMES = ["meditation", "cold-shower", "vitamin-d", "b12"]


@pytest.mark.parametrize(
    ("raw", "expected"), [("Cold Shower", "cold-shower"), ("  B12 ", "b12"), ("", "")]
)
def test_slug(raw: str, expected: str) -> None:
    assert slug(raw) == expected


async def test_exact_and_fuzzy_need_no_model() -> None:
    llm = FakeLLM()
    assert await resolve_name("cold shower", NAMES, llm=llm) == "cold-shower"
    assert await resolve_name("meditaton", NAMES, llm=llm) == "meditation"
    assert llm.calls == []


async def test_other_language_goes_to_the_model_and_is_constrained() -> None:
    llm = FakeLLM()
    llm.queue_structured({"name": "vitamin-d"}, {"name": "aspirin"})
    assert await resolve_name("принял витамин д", NAMES, llm=llm) == "vitamin-d"
    assert "vitamin-d" in llm.calls[0].system
    assert await resolve_name("аспирин", NAMES, llm=llm) is None  # not in the list → rejected


async def test_no_names_or_model_failure_is_none() -> None:
    llm = FakeLLM()
    assert await resolve_name("x", [], llm=llm) is None
    llm.queue_structured(RuntimeError("down"))
    assert await resolve_name("что-то", NAMES, llm=llm) is None


async def test_ambiguous_fuzzy_matches_use_the_model() -> None:
    llm = FakeLLM()
    llm.queue_structured({"name": "vitamin-d3"})
    assert await resolve_name("vitamin d2", ["vitamin-d", "vitamin-d3"], llm=llm) == "vitamin-d3"
    assert len(llm.calls) == 1


async def test_empty_input_skips_the_model() -> None:
    llm = FakeLLM()
    assert await resolve_name("  ", NAMES, llm=llm) is None
    assert llm.calls == []
