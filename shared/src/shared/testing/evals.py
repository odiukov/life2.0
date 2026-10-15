"""Real-provider eval helper: skip cleanly when no real model is configured."""

from __future__ import annotations

import pytest

from shared.adapters.chat_model.factory import LangChainChatModelFactory
from shared.adapters.llm.build import build_llm_provider
from shared.config import BaseServiceSettings
from shared.ports.chat_model import ChatModelFactory
from shared.ports.llm import LLMProvider, LLMTask

KEYS = {
    "anthropic": "anthropic_api_key",
    "openrouter": "openrouter_api_key",
    "gemini": "gemini_api_key",
    "groq": "groq_api_key",
}


def _skip_without_real_model(settings: BaseServiceSettings, task: LLMTask) -> None:
    provider = settings.llm.route(task).provider
    if provider == "fake":
        pytest.skip("evals do not run against the fake provider")
    key = KEYS.get(provider)
    if key is not None:
        secret = getattr(settings, key)
        value = secret.get_secret_value().strip() if secret is not None else ""
        if not value or value == "test-placeholder":
            pytest.skip(f"{key.upper()} needs a real key; absent or test-placeholder")


def real_llm_or_skip(settings: BaseServiceSettings, task: LLMTask = LLMTask.FAST) -> LLMProvider:
    _skip_without_real_model(settings, task)
    return build_llm_provider(settings)


def real_chat_models_or_skip(
    settings: BaseServiceSettings, task: LLMTask = LLMTask.SMART
) -> ChatModelFactory:
    _skip_without_real_model(settings, task)
    return LangChainChatModelFactory(settings)
