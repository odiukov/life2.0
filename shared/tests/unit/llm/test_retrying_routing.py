import pytest
from pydantic import BaseModel
from shared.adapters.llm.retrying import RetryingLLM
from shared.adapters.llm.routing import RoutingLLM
from shared.ports.llm import LLMInvalidOutput, LLMTask, LLMUnavailable
from shared.testing.fakes import FakeLLM


class Echo(BaseModel):
    word: str


async def no_sleep(_: float) -> None:
    return None


async def test_retries_unavailable_then_succeeds() -> None:
    inner = FakeLLM()
    inner.queue_text(LLMUnavailable("1"), LLMUnavailable("2"), "ok")
    llm = RetryingLLM(inner, attempts=3, sleep=no_sleep)
    assert await llm.text(task=LLMTask.FAST, system="s", user="u") == "ok"
    assert len(inner.calls) == 3


async def test_gives_up_after_attempts() -> None:
    inner = FakeLLM()
    inner.queue_text(LLMUnavailable("1"), LLMUnavailable("2"))
    with pytest.raises(LLMUnavailable):
        await RetryingLLM(inner, attempts=2, sleep=no_sleep).text(
            task=LLMTask.FAST, system="s", user="u"
        )


async def test_never_retries_invalid_output() -> None:
    inner = FakeLLM()
    inner.queue_structured(LLMInvalidOutput("x", "bad"), {"word": "unused"})
    with pytest.raises(LLMInvalidOutput):
        await RetryingLLM(inner, sleep=no_sleep).structured(
            task=LLMTask.FAST, system="s", user="u", schema=Echo
        )
    assert len(inner.calls) == 1


async def test_routing_dispatches_by_task() -> None:
    fast, smart = FakeLLM(), FakeLLM()
    fast.queue_text("fast")
    smart.queue_text("smart")
    llm = RoutingLLM(dict.fromkeys(LLMTask, fast) | {LLMTask.SMART: smart})
    assert await llm.text(task=LLMTask.SMART, system="s", user="u") == "smart"
    assert await llm.text(task=LLMTask.FAST, system="s", user="u") == "fast"


def test_routing_requires_every_task() -> None:
    with pytest.raises(ValueError, match="mood_coach"):
        RoutingLLM({LLMTask.FAST: FakeLLM(), LLMTask.SMART: FakeLLM()})


async def test_retry_backoff_doubles_and_preserves_request() -> None:
    delays: list[float] = []

    async def sleep(delay: float) -> None:
        delays.append(delay)

    inner = FakeLLM()
    inner.queue_structured(LLMUnavailable("quota"), LLMUnavailable("transport"), {"word": "ok"})
    answer = await RetryingLLM(inner, backoff_s=0.25, sleep=sleep).structured(
        task=LLMTask.SMART, system="system", user="user", schema=Echo
    )
    assert answer == Echo(word="ok")
    assert delays == [0.25, 0.5]
    assert all(
        call.task == LLMTask.SMART
        and call.system == "system"
        and call.user == "user"
        and call.schema is Echo
        for call in inner.calls
    )


async def test_text_invalid_output_is_not_retried() -> None:
    inner = FakeLLM()
    inner.queue_text(LLMInvalidOutput("", "blank"), "unused")
    with pytest.raises(LLMInvalidOutput):
        await RetryingLLM(inner, sleep=no_sleep).text(task=LLMTask.FAST, system="s", user="u")
    assert len(inner.calls) == 1


async def test_structured_routes_mood_to_its_provider() -> None:
    fast, smart, mood = FakeLLM(), FakeLLM(), FakeLLM()
    mood.queue_structured({"word": "coach"})
    llm = RoutingLLM(
        dict.fromkeys(LLMTask, fast) | {LLMTask.SMART: smart, LLMTask.MOOD_COACH: mood}
    )
    assert await llm.structured(task=LLMTask.MOOD_COACH, system="s", user="u", schema=Echo) == Echo(
        word="coach"
    )
    assert not fast.calls
    assert not smart.calls


def test_zero_attempts_rejected() -> None:
    with pytest.raises(ValueError, match="at least 1"):
        RetryingLLM(FakeLLM(), attempts=0)
