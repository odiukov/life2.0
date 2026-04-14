# orchestrator/app/llm.py
"""LLM provider factory for the health agent.

Reads env vars at call time and returns a configured chat model:

- LLM_PROVIDER: "anthropic" (default) or "openrouter".
- LLM_MODEL: optional override. Defaults per provider below.
- ANTHROPIC_API_KEY / OPENROUTER_API_KEY: required for the selected provider.
"""
import os

import anthropic
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI


_DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-4-6",
    "openrouter": "openrouter/elephant-alpha",
}


def build_llm() -> BaseChatModel:
    provider = os.environ.get("LLM_PROVIDER", "anthropic").lower()
    if provider not in _DEFAULT_MODELS:
        raise ValueError(
            f"Unknown LLM_PROVIDER={provider!r}. "
            f"Supported: {sorted(_DEFAULT_MODELS)}"
        )

    model = os.environ.get("LLM_MODEL") or _DEFAULT_MODELS[provider]

    if provider == "openrouter":
        return ChatOpenAI(
            model=model,
            temperature=0,
            api_key=os.environ["OPENROUTER_API_KEY"],
            base_url="https://openrouter.ai/api/v1",
        )

    # provider == "anthropic"
    # OAuth tokens (sk-ant-oat*) must be sent as Authorization: Bearer with
    # the anthropic-beta: oauth-2025-04-20 header. Inject a manually-built
    # SDK client into ChatAnthropic's cached client slots so LangChain uses it.
    token = os.environ.get("ANTHROPIC_API_KEY", "")
    is_oauth = token.startswith("sk-ant-oat")
    llm = ChatAnthropic(model=model, temperature=0)
    if is_oauth:
        headers = {"anthropic-beta": "oauth-2025-04-20"}
        llm.__dict__["_async_client"] = anthropic.AsyncAnthropic(
            api_key="", auth_token=token, default_headers=headers,
        )
        llm.__dict__["_client"] = anthropic.Anthropic(
            api_key="", auth_token=token, default_headers=headers,
        )
    return llm
