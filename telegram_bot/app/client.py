import json
import os

import httpx

ORCHESTRATOR_URL = os.environ.get("ORCHESTRATOR_URL", "http://orchestrator:8000")
SYNC_SERVICE_URL = os.environ.get("SYNC_SERVICE_URL", "http://sync-service:8080")


async def ask_orchestrator(message: str, thread_id: str) -> str:
    """POST message to orchestrator /chat/stream, accumulate text deltas, return final string."""
    parts: list[str] = []
    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            async with client.stream(
                "POST",
                f"{ORCHESTRATOR_URL}/chat/stream",
                json={
                    "threadId": thread_id,
                    "messages": [{"role": "user", "content": message}],
                },
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    try:
                        event = json.loads(line[6:])
                    except json.JSONDecodeError:
                        continue
                    if event.get("type") == "TextMessageContent":
                        parts.append(event.get("delta", ""))
    except httpx.RequestError as e:
        return f"Orchestrator unavailable: {e}"
    except httpx.HTTPStatusError as e:
        return f"Orchestrator error {e.response.status_code}: {e.response.text[:200]}"

    return "".join(parts) or "(empty response)"


async def trigger_full_sync() -> str:
    """Kick off the full daily pipeline (Garmin + Yazio + briefing) manually."""
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            resp = await client.post(f"{SYNC_SERVICE_URL}/sync/all")
            resp.raise_for_status()
            data = resp.json()
    except httpx.RequestError as e:
        return f"Sync service unavailable: {e}"
    except httpx.HTTPStatusError as e:
        return f"Sync error {e.response.status_code}: {e.response.text[:200]}"

    lines = ["✅ Sync complete"]
    garmin = data.get("garmin") or {}
    yazio = data.get("yazio") or {}
    if garmin:
        lines.append(
            f"• Garmin: +{garmin.get('synced', 0)} new, {garmin.get('skipped', 0)} dup"
        )
    if yazio:
        lines.append(
            f"• Yazio: +{yazio.get('synced', 0)} new, {yazio.get('skipped', 0)} dup"
        )
    errors = list(data.get("errors") or []) + list(garmin.get("errors") or []) + list(yazio.get("errors") or [])
    if errors:
        lines.append("⚠️ " + "; ".join(errors[:3]))
    lines.append("📨 Briefing queued…")
    return "\n".join(lines)


async def sync_body_pdf(payload: dict) -> str:
    """POST extracted body composition payload to sync service, return human-readable result."""
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{SYNC_SERVICE_URL}/sync/body",
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.RequestError as e:
        return f"Sync service unavailable: {e}"
    except httpx.HTTPStatusError as e:
        return f"Sync service error {e.response.status_code}: {e.response.text[:200]}"

    errors = data.get("errors", [])
    synced = data.get("synced", 0)
    skipped = data.get("skipped", 0)

    if errors:
        return f"Error importing body data: {', '.join(errors)}"
    if synced == 0 and skipped > 0:
        return "Body composition data already up to date (no new measurements)."
    return f"Saved {synced} body composition measurement(s) from ViHealth report."


HABITS_AGENT_URL = os.environ.get("HABITS_AGENT_URL", "http://agent-habits:8006/")


async def habits_a2a_call(skill: str, message: str, params: dict | None = None) -> str:
    """Invoke a habits-agent skill directly via A2A JSON-RPC. Returns text artifact content."""
    import uuid as _uuid
    from a2a.types import Message, Part, Role, TextPart
    from shared.a2a_clients import get_client

    client = await get_client(HABITS_AGENT_URL)
    meta: dict = {"skillId": skill}
    if params:
        meta["params"] = params
    msg = Message(
        role=Role.user,
        parts=[Part(root=TextPart(text=message))],
        message_id=str(_uuid.uuid4()),
        metadata=meta,
    )
    out = ""
    async for resp in client.send_message(msg):
        if isinstance(resp, tuple):
            task, _ = resp
            for art in task.artifacts or []:
                if art.name != "analysis":
                    continue
                for p in art.parts or []:
                    root = getattr(p, "root", p)
                    text = getattr(root, "text", None)
                    if text:
                        out = text
    return out
