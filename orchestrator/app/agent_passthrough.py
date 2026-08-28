"""Thin pass-through route: mobile slash tags hit `/agent/{name}/stream` to
talk to a single peer directly. The orchestrator's LangGraph router never sees
the message — we just relay text to the A2A peer and stream events back."""
from __future__ import annotations

import json
import uuid
from typing import AsyncIterator
from uuid import UUID

from a2a.types import DataPart, Message, Part, Role, TextPart
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from shared.a2a_clients import get_client

from .auth import current_user
from .registry import get_agent_url

router = APIRouter()


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


async def stream_peer_call(
    *, agent: str, message: str, user_id: str
) -> AsyncIterator[dict]:
    """Call the peer via A2A; yield normalized event dicts the route can wrap as SSE.

    Yields:
        {"type": "text", "delta": str}     for text chunks
        {"type": "consulted", "peers": [...]}  once, after the analysis artifact lands
    """
    url = get_agent_url(agent)
    if not url:
        raise HTTPException(status_code=404, detail=f"Agent '{agent}' not registered")
    client = await get_client(url)
    msg = Message(
        role=Role.user,
        parts=[Part(root=TextPart(text=message))],
        message_id=str(uuid.uuid4()),
        metadata={"user_id": user_id},
    )
    text_yielded = False
    async for resp in client.send_message(msg):
        # A2A SDK yields either a (Task, update) tuple or a Message.
        if isinstance(resp, tuple):
            task, _update = resp
            for art in task.artifacts or []:
                if art.name == "analysis" and not text_yielded:
                    for part in art.parts or []:
                        root = getattr(part, "root", part)
                        text = getattr(root, "text", None)
                        if text:
                            yield {"type": "text", "delta": text}
                            text_yielded = True
                if art.name == "consulted_peers":
                    for part in art.parts or []:
                        root = getattr(part, "root", part)
                        data = getattr(root, "data", None)
                        if isinstance(data, dict) and isinstance(data.get("peers"), list):
                            yield {"type": "consulted", "peers": data["peers"]}
        elif isinstance(resp, Message):
            for part in resp.parts or []:
                root = getattr(part, "root", part)
                text = getattr(root, "text", None)
                if text and not text_yielded:
                    yield {"type": "text", "delta": text}
                    text_yielded = True


@router.post("/agent/{name}/stream")
async def agent_stream(name: str, req: dict, user_id: UUID = Depends(current_user)):
    """Stream a single-agent response via SSE. `req` mirrors StreamChatRequest."""
    if get_agent_url(name) is None:
        raise HTTPException(status_code=404, detail=f"Agent '{name}' not registered")

    thread_id = req.get("threadId") or str(uuid.uuid4())
    run_id = req.get("runId") or str(uuid.uuid4())
    message_id = str(uuid.uuid4())

    user_messages = [m for m in (req.get("messages") or []) if m.get("role") == "user"]
    if not user_messages:
        raise HTTPException(status_code=400, detail="No user message found")
    text = user_messages[-1].get("content", "")

    async def event_stream():
        yield _sse({"type": "RunStarted", "threadId": thread_id, "runId": run_id})
        yield _sse({"type": "TextMessageStart", "messageId": message_id, "role": "assistant"})
        yield _sse({"type": "AgentRouted", "primary": name})
        try:
            async for ev in stream_peer_call(agent=name, message=text, user_id=str(user_id)):
                if ev["type"] == "text":
                    yield _sse({"type": "TextMessageContent", "messageId": message_id, "delta": ev["delta"]})
                elif ev["type"] == "consulted":
                    yield _sse({"type": "AgentConsulted", "peers": ev["peers"]})
        except Exception as e:  # noqa: BLE001 — surface as text frame, never break the stream
            yield _sse({
                "type": "TextMessageContent",
                "messageId": message_id,
                "delta": f"Error: {e}",
            })
        yield _sse({"type": "TextMessageEnd", "messageId": message_id})
        yield _sse({"type": "RunFinished", "threadId": thread_id, "runId": run_id})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
