"""Dispatches each LLMTask to the provider configured for it."""

from __future__ import annotations

from collections.abc import Mapping

from shared.ports.llm import LLMProvider, LLMTask, SchemaT


class RoutingLLM:
    def __init__(self, routes: Mapping[LLMTask, LLMProvider]) -> None:
        missing = [task.value for task in LLMTask if task not in routes]
        if missing:
            raise ValueError(f"no provider for tasks: {', '.join(missing)}")
        self._routes = dict(routes)

    async def structured(
        self, *, task: LLMTask, system: str, user: str, schema: type[SchemaT]
    ) -> SchemaT:
        return await self._routes[task].structured(
            task=task, system=system, user=user, schema=schema
        )

    async def text(self, *, task: LLMTask, system: str, user: str) -> str:
        return await self._routes[task].text(task=task, system=system, user=user)
