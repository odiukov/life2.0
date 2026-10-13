import asyncio
from typing import Any, cast

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from pydantic import BaseModel
from shared.adapters.llm.langchain_provider import LangChainLLMProvider
from shared.ports.llm import LLMInvalidOutput, LLMTask, LLMUnavailable


class Echo(BaseModel):
    word: str


class Runnable:
    def __init__(self, outputs: list[object], delay_s: float = 0.0) -> None:
        self.outputs = outputs
        self.inputs: list[list[BaseMessage]] = []
        self.delay_s = delay_s

    async def ainvoke(self, messages: list[BaseMessage]) -> object:
        self.inputs.append(list(messages))
        if self.delay_s:
            await asyncio.sleep(self.delay_s)
        item = self.outputs.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


class Model(Runnable):
    def __init__(
        self, structured: Runnable | None = None, text: list[object] | None = None
    ) -> None:
        super().__init__(text or [])
        self.structured_runnable = structured or Runnable([])
        self.schemas: list[type[BaseModel]] = []

    def with_structured_output(self, schema: type[BaseModel], *, include_raw: bool) -> Runnable:
        assert include_raw is True
        self.schemas.append(schema)
        return self.structured_runnable


class Factory:
    def __init__(self, model: Model) -> None:
        self.model = model
        self.tasks: list[LLMTask] = []

    def chat_model(self, task: LLMTask) -> BaseChatModel:
        self.tasks.append(task)
        return cast(BaseChatModel, self.model)


def provider(model: Model, timeout_s: float = 5.0) -> tuple[LangChainLLMProvider, Factory]:
    factory = Factory(model)
    return LangChainLLMProvider(factory, timeout_s=timeout_s), factory


def ok(word: str) -> dict[str, Any]:
    return {
        "parsed": Echo(word=word),
        "raw": AIMessage(f'{{"word": "{word}"}}'),
        "parsing_error": None,
    }


def bad(raw: str) -> dict[str, Any]:
    return {"parsed": None, "raw": AIMessage(raw), "parsing_error": ValueError("missing word")}


async def test_structured_returns_parsed_on_first_try() -> None:
    runnable = Runnable([ok("hi")])
    llm, factory = provider(Model(structured=runnable))
    assert await llm.structured(task=LLMTask.FAST, system="s", user="u", schema=Echo) == Echo(
        word="hi"
    )
    assert factory.tasks == [LLMTask.FAST]
    assert len(runnable.inputs) == 1


async def test_structured_repairs_once_with_the_parsing_error() -> None:
    runnable = Runnable([bad("{}"), ok("fixed")])
    llm, _ = provider(Model(structured=runnable))
    result = await llm.structured(task=LLMTask.FAST, system="s", user="u", schema=Echo)
    assert result.word == "fixed"
    second = runnable.inputs[1]
    assert isinstance(second[-2], AIMessage)
    assert second[-2].content == "{}"
    assert isinstance(second[-1], HumanMessage)
    assert "missing word" in str(second[-1].content)


async def test_structured_gives_up_after_one_repair() -> None:
    llm, _ = provider(Model(structured=Runnable([bad("{}"), bad("still bad")])))
    with pytest.raises(LLMInvalidOutput) as info:
        await llm.structured(task=LLMTask.FAST, system="s", user="u", schema=Echo)
    assert info.value.raw == "still bad"


async def test_provider_errors_become_unavailable() -> None:
    llm, _ = provider(Model(structured=Runnable([ConnectionError("reset")])))
    with pytest.raises(LLMUnavailable, match="ConnectionError"):
        await llm.structured(task=LLMTask.FAST, system="s", user="u", schema=Echo)


async def test_timeout_becomes_unavailable() -> None:
    llm, _ = provider(Model(structured=Runnable([ok("late")], delay_s=0.2)), timeout_s=0.01)
    with pytest.raises(LLMUnavailable, match="timeout"):
        await llm.structured(task=LLMTask.FAST, system="s", user="u", schema=Echo)


async def test_text_strips_and_rejects_empty() -> None:
    llm, _ = provider(Model(text=[AIMessage("  hello \n"), AIMessage("   ")]))
    assert await llm.text(task=LLMTask.SMART, system="s", user="u") == "hello"
    with pytest.raises(LLMInvalidOutput):
        await llm.text(task=LLMTask.SMART, system="s", user="u")


async def test_text_joins_content_blocks() -> None:
    message = AIMessage(content=[{"type": "text", "text": "a"}, {"type": "text", "text": "b"}])
    llm, _ = provider(Model(text=[message]))
    assert await llm.text(task=LLMTask.SMART, system="s", user="u") == "ab"


@pytest.mark.parametrize("method", ["text", "structured"])
async def test_invalid_output_is_preserved(method: str) -> None:
    error = LLMInvalidOutput("private-output", "invalid")
    llm, _ = provider(Model(text=[error], structured=Runnable([error])))
    call = (
        llm.text(task=LLMTask.FAST, system="s", user="u")
        if method == "text"
        else llm.structured(task=LLMTask.FAST, system="s", user="u", schema=Echo)
    )
    with pytest.raises(LLMInvalidOutput) as info:
        await call
    assert info.value is error


