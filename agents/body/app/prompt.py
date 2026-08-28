"""Body-agent prompt builder. Cross-domain context comes from peer_artifacts,
not direct DB reads — see spec §5."""
from __future__ import annotations

from uuid import UUID

from shared.db import fetch_body_logs
from shared.grounding import GROUNDING_RULES
from shared.peer_chip_rules import PEER_CHIP_RULES
from shared.personas import IDENTITY, VOCAB
from shared.vector import search_memories


def _format_body(r: dict) -> str:
    date_ = r["recorded_at"].date()
    d = r.get("data", {})
    fields = [
        ("weight", "kg", d.get("weight_kg")),
        ("fat", "%", d.get("body_fat_pct")),
        ("muscle", "kg", d.get("muscle_kg")),
        ("skeletal_muscle", "kg", d.get("skeletal_muscle_kg")),
        ("bmr", "kcal", d.get("bmr_kcal")),
        ("visceral_fat", "", d.get("visceral_fat_grade")),
        ("body_age", "", d.get("body_age")),
        ("body_score", "", d.get("body_score")),
    ]
    parts = [f"{label}={value}{unit}" for label, unit, value in fields if value is not None]
    if not parts:
        return f"- {date_} | (no metrics)"
    return f"- {date_} | " + " | ".join(parts)


# Keys are the bare task names that skills.py passes to build_body_prompt.
# See agents/body/app/skills.py.
_SKILL_TAIL: dict[str, str] = {
    "get_latest_body": (
        "State the most recent weight, body fat %, and any standouts (score, "
        "visceral fat) in 1–3 sentences plain text. No markdown."
    ),
    "analyze_body_trend": (
        "Respond in 6–10 lines plain text: (1) weight / fat / muscle trend "
        "grounded in the body history, (2) one mechanism (recomposition vs "
        "deficit vs hypertrophy phase) tied to the data, (3) one observation "
        "linking peer nutrition / workout / recovery context if present. "
        "Redirect cross-domain prescriptions ('eat fewer carbs', 'lift "
        "heavier') to /nutrition or /workout. No markdown."
    ),
}


async def build_body_prompt(
    task: str,
    params: dict,
    peer_artifacts: dict | None = None,
) -> str:
    user_id = UUID(params["user_id"])
    body_logs = await fetch_body_logs(user_id, limit=30)
    memories = await search_memories(user_id, task, limit=5)

    body_text = "\n".join(_format_body(r) for r in body_logs) \
        or "No body composition measurements yet — ask the user to upload a ViHealth PDF."
    memories_text = "\n".join(f"- {m.get('text', '')}" for m in memories) \
        or "No relevant memories."

    # Body's prompt builder is invoked from skills.py with peer_artifacts now
    # threaded through the executor → params dict. Read either form.
    peer = peer_artifacts if peer_artifacts is not None else (params.get("peer_artifacts") or {})
    peer_section = ""
    if peer:
        chunks = []
        for name in ("nutrition", "workout", "recovery"):
            text = peer.get(name)
            if text and text.strip() and text != "(данные недоступны)":
                chunks.append(f"### {name}\n{text}")
        if chunks:
            peer_section = "\n## Peer context\n" + "\n\n".join(chunks)

    chip_block = f"\n{PEER_CHIP_RULES}" if peer_section else ""
    skill_tail = _SKILL_TAIL.get(task, "")

    return (
        f"{IDENTITY['body']}\n\n"
        f"## Body composition history (latest 30)\n{body_text}\n"
        f"{peer_section}\n\n"
        f"## Vocabulary you may invoke (only when grounded by data)\n"
        f"{VOCAB['body']}\n\n"
        f"## Memories\n{memories_text}\n\n"
        f"## User request\n"
        f"Task: {task}\n"
        f"Params: {params}\n"
        f"{chip_block}\n"
        f"{skill_tail}\n\n"
        f"{GROUNDING_RULES}"
    )
