"""Workout-agent analytical/recommendation prompt builder.

Composition (per spec §10):
  IDENTITY → DATA → PEER_CONTEXT → VOCAB → MEMORIES → REQUEST
  → PEER_CHIP_RULES (only with peer artifacts) → SKILL_TAIL → GROUNDING_RULES
"""
from __future__ import annotations

from uuid import UUID

from shared.db import fetch_recent_logs, fetch_body_logs
from shared.grounding import GROUNDING_RULES
from shared.peer_chip_rules import PEER_CHIP_RULES
from shared.personas import IDENTITY, VOCAB
from shared.vector import search_memories


# Note: skills.py calls build_workout_prompt("get_recommendations", ...) — the
# bare task name internally. The AgentCard skill ID is
# Workout.RECOMMENDATIONS = "get_workout_recommendations" but the executor
# routes by that bare task string, so the dict key here must match.
_SKILL_TAIL: dict[str, str] = {
    "analyze_workout": (
        "Respond in 6–10 lines plain text: (1) volume + intensity over the "
        "last 7–14 days grounded in the logs, (2) one mechanism (e.g. "
        "eccentric vs concentric load) tied to the user's pattern, (3) one "
        "implication for readiness. No markdown."
    ),
    "get_recommendations": (
        "Respond in 4–6 lines plain text: 2–3 concrete training-domain "
        "actions for the next session + the 'why' grounded in the data. "
        "Redirect nutrition asks to /nutrition, sleep to /sleep, recovery "
        "to /recovery. No markdown."
    ),
    "log_workout": (
        "Confirm what was logged in 1–2 lines and note the recovery demand "
        "category (e.g. CNS-heavy, metabolic, eccentric). No markdown."
    ),
}


async def build_workout_prompt(
    task: str,
    params: dict,
    peer_artifacts: dict | None = None,
) -> str:
    user_id = UUID(params["user_id"])
    workout_logs = await fetch_recent_logs(user_id, "workout", limit=10)
    body_logs = await fetch_body_logs(user_id, limit=5)
    memories = await search_memories(user_id, task, limit=5)

    workout_text = "\n".join(
        f"- {r['recorded_at'].date()} | {r['type']} | {r['data']}"
        for r in workout_logs
    ) or "No recent workout logs."

    body_text = "\n".join(
        f"- {r['recorded_at'].date()} | weight={r['data'].get('weight_kg')}kg "
        f"| fat={r['data'].get('body_fat_pct')}% "
        f"| muscle={r['data'].get('skeletal_muscle_kg')}kg "
        f"| lean={r['data'].get('lean_mass_kg')}kg"
        for r in body_logs[:5]
    ) or "No body composition data."

    memories_text = "\n".join(
        f"- {m.get('text', '')}" for m in memories
    ) or "No relevant memories."

    peer = peer_artifacts if peer_artifacts is not None else (params.get("peer_artifacts") or {})
    peer_section = ""
    if peer:
        chunks = []
        for name in ("recovery", "sleep", "nutrition", "body", "habits", "medication"):
            text = peer.get(name)
            if text and text.strip() and text != "(данные недоступны)":
                chunks.append(f"### {name}-agent\n{text}")
        if chunks:
            peer_section = "\n## Peer context\n" + "\n\n".join(chunks)

    # `for_date` is set when this is a peer-consult call (e.g. sleep agent
    # asking "what did the user train on YYYY-MM-DD"). Surface it so the LLM
    # focuses its summary on that day.
    raw_for_date = params.get("for_date")
    focus_date_section = (
        f"\n## Peer-consult focus date: {raw_for_date}\n"
        f"This call is from another agent that needs context for "
        f"{raw_for_date} specifically. Prioritize sessions on/around this "
        f"date in your summary; only mention the broader trend if directly "
        f"relevant.\n"
        if isinstance(raw_for_date, str) and raw_for_date else ""
    )

    chip_block = f"\n{PEER_CHIP_RULES}" if peer_section else ""
    skill_tail = _SKILL_TAIL.get(task, "")

    return (
        f"{IDENTITY['workout']}\n\n"
        f"## Recent workouts (last 10)\n{workout_text}\n\n"
        f"## Body composition (last 5 measurements)\n{body_text}\n"
        f"{focus_date_section}{peer_section}\n\n"
        f"## Vocabulary you may invoke (only when grounded by data)\n"
        f"{VOCAB['workout']}\n\n"
        f"## Memories\n{memories_text}\n\n"
        f"## User request\n"
        f"Task: {task}\n"
        f"Params: {params}\n"
        f"{chip_block}\n"
        f"{skill_tail}\n\n"
        f"{GROUNDING_RULES}"
    )
