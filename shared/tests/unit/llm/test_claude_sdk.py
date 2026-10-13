from collections.abc import AsyncIterator
from typing import Any

import pytest
from pydantic import BaseModel

sdk = pytest.importorskip("claude_agent_sdk")

from shared.adapters.llm import claude_sdk  # noqa: E402
from shared.ports.llm import LLMInvalidOutput, LLMTask, LLMUnavailable  # noqa: E402

MODELS = {LLMTask.FAST: "claude-sonnet-5-5", LLMTask.SMART: "claude-opus-5-5"}


class Echo(BaseModel):
    word: str


def result(**kwargs: Any) -> Any:
    defaults: dict[str, Any] = {
        "subtype": "success",
        "duration_ms": 1,
        "duration_api_ms": 1,
        "is_error": False,
        "num_turns": 1,
        "session_id": "s",
    }
    return sdk.ResultMessage(**{**defaults, **kwargs})


def fake_query(*messages: Any, seen: list[Any] | None = None) -> Any:
    async def query(*, prompt: str, options: Any) -> AsyncIterator[Any]:
        if seen is not None:
            seen.append(options)
        for message in messages:
            yield message

    return query


@pytest.fixture
def provider() -> claude_sdk.ClaudeSdkLLMProvider:
    return claude_sdk.ClaudeSdkLLMProvider(models=MODELS, timeout_s=5)


async def test_uses_structured_output(
    monkeypatch: pytest.MonkeyPatch, provider: claude_sdk.ClaudeSdkLLMProvider
) -> None:
    seen: list[Any] = []
    monkeypatch.setattr(
        claude_sdk, "query", fake_query(result(structured_output={"word": "a"}), seen=seen)
    )
    echo = await provider.structured(task=LLMTask.FAST, system="s", user="u", schema=Echo)
    assert echo == Echo(word="a")
    assert seen[0].model == "claude-sonnet-5-5"
    assert seen[0].tools == []
    assert seen[0].setting_sources == []
    assert seen[0].output_format["type"] == "json_schema"


async def test_falls_back_to_json_in_text(
    monkeypatch: pytest.MonkeyPatch, provider: claude_sdk.ClaudeSdkLLMProvider
) -> None:
    monkeypatch.setattr(
        claude_sdk, "query", fake_query(result(result='```json\n{"word": "b"}\n```'))
    )
    assert (
        await provider.structured(task=LLMTask.FAST, system="s", user="u", schema=Echo)
    ).word == "b"


async def test_error_result_is_unavailable(
    monkeypatch: pytest.MonkeyPatch, provider: claude_sdk.ClaudeSdkLLMProvider
) -> None:
    monkeypatch.setattr(claude_sdk, "query", fake_query(result(is_error=True, subtype="error")))
    with pytest.raises(LLMUnavailable):
        await provider.text(task=LLMTask.SMART, system="s", user="u")


async def test_invalid_payload_is_invalid_output(
    monkeypatch: pytest.MonkeyPatch, provider: claude_sdk.ClaudeSdkLLMProvider
) -> None:
    monkeypatch.setattr(claude_sdk, "query", fake_query(result(structured_output={"x": 1})))
    with pytest.raises(LLMInvalidOutput):
        await provider.structured(task=LLMTask.FAST, system="s", user="u", schema=Echo)


async def test_missing_result_is_unavailable_and_blank_text_is_invalid(
    monkeypatch: pytest.MonkeyPatch, provider: claude_sdk.ClaudeSdkLLMProvider
) -> None:
    monkeypatch.setattr(claude_sdk, "query", fake_query())
    with pytest.raises(LLMUnavailable):
        await provider.text(task=LLMTask.FAST, system="s", user="u")
    monkeypatch.setattr(claude_sdk, "query", fake_query(result(result="   ")))
    with pytest.raises(LLMInvalidOutput):
        await provider.text(task=LLMTask.FAST, system="s", user="u")


