"""SkillClient over A2A JSON-RPC `message/send` (non-streaming)."""

from __future__ import annotations

from collections.abc import Mapping
from uuid import UUID, uuid4

import httpx
from a2a.types import DataPart, Task, TaskState, TextPart
from pydantic import ValidationError

from shared.ports.skills import SkillCallError, SkillReply, SkillUnavailable


class A2ASkillClient:
    def __init__(self, base_url: str, http: httpx.AsyncClient, *, timeout_s: float = 10.0) -> None:
        self._url = base_url.rstrip("/") + "/"
        self._http = http
        self._timeout = timeout_s

    async def call(
        self,
        *,
        skill_id: str,
        user_id: UUID,
        params: Mapping[str, object],
        text: str = "",
    ) -> SkillReply:
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
                    "metadata": {
                        "skillId": skill_id,
                        "user_id": str(user_id),
                        "params": dict(params),
                    },
                }
            },
        }
        try:
            response = await self._http.post(self._url, json=payload, timeout=self._timeout)
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise SkillUnavailable(type(exc).__name__) from exc
        task = body.get("result") if isinstance(body, Mapping) else None
        if not isinstance(task, Mapping):
            raise SkillUnavailable("no task in reply")
        try:
            result = Task.model_validate(task)
        except ValidationError as exc:
            raise SkillUnavailable("invalid task in reply") from exc
        if result.status.state == TaskState.failed:
            message = result.status.message
            texts = (
                [
                    part.root.text
                    for part in message.parts
                    if isinstance(part.root, TextPart) and part.root.text
                ]
                if message is not None
                else []
            )
            raise SkillCallError(texts[0] if texts else "failed")
        if result.status.state != TaskState.completed:
            raise SkillUnavailable("task did not complete")
        reply_text = ""
        data: Mapping[str, object] | None = None
        for artifact in result.artifacts or []:
            for part in artifact.parts:
                if artifact.name == "data" and isinstance(part.root, DataPart):
                    data = dict(part.root.data)
                elif artifact.name == "analysis" and isinstance(part.root, TextPart):
                    reply_text = part.root.text
        return SkillReply(text=reply_text, data=data)
