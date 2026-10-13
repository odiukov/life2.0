"""Factory for tool-calling LangChain chat models (used by ReAct graphs)."""

from __future__ import annotations

from typing import Protocol

from langchain_core.language_models import BaseChatModel

from shared.ports.llm import LLMTask


class ChatModelFactory(Protocol):
    def chat_model(self, task: LLMTask) -> BaseChatModel: ...
