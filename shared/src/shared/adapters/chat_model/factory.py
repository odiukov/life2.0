"""LangChain chat models per task route, built from typed settings."""

from __future__ import annotations

import anthropic
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

from shared.config import BaseServiceSettings, LLMRoute
from shared.ports.llm import LLMTask

_OAUTH_PREFIX = "sk-ant-oat"
_OAUTH_HEADERS = {"anthropic-beta": "oauth-2025-04-20"}


class LangChainChatModelFactory:
    def __init__(self, settings: BaseServiceSettings) -> None:
        self._settings = settings
        self._cache: dict[str, BaseChatModel] = {}

    def chat_model(self, task: LLMTask) -> BaseChatModel:
        route = self._settings.llm.route(task)
        key = str(route)
        if key not in self._cache:
            self._cache[key] = self._build(route)
        return self._cache[key]

    def _build(self, route: LLMRoute) -> BaseChatModel:
        timeout = self._settings.llm.timeout_s
        match route.provider:
            case "anthropic":
                return self._anthropic(route.model)
            case "openrouter":
                return ChatOpenAI(
                    model=route.model,
                    temperature=0,
                    api_key=self._secret("openrouter_api_key"),
                    base_url="https://openrouter.ai/api/v1",
                    timeout=timeout,
                    max_retries=0,
                )
            case "gemini":
                return ChatGoogleGenerativeAI(
                    model=route.model,
                    temperature=0,
                    google_api_key=self._secret("gemini_api_key"),
                    retries=0,
                    request_timeout=timeout,
                )
            case "groq":
                return ChatGroq(
                    model_name=route.model,
                    temperature=0,
                    api_key=self._secret("groq_api_key"),
                    max_retries=0,
                    timeout=timeout,
                )
            case "ollama":
                return ChatOllama(
                    model=route.model, temperature=0, base_url=self._settings.ollama_host
                )
            case "claude_sdk" | "fake":
                raise ValueError(f"{route.provider} cannot back a tool-calling chat model")

    def _secret(self, field: str) -> str:
        value = getattr(self._settings, field)
        if value is None:
            raise ValueError(f"{field.upper()} is not set")
        return str(value.get_secret_value())

    def _anthropic(self, model: str) -> BaseChatModel:
        token = self._secret("anthropic_api_key")
        oauth = token.startswith(_OAUTH_PREFIX)
        if oauth and self._settings.llm.anthropic_auth != "oauth_token":
            raise ValueError(
                "ANTHROPIC_API_KEY holds a Claude subscription OAuth token; set "
                "LLM__ANTHROPIC_AUTH=oauth_token to opt in (outside Anthropic's API terms)"
            )
        llm = ChatAnthropic(
            model=model,
            temperature=0,
            api_key=token,
            timeout=self._settings.llm.timeout_s,
            max_retries=0,
            max_tokens=4096,
        )
        if oauth:
            llm.__dict__["_async_client"] = anthropic.AsyncAnthropic(
                api_key="",
                auth_token=token,
                default_headers=_OAUTH_HEADERS,
                max_retries=0,
                timeout=self._settings.llm.timeout_s,
            )
            llm.__dict__["_client"] = anthropic.Anthropic(
                api_key="",
                auth_token=token,
                default_headers=_OAUTH_HEADERS,
                max_retries=0,
                timeout=self._settings.llm.timeout_s,
            )
        return llm
