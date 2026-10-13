"""Builds the LLMProvider a service uses from its settings."""

from __future__ import annotations

from shared.adapters.chat_model.factory import LangChainChatModelFactory
from shared.adapters.llm.langchain_provider import LangChainLLMProvider
from shared.adapters.llm.retrying import RetryingLLM
from shared.adapters.llm.routing import RoutingLLM
from shared.config import BaseServiceSettings
from shared.ports.llm import LLMProvider, LLMTask


def build_llm_provider(settings: BaseServiceSettings) -> LLMProvider:
    timeout_s = settings.llm.timeout_s
    langchain = LangChainLLMProvider(LangChainChatModelFactory(settings), timeout_s=timeout_s)
    sdk_models = {
        task: settings.llm.route(task).model
        for task in LLMTask
        if settings.llm.route(task).provider == "claude_sdk"
    }
    routes: dict[LLMTask, LLMProvider] = dict.fromkeys(LLMTask, langchain)
    if sdk_models:
        from shared.adapters.llm.claude_sdk import ClaudeSdkLLMProvider  # optional extra

        sdk = ClaudeSdkLLMProvider(models=sdk_models, timeout_s=timeout_s)
        routes.update(dict.fromkeys(sdk_models, sdk))
    return RetryingLLM(RoutingLLM(routes), attempts=settings.llm.retry_attempts)