async def test_sdk_errors_map_to_unavailable(
    monkeypatch: pytest.MonkeyPatch, provider: claude_sdk.ClaudeSdkLLMProvider
) -> None:
    async def failed(**_: Any) -> AsyncIterator[Any]:
        raise sdk.CLIConnectionError("disconnected")
        yield  # pragma: no cover

    monkeypatch.setattr(claude_sdk, "query", failed)
    with pytest.raises(LLMUnavailable, match="disconnected"):
        await provider.text(task=LLMTask.FAST, system="s", user="u")


async def test_timeout_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio

    async def slow(**_: Any) -> AsyncIterator[Any]:
        await asyncio.sleep(0.2)
        yield result(result="late")

    monkeypatch.setattr(claude_sdk, "query", slow)
    llm = claude_sdk.ClaudeSdkLLMProvider(models=MODELS, timeout_s=0.01)
    with pytest.raises(LLMUnavailable, match="timeout"):
        await llm.text(task=LLMTask.FAST, system="s", user="u")


async def test_bad_json_is_invalid_output(
    monkeypatch: pytest.MonkeyPatch, provider: claude_sdk.ClaudeSdkLLMProvider
) -> None:
    monkeypatch.setattr(claude_sdk, "query", fake_query(result(result="not json")))
    with pytest.raises(LLMInvalidOutput) as info:
        await provider.structured(task=LLMTask.FAST, system="s", user="u", schema=Echo)
    assert info.value.raw == "not json"


async def test_text_uses_smart_route_and_strips(
    monkeypatch: pytest.MonkeyPatch, provider: claude_sdk.ClaudeSdkLLMProvider
) -> None:
    seen: list[Any] = []
    monkeypatch.setattr(claude_sdk, "query", fake_query(result(result="  hello  "), seen=seen))
    assert await provider.text(task=LLMTask.SMART, system="s", user="u") == "hello"
    assert seen[0].model == MODELS[LLMTask.SMART]
    assert seen[0].system_prompt == "s"


@pytest.mark.parametrize("error_type", [TypeError, ValueError])
async def test_programming_errors_pass_through_without_retry(
    monkeypatch: pytest.MonkeyPatch,
    provider: claude_sdk.ClaudeSdkLLMProvider,
    error_type: type[Exception],
) -> None:
    from shared.adapters.llm.retrying import RetryingLLM

    from shared.tests.unit.llm.test_retrying_routing import no_sleep

    error = error_type("callback programming error")
    calls = 0

    async def failed(**_: Any) -> AsyncIterator[Any]:
        nonlocal calls
        calls += 1
        raise error
        yield  # pragma: no cover

    monkeypatch.setattr(claude_sdk, "query", failed)
    with pytest.raises(error_type) as info:
        await RetryingLLM(provider, sleep=no_sleep).text(task=LLMTask.FAST, system="s", user="u")
    assert info.value is error
    assert calls == 1


@pytest.mark.parametrize("kind", ["missing_cli", "malformed_message"])
async def test_sdk_configuration_and_parsing_errors_are_not_retried(
    monkeypatch: pytest.MonkeyPatch, provider: claude_sdk.ClaudeSdkLLMProvider, kind: str
) -> None:
    from shared.adapters.llm.retrying import RetryingLLM

    from shared.tests.unit.llm.test_retrying_routing import no_sleep

    error = (
        sdk.CLINotFoundError("CLI is not installed")
        if kind == "missing_cli"
        else sdk.CLIJSONDecodeError("not json", ValueError("malformed message"))
    )
    calls = 0

    async def failed(**_: Any) -> AsyncIterator[Any]:
        nonlocal calls
        calls += 1
        raise error
        yield  # pragma: no cover

    monkeypatch.setattr(claude_sdk, "query", failed)
    with pytest.raises(type(error)) as info:
        await RetryingLLM(provider, sleep=no_sleep).text(task=LLMTask.FAST, system="s", user="u")
    assert info.value is error
    assert calls == 1
