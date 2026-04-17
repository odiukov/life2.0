"""Prompt builders for the 5 habits agent skills."""
from shared.db import fetch_active_habits, fetch_habit_logs
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


async def build_habits_prompt(task: str, params: dict) -> str:
    habit_rows = await fetch_active_habits()
    habit_id = params.get("habit_id") if task == "analyze_habit" else None
    check_rows: list[dict] = []
    if task in ("analyze_habit",):
        check_rows = await fetch_habit_logs(habit_id=habit_id, days=int(params.get("days", 30)))

    habits_text = "\n".join(f"- {_format_habit(h)}" for h in habit_rows) \
        or "No active habits."
    checks_text = "\n".join(_format_check(r) for r in check_rows) \
        or "No check-ins in window."

    base = _SYSTEM_TEMPLATE.format(
        habits=habits_text,
        checks=checks_text,
        task=task,
        params=params,
    )

    if task == "define_habit":
        return base + "\n" + _DEFINE_INSTRUCTIONS

    if task == "analyze_habit":
        if not check_rows:
            return base + (
                "\nThere are not enough check-ins to analyze yet. "
                "Tell the user to log a few days first. Plain text, no markdown."
            )
        return base + (
            "\nRespond in the user's language with: (1) per-habit completion %, "
            "(2) current streak and longest streak, (3) one concrete observation. "
            "Keep it to 3-6 lines. Plain text, no markdown."
        )

    if task == "log_habit_check":
        return base + (
            "\nThis skill is handled deterministically by the executor — "
            "no LLM output is used."
        )

    if task == "get_streak_summary":
        return base + (
            "\nThis skill is handled deterministically by the executor — "
            "no LLM output is used. Included for observability."
        )

    if task == "archive_habit":
        return base + (
            "\nThis skill is handled deterministically by the executor — "
            "no LLM output is used."
        )

    return base
