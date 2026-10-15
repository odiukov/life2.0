from __future__ import annotations

from collections.abc import Mapping

import httpx
from shared.adapters.a2a.skill_client import A2ASkillClient
from shared.ports.skills import SkillClient


class AgentClients:
    def __init__(
        self,
        urls: Mapping[str, str],
        http: httpx.AsyncClient,
        *,
        timeout_s: float,
        timeouts: Mapping[str, float] | None = None,
    ) -> None:
        overrides = timeouts or {}
        self._clients = {
            name: A2ASkillClient(url, http, timeout_s=overrides.get(name, timeout_s))
            for name, url in urls.items()
        }

    def client(self, agent: str) -> SkillClient:
        return self._clients[agent]
