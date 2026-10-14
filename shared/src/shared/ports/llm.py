"""LLM ports: one-shot structured/text calls."""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol, TypeVar

from pydantic import BaseModel

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class LLMTask(StrEnum):
    FAST = "fast"
    SMART = "smart"
    MOOD_COACH = "mood_coach"
    KITCHEN_EXTRACT = "kitchen_extract"
    KITCHEN_QUERY = "kitchen_query"


class LLMError(Exception):
    """Base class for LLM port errors."""


class LLMUnavailable(LLMError):
    """The provider could not be reached, timed out, or failed transiently."""


class LLMInvalidOutput(LLMError):
    """The provider answered, but the answer does not satisfy the requested schema."""

    def __init__(self, raw: str, reason: str) -> None:
        super().__init__(reason)
        self.raw = raw
        self.reason = reason


class LLMProvider(Protocol):
    async def structured(
        self, *, task: LLMTask, system: str, user: str, schema: type[SchemaT]
    ) -> SchemaT: ...

    async def text(self, *, task: LLMTask, system: str, user: str) -> str: ...
