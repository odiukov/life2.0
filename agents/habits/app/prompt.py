"""Prompt builders for the 5 habits agent skills."""
from uuid import UUID

from shared.db import fetch_active_habits, fetch_habit_logs
from shared.grounding import GROUNDING_RULES
from shared.peer_chip_rules import PEER_CHIP_RULES
from shared.personas import IDENTITY, VOCAB
from shared.vector import search_memories


def _format_habit(h: dict) -> str:
    parts = [f"{h['name']} ({h['kind']})"]
    if h["cadence_type"] == "daily":
        parts.append("daily")
    else:
        days = ", ".join(h.get("cadence_days") or [])
        parts.append(f"weekly: {days}")
    if h.get("target_value") is not None:
        parts.append(f"target={h['target_value']}{h.get('unit') or ''}")
    return " | ".join(parts)


def _format_check(r: dict) -> str:
    date = r["recorded_at"].date()
    time = r["recorded_at"].strftime("%H:%M")
    d = r.get("data", {})
    bits = [d.get("name", "?")]
    if d.get("value") is not None:
        bits.append(f"{d['value']}{d.get('unit') or ''}")
    if d.get("note"):
        bits.append(f'"{d["note"][:40]}"')
    return f"- {date} {time} | " + " | ".join(bits)


_DEFINE_INSTRUCTIONS = """You are a habit definition parser. The user just sent a free-text
description of a habit they want to track. Extract the fields and respond with STRICT JSON
only — no prose, no markdown fences, no keys beyond the schema below.

Schema:
{
  "name":          string in lowercase kebab-case, single token, English ASCII preferred
                   (e.g. "meditation", "cold-shower", "no-alcohol", "gym").
                   If the user named the habit in another language, translate to a short
                   canonical English name (e.g. "медитация" → "meditation").
  "kind":          "boolean" | "quantitative",
  "cadence_type":  "daily" | "weekly",
  "cadence_days":  null OR array of lowercase weekday abbreviations
                   (["mon","tue","wed","thu","fri","sat","sun"]).
                   Required when cadence_type="weekly"; null when "daily".
  "target_value":  number or null (only for kind="quantitative"),
  "unit":          string or null (e.g. "min","pages","km"; only for kind="quantitative")
}

Rules:
- If the user gives a numeric target ("20 minutes", "30 pages", "5 km"), set kind="quantitative"
  with matching target_value and unit. Otherwise kind="boolean".
- If the user says "every day" / "daily" / "ежедневно" / nothing specific → cadence_type="daily",
  cadence_days=null.
- If the user names specific days ("Mon/Wed/Fri", "по пн/ср/пт", "weekends") → cadence_type="weekly"
  with cadence_days populated.
- Return STRICT JSON with exactly these keys. No extras, no comments.
"""


_SYSTEM_TEMPLATE = """You are a personal habits assistant. You have access to the user's
active habit definitions and recent check-ins.

## Active habits:
{habits}

## Recent check-ins:
{checks}

## User request:
Task: {task}
Params: {params}
"""


async def build_habits_prompt(
    task: str,
    params: dict,
    peer_artifacts: dict | None = None,
) -> str:
    user_id = UUID(params["user_id"])
    habit_rows = await fetch_active_habits(user_id)
    habit_id = params.get("habit_id") if task == "analyze_habit" else None
    check_rows: list[dict] = []
    if task in ("analyze_habit",):
        check_rows = await fetch_habit_logs(user_id, habit_id=habit_id, days=int(params.get("days", 30)))

    habits_text = "\n".join(f"- {_format_habit(h)}" for h in habit_rows) \
        or "No active habits."
    checks_text = "\n".join(_format_check(r) for r in check_rows) \
        or "No check-ins in window."

    peer = peer_artifacts if peer_artifacts is not None else (params.get("peer_artifacts") or {})
    peer_section = ""
    if peer:
        chunks = []
        for name in ("mood", "sleep", "workout"):
            text = peer.get(name)
            if text and text.strip() and text != "(данные недоступны)":
                chunks.append(f"### {name}\n{text}")
        if chunks:
            peer_section = "\n## Peer context\n" + "\n\n".join(chunks)
    chip_block = f"\n{PEER_CHIP_RULES}" if peer_section else ""

    if task == "define_habit":
        # Pure JSON parser — no persona, no peer context, no grounding rules.
        # The whole prompt is the parser instruction.
        return _SYSTEM_TEMPLATE.format(
            habits=habits_text, checks=checks_text, task=task, params=params,
        ) + "\n" + _DEFINE_INSTRUCTIONS

    if task in ("log_habit_check", "get_streak_summary", "archive_habit"):
        # Deterministic skills — the executor short-circuits and never sends
        # this prompt to the LLM. Return the legacy stub for observability.
        return _SYSTEM_TEMPLATE.format(
            habits=habits_text, checks=checks_text, task=task, params=params,
        ) + (
            "\nThis skill is handled deterministically by the executor — "
            "no LLM output is used."
        )

    # analyze_habit — full persona composition with peer context + grounding.
    base = (
        f"{IDENTITY['habits']}\n\n"
        f"## Active habits\n{habits_text}\n\n"
        f"## Recent check-ins\n{checks_text}\n"
        f"{peer_section}\n\n"
        f"## Vocabulary you may invoke (only when grounded by data)\n"
        f"{VOCAB['habits']}\n\n"
        f"## User request\n"
        f"Task: {task}\n"
        f"Params: {params}\n"
        f"{chip_block}"
    )
    if not check_rows:
        return base + (
            "\nThere are not enough check-ins to analyze yet. Tell the user "
            "to log a few days first. Plain text, no markdown.\n\n"
            + GROUNDING_RULES
        )
    return base + (
        "\nRespond in 4–6 lines plain text: (1) per-habit completion %, "
        "(2) current streak and longest streak, (3) one observation linking "
        "to peer context (e.g. mood, sleep, training) if present. Redirect "
        "cross-domain prescriptions to peers. No markdown.\n\n"
        + GROUNDING_RULES
    )
