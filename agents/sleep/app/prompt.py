"""Sleep-agent analytical/recommendation prompt builder.

Composition (per spec §10):
  IDENTITY → DATA → VOCAB → PEER_CONTEXT → MEMORIES → REQUEST
  → PEER_CHIP_RULES (only with peer artifacts) → SKILL_TAIL → GROUNDING_RULES
"""
from __future__ import annotations

from uuid import UUID

from shared.db import fetch_recent_logs
from shared.grounding import GROUNDING_RULES
from shared.peer_chip_rules import PEER_CHIP_RULES
from shared.personas import IDENTITY, VOCAB
from shared.vector import search_memories


_SKILL_TAIL: dict[str, str] = {
    "analyze_sleep": (
        "Respond in 6–10 lines plain text: (1) the sleep observation grounded "
        "in the data, (2) one mechanism explaining it, (3) one sentence on "
        "expected impact for today. No markdown."
    ),
    # skills.py passes "get_recommendations" (bare task name), not the
    # AgentCard skill ID Sleep.RECOMMENDATIONS = "get_sleep_recommendations".
    "get_recommendations": (
        "Respond in 4–6 lines plain text: 2–3 concrete sleep-domain actions "
        "for tonight + a one-line 'why' tied to the data. Redirect "
        "cross-domain asks (meal timing → /nutrition, training timing → "
        "/workout). No markdown."
    ),
    "log_sleep": (
        "Confirm what was logged in 1–2 lines: include duration / deep / HRV "
        "if present in the message. No markdown."
    ),
}


async def build_sleep_prompt(
    task: str,
    params: dict,
    peer_artifacts: dict | None = None,
) -> str:
    user_id = UUID(params["user_id"])
    recent_logs = await fetch_recent_logs(user_id, "sleep", limit=10)
    memories = await search_memories(user_id, task, limit=5)

    logs_text = "\n".join(
        f"- {r['recorded_at'].date()} | {r['type']} | {r['data']}"
        for r in recent_logs
    ) or "No recent sleep logs."

    memories_text = "\n".join(
        f"- {m.get('text', '')}" for m in memories
    ) or "No relevant memories."

    peer = peer_artifacts if peer_artifacts is not None else (params.get("peer_artifacts") or {})
    peer_section = ""
    if peer:
        chunks = []
        for name in ("workout", "nutrition", "recovery", "mood", "medication"):
            text = peer.get(name)
            if text and text.strip() and text != "(данные недоступны)":
                chunks.append(f"### {name}\n{text}")
        if chunks:
            peer_section = "\n## Peer context\n" + "\n\n".join(chunks)

    chip_block = f"\n{PEER_CHIP_RULES}" if peer_section else ""
    skill_tail = _SKILL_TAIL.get(task, "")

    return (
        f"{IDENTITY['sleep']}\n\n"
        f"## Recent sleep logs (last 10 entries)\n{logs_text}\n"
        f"{peer_section}\n\n"
        f"## Vocabulary you may invoke (only when grounded by data)\n"
        f"{VOCAB['sleep']}\n\n"
        f"## Memories\n{memories_text}\n\n"
        f"## User request\n"
        f"Task: {task}\n"
        f"Params: {params}\n"
        f"{chip_block}\n"
        f"{skill_tail}\n\n"
        f"{GROUNDING_RULES}"
    )
