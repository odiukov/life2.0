from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from shared.ports.household_credentials import HouseholdConnection

from home.domain.actions import ToolCall

SERVICE = "ha"


class HomeUnavailable(Exception):
    """Home Assistant could not be reached in time (network, timeout, MCP error)."""


class InvalidToken(Exception):
    """Home Assistant rejected the token (401)."""


class ToolRejected(Exception):
    """Home Assistant answered the tool call with an error."""


@dataclass(frozen=True, slots=True)
class AgentOutcome:
    text: str
    proposal: ToolCall | None


class HomeAssistant(Protocol):
    async def ping(self, base_url: str, token: str) -> str | None:
        """HA version; raises InvalidToken or HomeUnavailable."""
        ...

    async def call_tool(
        self, conn: HouseholdConnection, tool: str, args: Mapping[str, object]
    ) -> None:
        """Raises HomeUnavailable or ToolRejected."""
        ...


class HomeAgent(Protocol):
    async def run(self, question: str, conn: HouseholdConnection, locale: str) -> AgentOutcome:
        """Answer with the household's tools; mutating calls are captured, not run. Raises HomeUnavailable."""
        ...
