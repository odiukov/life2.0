"""LLM provider factory shared by orchestrator and all sub-agents.

Public surface: a single function `build_llm() -> BaseChatModel`.

Env vars:
    LLM_PROVIDER — one of: anthropic | openrouter | gemini | groq | ollama | claude-cli
                   (default: openrouter).
    LLM_MODEL    — optional override. Each provider has a default (see below).

Required key per provider:
    anthropic   — ANTHROPIC_API_KEY
    openrouter  — OPENROUTER_API_KEY
    gemini      — GEMINI_API_KEY
    groq        — GROQ_API_KEY
    ollama      — (none; OLLAMA_HOST optional, defaults to http://localhost:11434)
    claude-cli  — ANTHROPIC_API_KEY  (OAuth token from scripts/export-auth.sh)

Unknown provider → ValueError. Missing required key → ValueError.

Third-party extension: write your own BaseChatModel subclass per the LangChain
docs and instantiate it directly in application code — this factory covers
the shipped providers only.
"""
from __future__ import annotations

import os

import anthropic
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

from .chat_claude_cli import ChatClaudeCLI


_DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-4-6",
    "openrouter": "meta-llama/llama-3.3-70b-instruct:free",
    "gemini": "gemini-2.0-flash-exp",
    "groq": "llama-3.3-70b-versatile",
    "ollama": "llama3.1:8b",
    "claude-cli": "claude-sonnet-4-6",
}


def build_llm() -> BaseChatModel:
    provider = os.environ.get("LLM_PROVIDER", "openrouter").lower()
    if provider not in _DEFAULT_MODELS:
        raise ValueError(
            f"unknown provider: {provider!r}. Supported: {sorted(_DEFAULT_MODELS)}"
        )
    model = os.environ.get("LLM_MODEL") or _DEFAULT_MODELS[provider]

    if provider == "anthropic":
        return _build_anthropic(model)
    if provider == "openrouter":
        return _build_openrouter(model)
    if provider == "gemini":
        return _build_gemini(model)
    if provider == "groq":
        return _build_groq(model)
    if provider == "ollama":
        return _build_ollama(model)
    if provider == "claude-cli":
        return _build_claude_cli(model)
    raise ValueError(f"unknown provider: {provider!r}")


def _require(key: str) -> str:
    val = os.environ.get(key)
    if not val:
        raise ValueError(f"{key} not set")
    return val


def _build_anthropic(model: str) -> BaseChatModel:
    token = _require("ANTHROPIC_API_KEY")
    llm = ChatAnthropic(model=model, temperature=0, streaming=True)
    if token.startswith("sk-ant-oat"):
        headers = {"anthropic-beta": "oauth-2025-04-20"}
        llm.__dict__["_async_client"] = anthropic.AsyncAnthropic(
            api_key="", auth_token=token, default_headers=headers,
        )
        llm.__dict__["_client"] = anthropic.Anthropic(
            api_key="", auth_token=token, default_headers=headers,
        )
    return llm


def _build_openrouter(model: str) -> BaseChatModel:
    return ChatOpenAI(
        model=model,
        temperature=0,
        api_key=_require("OPENROUTER_API_KEY"),
        base_url="https://openrouter.ai/api/v1",
    )


def _build_gemini(model: str) -> BaseChatModel:
    return ChatGoogleGenerativeAI(
        model=model,
        temperature=0,
        google_api_key=_require("GEMINI_API_KEY"),
    )


def _build_groq(model: str) -> BaseChatModel:
    return ChatGroq(
        model=model,
        temperature=0,
        api_key=_require("GROQ_API_KEY"),
    )


def _build_ollama(model: str) -> BaseChatModel:
    host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    return ChatOllama(model=model, temperature=0, base_url=host)


def _build_claude_cli(model: str) -> BaseChatModel:
    _require("ANTHROPIC_API_KEY")
    return ChatClaudeCLI(model=model)