async def test_transport_failures_do_not_log_prompt_or_output(
    caplog: pytest.LogCaptureFixture,
) -> None:
    llm, _ = provider(Model(text=[ConnectionError("private-output")]))
    with pytest.raises(LLMUnavailable):
        await llm.text(task=LLMTask.FAST, system="private-system", user="private-user")
    assert "private-user" not in caplog.text
    assert "private-system" not in caplog.text
    assert "private-output" not in caplog.text


async def test_cancelled_call_is_not_unavailable() -> None:
    llm, _ = provider(Model(text=[asyncio.CancelledError()]))
    with pytest.raises(asyncio.CancelledError):
        await llm.text(task=LLMTask.FAST, system="s", user="u")


@pytest.mark.parametrize("error_type", [TypeError, ValueError])
@pytest.mark.parametrize("method", ["text", "structured"])
async def test_programming_errors_pass_through_without_retry(
    error_type: type[Exception], method: str
) -> None:
    from shared.adapters.llm.retrying import RetryingLLM

    from shared.tests.unit.llm.test_retrying_routing import no_sleep

    error = error_type("callback programming error")
    runnable = Runnable([error, error, error])
    model = Model(text=[error, error, error], structured=runnable)
    inner, _ = provider(model)
    llm = RetryingLLM(inner, sleep=no_sleep)
    call = (
        llm.text(task=LLMTask.FAST, system="s", user="u")
        if method == "text"
        else llm.structured(task=LLMTask.FAST, system="s", user="u", schema=Echo)
    )
    with pytest.raises(error_type) as info:
        await call
    assert info.value is error
    inputs = model.inputs if method == "text" else runnable.inputs
    assert len(inputs) == 1


def sdk_failure(name: str, status: int | None) -> Exception:
    import anthropic
    import groq
    import httpx
    import openai
    from google.genai import errors

    if name == "gemini_wrapped":
        from langchain_google_genai.chat_models import (
            GoogleAPIError,
            GoogleAuthenticationError,
            GoogleInvalidRequestError,
            GoogleRateLimitError,
        )

        if status == 400:
            return GoogleInvalidRequestError("invalid request")
        if status == 401:
            return GoogleAuthenticationError("invalid credentials")
        return (
            GoogleRateLimitError("quota")
            if status == 429
            else GoogleAPIError(503, {"error": {"message": "provider unavailable"}})
        )
    if name == "gemini":
        return errors.APIError(status or 503, {"error": {"message": "provider unavailable"}})
    module = {"anthropic": anthropic, "groq": groq, "openrouter": openai}[name]
    request = httpx.Request("POST", "https://provider.invalid")
    if status is None:
        return module.APIConnectionError(request=request)
    response = httpx.Response(status, request=request)
    return module.APIStatusError("provider failure", response=response, body=None)


@pytest.mark.parametrize("name", ["anthropic", "groq", "openrouter", "gemini", "gemini_wrapped"])
@pytest.mark.parametrize("status", [None, 429])
async def test_sdk_transport_and_quota_failures_retry_then_succeed(
    name: str, status: int | None
) -> None:
    from shared.adapters.llm.retrying import RetryingLLM

    from shared.tests.unit.llm.test_retrying_routing import no_sleep

    error = sdk_failure(name, status)
    model = Model(text=[error, error, AIMessage("ok")])
    inner, _ = provider(model)
    assert (
        await RetryingLLM(inner, sleep=no_sleep).text(task=LLMTask.FAST, system="s", user="u")
        == "ok"
    )
    assert len(model.inputs) == 3


@pytest.mark.parametrize("name", ["anthropic", "groq", "openrouter", "gemini", "gemini_wrapped"])
@pytest.mark.parametrize("status", [400, 401])
async def test_sdk_configuration_errors_pass_through_without_retry(name: str, status: int) -> None:
    from shared.adapters.llm.retrying import RetryingLLM

    from shared.tests.unit.llm.test_retrying_routing import no_sleep

    error = sdk_failure(name, status)
    model = Model(text=[error, error, error])
    inner, _ = provider(model)
    with pytest.raises(type(error)) as info:
        await RetryingLLM(inner, sleep=no_sleep).text(task=LLMTask.FAST, system="s", user="u")
    assert info.value is error
    assert len(model.inputs) == 1


async def test_timeout_retries_exactly_three_times() -> None:
    from shared.adapters.llm.retrying import RetryingLLM

    from shared.tests.unit.llm.test_retrying_routing import no_sleep

    runnable = Runnable([ok("late")], delay_s=0.2)
    inner, _ = provider(Model(structured=runnable), timeout_s=0.01)
    with pytest.raises(LLMUnavailable, match="timeout"):
        await RetryingLLM(inner, sleep=no_sleep).structured(
            task=LLMTask.FAST, system="s", user="u", schema=Echo
        )
    assert len(runnable.inputs) == 3


async def test_invalid_transport_configuration_is_not_retried() -> None:
    import httpx
    from shared.adapters.llm.retrying import RetryingLLM

    from shared.tests.unit.llm.test_retrying_routing import no_sleep

    error = httpx.UnsupportedProtocol("invalid provider URL")
    model = Model(text=[error, error, error])
    inner, _ = provider(model)
    with pytest.raises(httpx.UnsupportedProtocol) as info:
        await RetryingLLM(inner, sleep=no_sleep).text(task=LLMTask.FAST, system="s", user="u")
    assert info.value is error
    assert len(model.inputs) == 1
