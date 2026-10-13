"""Decorator that retries transient LLM failures with exponential backoff."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from shared.ports.llm import LLMProvider, LLMTask, LLMUnavailable, SchemaT

ResultT = TypeVar("ResultT")


class RetryingLLM:
    def __init__(
        self,
        inner: LLMProvider,
        *,
        attempts: int = 3,
        backoff_s: float = 1.0,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if attempts < 1:
            raise ValueError("attempts must be at least 1")
        self._inner = inner
        self._attempts = attempts
        self._backoff_s = backoff_s
        self._sleep = sleep

    async def structured(
        self, *, task: LLMTask, system: str, user: str, schema: type[SchemaT]
    ) -> SchemaT:
        return await self._retry(
            lambda: self._inner.structured(task=task, system=system, user=user, schema=schema)
        )

    async def text(self, *, task: LLMTask, system: str, user: str) -> str:
        return await self._retry(lambda: self._inner.text(task=task, system=system, user=user))

    async def _retry(self, call: Callable[[], Awaitable[ResultT]]) -> ResultT:
        for attempt in range(self._attempts):
            try:
                return await call()
            except LLMUnavailable:
                if attempt == self._attempts - 1:
                    raise
                await self._sleep(self._backoff_s * 2**attempt)
        raise AssertionError("unreachable")
