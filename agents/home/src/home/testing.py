from __future__ import annotations

import asyncio
from collections.abc import Mapping

from shared.ports.household_credentials import HouseholdConnection

from home.application.ports import AgentOutcome, HomeUnavailable, InvalidToken, ToolRejected
from home.domain.actions import ToolCall


class FakeHomeAssistant:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.down = False
        self.reject = False

    async def ping(self, base_url: str, token: str) -> str | None:
        if self.down:
            raise HomeUnavailable
        if token == "wrong":
            raise InvalidToken
        return "2026.10.1"

    async def call_tool(
        self, conn: HouseholdConnection, tool: str, args: Mapping[str, object]
    ) -> None:
        if self.down:
            raise HomeUnavailable
        if self.reject:
            raise ToolRejected
        self.calls.append((tool, dict(args)))


class FakeHomeAgent:
    def __init__(
        self, text: str = "Ready.", proposal: ToolCall | None = None, *, hang: bool = False
    ) -> None:
        self.outcome = AgentOutcome(text, proposal)
        self.hang = hang
        self.questions: list[str] = []

    async def run(self, question: str, conn: HouseholdConnection, locale: str) -> AgentOutcome:
        self.questions.append(question)
        if self.hang:
            await asyncio.sleep(3600)
        return self.outcome
