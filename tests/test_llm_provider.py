import os

import pytest
from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI

from orchestrator.app.llm import build_llm


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    for key in ("LLM_PROVIDER", "LLM_MODEL", "ANTHROPIC_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(key, raising=False)


def test_default_provider_is_anthropic(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-api03-plainkey")
    llm = build_llm()
    assert isinstance(llm, ChatAnthropic)
    assert llm.model == "claude-sonnet-4-6"


def test_anthropic_oauth_token_injects_client(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-oat01-testtoken")
    llm = build_llm()
    assert isinstance(llm, ChatAnthropic)
    async_client = llm.__dict__["_async_client"]
    assert async_client.auth_token == "sk-ant-oat01-testtoken"
    assert async_client.default_headers.get("anthropic-beta") == "oauth-2025-04-20"


def test_anthropic_respects_llm_model_override(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-api03-x")
    monkeypatch.setenv("LLM_MODEL", "claude-haiku-4-5-20251001")
    llm = build_llm()
    assert isinstance(llm, ChatAnthropic)
    assert llm.model == "claude-haiku-4-5-20251001"


def test_openrouter_returns_chatopenai_with_base_url(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    llm = build_llm()
    assert isinstance(llm, ChatOpenAI)
    assert llm.model_name == "openrouter/elephant-alpha"
    assert str(llm.openai_api_base) == "https://openrouter.ai/api/v1"


def test_openrouter_respects_llm_model_override(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    monkeypatch.setenv("LLM_MODEL", "deepseek/deepseek-chat-v3.1:free")
    llm = build_llm()
    assert llm.model_name == "deepseek/deepseek-chat-v3.1:free"


def test_openrouter_missing_key_raises(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    with pytest.raises(KeyError):
        build_llm()


def test_unknown_provider_raises(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    with pytest.raises(ValueError, match="Unknown LLM_PROVIDER"):
        build_llm()
