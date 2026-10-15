"""Conversational agent calls over A2A message/send: text, consulted peers and structured data."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID, uuid4

import httpx
from a2a.types import DataPart, Task, TaskState, TextPart

from orchestrator.application.ports import PeerReply, PeerUnavailable


class A2APeerAgents:
    def __init__(
        self, urls: Mapping[str, str], http: httpx.AsyncClient, *, timeout_s: float
    ) -> None:
        self._urls = {name: url.rstrip("/") + "/" for name, url in urls.items()}
        self._http, self._timeout = http, timeout_s

    async def ask(
        self,
        agent: str,
        *,
        user_id: UUID,
        skill: str,
        text: str,
        focus_sources: Sequence[str] | None,
    ) -> PeerReply:
        metadata: dict[str, Any] = {"skillId": skill, "user_id": str(user_id)}
        if focus_sources:
            metadata["focus_sources"] = list(focus_sources)
        payload = {
            "jsonrpc": "2.0",
            "id": str(uuid4()),
            "method": "message/send",
            "params": {
                "message": {
                    "kind": "message",
                    "role": "user",
                    "messageId": str(uuid4()),
                    "parts": [{"kind": "text", "text": text}],
                    "metadata": metadata,
                }
            },
        }
        try:
            response = await self._http.post(self._urls[agent], json=payload, timeout=self._timeout)
            response.raise_for_status()
            body = response.json()
            if not isinstance(body, dict):
                raise ValueError("invalid_response")
            task = Task.model_validate(body["result"])
        except (httpx.HTTPError, KeyError, ValueError):
            raise PeerUnavailable(agent) from None
        if task.status.state not in (TaskState.completed, TaskState.failed):
            raise PeerUnavailable(agent)
        texts: list[str] = []
        consulted: list[str] = []
        data: dict[str, Any] | None = None
        for artifact in task.artifacts or []:
            for part in artifact.parts:
                root = part.root
                if artifact.name == "analysis" and isinstance(root, TextPart):
                    texts.append(root.text)
                elif artifact.name == "consulted_peers" and isinstance(root, DataPart):
                    peers = root.data.get("peers")
                    if isinstance(peers, list):
                        consulted.extend(p for p in peers if isinstance(p, str) and p)
                elif artifact.name == "data" and isinstance(root, DataPart):
                    data = {**(data or {}), **root.data}
        failed = task.status.state == TaskState.failed
        if not texts and failed and task.status.message:
            texts = [p.root.text for p in task.status.message.parts if isinstance(p.root, TextPart)]
        return PeerReply("".join(texts), tuple(dict.fromkeys(consulted)), data, failed)
