"""The SSE events of a chat run (AG-UI shaped, as the app already parses them)."""

from __future__ import annotations

import json
from typing import Any

Event = dict[str, Any]


def sse(event: Event) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def run_started(task_id: str, run_id: str) -> Event:
    return {"type": "RunStarted", "threadId": task_id, "runId": run_id}


def text_start(message_id: str) -> Event:
    return {"type": "TextMessageStart", "messageId": message_id, "role": "assistant"}


def text_delta(message_id: str, delta: str) -> Event:
    return {"type": "TextMessageContent", "messageId": message_id, "delta": delta}


def text_end(message_id: str) -> Event:
    return {"type": "TextMessageEnd", "messageId": message_id}


def run_finished(task_id: str, run_id: str) -> Event:
    return {"type": "RunFinished", "threadId": task_id, "runId": run_id}


def agent_routed(primary: str) -> Event:
    return {"type": "AgentRouted", "primary": primary}


def agent_consulted(peers: list[str]) -> Event:
    return {"type": "AgentConsulted", "peers": peers}


def action_proposed(action_id: str, summary: str, expires_at: str) -> Event:
    return {
        "type": "ActionProposed",
        "actionId": action_id,
        "summary": summary,
        "expiresAt": expires_at,
    }


def action_resolved(action_id: str, status: str, message: str) -> Event:
    return {"type": "ActionResolved", "actionId": action_id, "status": status, "message": message}


def run_error(code: str, message: str) -> Event:
    return {"type": "RunError", "code": code, "message": message}
