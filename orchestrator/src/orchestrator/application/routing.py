"""Which agent a reply is attributed to (AgentRouted) and who else contributed (AgentConsulted).

The legacy rule: the last agent the chat called is the primary; the other agents it called, then
the peers those agents consulted themselves, are "consulted" — primary excluded, first seen first.
"""

from __future__ import annotations

from orchestrator.application.ports import ToolDone
from orchestrator.domain.catalog import CATALOG


class Routing:
    def __init__(self) -> None:
        self._observed: list[str] = []
        self._inner: list[str] = []
        self._primary = "main"

    def observe(self, event: ToolDone) -> None:
        if event.agent not in CATALOG:
            return
        self._primary = event.agent
        if event.agent not in self._observed:
            self._observed.append(event.agent)
        for peer in event.consulted:
            if peer and peer not in self._inner:
                self._inner.append(peer)

    @property
    def primary(self) -> str:
        return self._primary

    @property
    def consulted(self) -> list[str]:
        merged: list[str] = []
        for name in (*self._observed, *self._inner):
            if name != self.primary and name not in merged:
                merged.append(name)
        return merged
