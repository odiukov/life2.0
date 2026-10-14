"""Real-provider eval helper: skip cleanly when no real model is configured."""

from __future__ import annotations

import pytest

from shared.adapters.llm.build import build_llm_provider
from shared.config import BaseServiceSettings
from shared.ports.llm import LLMProvider, LLMTask

KEYS = {
    "anthropic": "anthropic_api_key",
    "openrouter": "openrouter_api_key",
    "gemini": "gemini_api_key",
    "groq": "groq_api_key",
}


def real_llm_or_skip(settings: BaseServiceSettings, task: LLMTask = LLMTask.FAST) -> LLMProvider:
    provider = settings.llm.route(task).provider
    if provider == "fake":
        pytest.skip("evals do not run against the fake provider")
    key = KEYS.get(provider)
    if key is not None:
        secret = getattr(settings, key)
        value = secret.get_secret_value().strip() if secret is not None else ""
        if not value or value == "test-placeholder":
            pytest.skip(f"{key.upper()} needs a real key; absent or test-placeholder")
    return build_llm_provider(settings)
