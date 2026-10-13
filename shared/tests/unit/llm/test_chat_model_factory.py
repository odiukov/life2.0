import pytest
from langchain_ollama import ChatOllama
from shared.adapters.chat_model.factory import LangChainChatModelFactory
from shared.adapters.llm.build import build_llm_provider
from shared.adapters.llm.retrying import RetryingLLM
from shared.config import BaseServiceSettings
from shared.ports.llm import LLMTask


def settings(**overrides: object) -> BaseServiceSettings:
    base: dict[str, object] = {
        "database": {"dsn": "postgresql://u:p@h/d"},
        "anthropic_api_key": None,
        "openrouter_api_key": None,
        "gemini_api_key": None,
        "groq_api_key": None,
    }
    return BaseServiceSettings.model_validate({**base, **overrides})


def test_ollama_uses_configured_host_and_is_cached() -> None:
    factory = LangChainChatModelFactory(
        settings(llm={"default": "ollama:llama3.1:8b"}, ollama_host="http://ollama:11434")
    )
    model = factory.chat_model(LLMTask.FAST)
    assert isinstance(model, ChatOllama)
    assert model.base_url == "http://ollama:11434"
    assert factory.chat_model(LLMTask.SMART) is model


def test_missing_api_key_names_the_variable() -> None:
    factory = LangChainChatModelFactory(settings(llm={"default": "openrouter:some/model"}))
    with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
        factory.chat_model(LLMTask.FAST)


def test_subscription_token_requires_explicit_opt_in() -> None:
    factory = LangChainChatModelFactory(
        settings(llm={"default": "anthropic:claude-sonnet-5-5"}, anthropic_api_key="sk-ant-oat01-x")
    )
    with pytest.raises(ValueError, match="LLM__ANTHROPIC_AUTH=oauth_token"):
        factory.chat_model(LLMTask.FAST)


def test_opted_in_subscription_token_builds() -> None:
    factory = LangChainChatModelFactory(
        settings(
            llm={"default": "anthropic:claude-sonnet-5-5", "anthropic_auth": "oauth_token"},
            anthropic_api_key="sk-ant-oat01-x",
        )
    )
    assert factory.chat_model(LLMTask.FAST) is not None


def test_claude_sdk_cannot_back_a_chat_model() -> None:
    factory = LangChainChatModelFactory(settings(llm={"default": "claude_sdk:claude-sonnet-5-5"}))
    with pytest.raises(ValueError, match="claude_sdk"):
        factory.chat_model(LLMTask.FAST)


def test_build_llm_provider_wraps_in_retries() -> None:
    llm = build_llm_provider(settings(llm={"default": "ollama:llama3.1:8b"}))
    assert isinstance(llm, RetryingLLM)


async def test_build_routes_sdk_and_langchain(monkeypatch: pytest.MonkeyPatch) -> None:
    from langchain_core.messages import AIMessage
    from shared.adapters.llm import claude_sdk

    from shared.tests.unit.llm.test_claude_sdk import fake_query, result

    monkeypatch.setattr(claude_sdk, "query", fake_query(result(result="sdk-answer")))

    async def invoke(*args: object, **kwargs: object) -> AIMessage:
        return AIMessage("local-answer")

    monkeypatch.setattr(ChatOllama, "ainvoke", invoke)
    llm = build_llm_provider(
        settings(
            llm={
                "default": "ollama:local",
                "tasks": {"smart": "claude_sdk:claude-opus-5-5"},
            }
        )
    )
    assert await llm.text(task=LLMTask.SMART, system="s", user="u") == "sdk-answer"
    assert await llm.text(task=LLMTask.FAST, system="s", user="u") == "local-answer"
    assert await llm.text(task=LLMTask.MOOD_COACH, system="s", user="u") == "local-answer"


def test_task_overrides_are_cached_separately() -> None:
    factory = LangChainChatModelFactory(
        settings(llm={"default": "ollama:fast", "tasks": {"smart": "ollama:smart"}})
    )
    fast = factory.chat_model(LLMTask.FAST)
    smart = factory.chat_model(LLMTask.SMART)
    assert isinstance(smart, ChatOllama)
    assert smart.model == "smart"
    assert fast is not smart
    assert factory.chat_model(LLMTask.SMART) is smart


@pytest.mark.parametrize("provider", ["groq", "gemini"])
def test_factory_owns_provider_retry_and_timeout_policy(provider: str) -> None:
    from langchain_google_genai import ChatGoogleGenerativeAI
    from langchain_groq import ChatGroq

    factory = LangChainChatModelFactory(
        settings(
            llm={"default": f"{provider}:model", "timeout_s": 12},
            groq_api_key="test-placeholder",
            gemini_api_key="test-placeholder",
        )
    )
    model = factory.chat_model(LLMTask.FAST)
    if isinstance(model, ChatGroq):
        assert model.max_retries == 0
        assert model.request_timeout == 12
    else:
        assert isinstance(model, ChatGoogleGenerativeAI)
        assert model.max_retries == 0
        assert model.timeout == 12


@pytest.mark.parametrize("auth", ["api_key", "oauth_token"])
def test_anthropic_clients_use_outer_retry_policy(auth: str) -> None:
    from langchain_anthropic import ChatAnthropic

    factory = LangChainChatModelFactory(
        settings(
            llm={"default": "anthropic:model", "anthropic_auth": auth, "timeout_s": 12},
            anthropic_api_key="sk-ant-oat01-placeholder"
            if auth == "oauth_token"
            else "test-placeholder",
        )
    )
    model = factory.chat_model(LLMTask.FAST)
    assert isinstance(model, ChatAnthropic)
    assert model._client.max_retries == 0
    assert model._async_client.max_retries == 0
    assert model._client.timeout == 12
    assert model._async_client.timeout == 12
