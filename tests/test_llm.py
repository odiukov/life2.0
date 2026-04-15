"""Unit tests for shared.llm.build_llm — pure env-driven, no network."""
from __future__ import annotations

import pytest
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

from shared.chat_claude_cli import ChatClaudeCLI
from shared.llm import build_llm


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    for k in ("LLM_PROVIDER", "LLM_MODEL", "ANTHROPIC_API_KEY",
              "OPENROUTER_API_KEY", "GEMINI_API_KEY", "OLLAMA_HOST"):
        monkeypatch.delenv(k, raising=False)


def test_default_provider_is_openrouter(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    llm = build_llm()
    assert isinstance(llm, ChatOpenAI)
    assert str(llm.openai_api_base).rstrip("/") == "https://openrouter.ai/api/v1"
    assert llm.model_name == "meta-llama/llama-3.3-70b-instruct:free"


def test_anthropic_branch(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-k")
    llm = build_llm()
    assert isinstance(llm, ChatAnthropic)
    assert llm.model == "claude-sonnet-4-6"


def test_anthropic_oauth_token_injects_manual_client(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-oat-xyz")
    llm = build_llm()
    assert "_async_client" in llm.__dict__
    assert "_client" in llm.__dict__


def test_openrouter_explicit_branch(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    llm = build_llm()
    assert isinstance(llm, ChatOpenAI)
    assert str(llm.openai_api_base).rstrip("/") == "https://openrouter.ai/api/v1"


def test_gemini_branch(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    llm = build_llm()
    assert isinstance(llm, ChatGoogleGenerativeAI)
    assert llm.model.endswith("gemini-2.0-flash-exp")


def test_ollama_branch(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    llm = build_llm()
    assert isinstance(llm, ChatOllama)
    assert llm.model == "llama3.1:8b"


def test_claude_cli_branch(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "claude-cli")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-oat-xyz")
    llm = build_llm()
    assert isinstance(llm, ChatClaudeCLI)
    assert llm.model == "claude-sonnet-4-6"


def test_llm_model_override(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("LLM_MODEL", "custom/model-x")
    llm = build_llm()
    assert llm.model == "custom/model-x"


def test_unknown_provider_raises(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "bogus")
    with pytest.raises(ValueError, match="unknown provider"):
        build_llm()


@pytest.mark.parametrize(
    "provider,key",
    [
        ("anthropic", "ANTHROPIC_API_KEY"),
        ("openrouter", "OPENROUTER_API_KEY"),
        ("gemini", "GEMINI_API_KEY"),
        ("claude-cli", "ANTHROPIC_API_KEY"),
    ],
)
def test_missing_api_key_raises(monkeypatch, provider, key):
    monkeypatch.setenv("LLM_PROVIDER", provider)
    monkeypatch.delenv(key, raising=False)
    with pytest.raises(ValueError, match=key):
        build_llm()
