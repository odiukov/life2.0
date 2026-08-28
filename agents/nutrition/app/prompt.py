"""Nutrition-agent prompt builder."""
from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import UUID

from shared.db import fetch_recent_logs, fetch_body_logs, get_body_profile
from shared.grounding import GROUNDING_RULES
from shared.peer_chip_rules import PEER_CHIP_RULES
from shared.personas import IDENTITY, VOCAB
from shared.vector import search_memories


def _format_log(r: dict) -> str:
    date_ = r["recorded_at"].date()
    log_type = r["type"]
    data = r.get("data", {})
    source = r.get("source", "manual")
    if source == "yazio" and log_type == "meal":
        meal_type = data.get("meal_type", "")
        totals = data.get("totals", {})
        items = data.get("items", [])
        items_str = ", ".join(
            f"{item['name']} {item['amount_g']}g" for item in items
        )
        kcal = round(totals.get("kcal", 0))
        protein = round(totals.get("protein_g", 0), 1)
        carbs = round(totals.get("carbs_g", 0), 1)
        fat = round(totals.get("fat_g", 0), 1)
        return f"- {date_} | {meal_type} | {items_str} → {kcal} kcal | P:{protein}g C:{carbs}g F:{fat}g"
    return f"- {date_} | {log_type} | {data}"


# Keys are the bare task names that skills.py passes to build_nutrition_prompt
# (NOT the AgentCard skill IDs). See agents/nutrition/app/skills.py.
_SKILL_TAIL: dict[str, str] = {
    "analyze_nutrition": (
        "Respond in 6–10 lines plain text: (1) intake vs goal grounded in "
        "the data, (2) protein floor and carb-around-training observations, "
        "(3) meal-timing pattern. Redirect cross-domain action to peers. "
        "No markdown."
    ),
    "get_recommendations": (
        "Respond in 4–6 lines plain text: 2–3 concrete nutrition actions for "
        "today + the 'why' grounded in the data and recent training. "
        "Redirect training prescriptions to /workout. No markdown."
    ),
    "log_meal": (
        "Parse the free-text meal description from params['raw_text'], "
        "estimate kcal/protein_g/carbs_g/fat_g, and confirm what was logged "
        "in 1–2 lines. If unsure, state confidence."
    ),
}


async def build_nutrition_prompt(
    task: str,
    params: dict,
    peer_artifacts: dict | None = None,
) -> str:
    user_id = UUID(params["user_id"])
    nutrition_logs = await fetch_recent_logs(user_id, "nutrition", limit=10)
    body_rows = await fetch_body_logs(user_id, limit=1)
    body_profile = await get_body_profile(user_id)
    memories = await search_memories(user_id, task, limit=5)

    target_date: date
    raw_for_date = params.get("for_date")
    if isinstance(raw_for_date, str) and raw_for_date:
        try:
            target_date = date.fromisoformat(raw_for_date)
        except ValueError:
            target_date = datetime.now(timezone.utc).date()
    else:
        target_date = datetime.now(timezone.utc).date()
    is_today = target_date == datetime.now(timezone.utc).date()
    target_label = "Today" if is_today else f"Day ({target_date})"
    target_logs = [
        r for r in nutrition_logs
        if r["recorded_at"].date() == target_date and r.get("source") == "yazio"
    ]
    today_kcal = round(sum(r["data"].get("totals", {}).get("kcal", 0) for r in target_logs))
    today_protein = round(sum(r["data"].get("totals", {}).get("protein_g", 0) for r in target_logs), 1)
    today_carbs = round(sum(r["data"].get("totals", {}).get("carbs_g", 0) for r in target_logs), 1)
    today_fat = round(sum(r["data"].get("totals", {}).get("fat_g", 0) for r in target_logs), 1)

    nutrition_text = "\n".join(_format_log(r) for r in nutrition_logs) or "No recent nutrition logs."
    memories_text = "\n".join(
        f"- {m.get('text', '')}" for m in memories
    ) or "No relevant memories."

    if body_rows:
        d = body_rows[0]["data"]
        body_date = body_rows[0]["recorded_at"].date()
        body_text = (
            f"- {body_date} | weight={d.get('weight_kg')}kg "
            f"| fat={d.get('body_fat_pct')}% | BMR={d.get('bmr_kcal')}kcal"
        )
    else:
        body_text = "No body composition measurements yet."

    calorie_goal: int | None = None
    if body_profile:
        profile_parts = []
        if body_profile.get("height_cm"):
            profile_parts.append(f"height={body_profile['height_cm']}cm")
        if body_profile.get("age"):
            profile_parts.append(f"age={body_profile['age']}")
        if body_profile.get("sex"):
            profile_parts.append(f"sex={body_profile['sex']}")
        if body_profile.get("activity_level"):
            profile_parts.append(f"activity={body_profile['activity_level']}")
        if body_profile.get("calorie_goal_override"):
            calorie_goal = int(body_profile["calorie_goal_override"])
            profile_parts.append(f"calorie_goal={calorie_goal}kcal")
        profile_text = " | ".join(profile_parts) if profile_parts else "Not set."
    else:
        profile_text = "Not set."

    if calorie_goal is None and body_rows:
        bmr = body_rows[0]["data"].get("bmr_kcal")
        if bmr:
            activity = (body_profile or {}).get("activity_level", "")
            multipliers = {
                "sedentary": 1.2, "lightly_active": 1.375,
                "moderately_active": 1.55, "very_active": 1.725, "extra_active": 1.9,
            }
            multiplier = multipliers.get(activity, 1.375)
            calorie_goal = round(bmr * multiplier)

    peer = peer_artifacts if peer_artifacts is not None else (params.get("peer_artifacts") or {})
    peer_section = ""
    if peer:
        chunks = []
        for name in ("workout", "body", "sleep", "mood", "medication"):
            text = peer.get(name)
            if text and text.strip() and text != "(данные недоступны)":
                chunks.append(f"### {name}\n{text}")
        if chunks:
            peer_section = "\n## Peer context\n" + "\n\n".join(chunks)

    goal_line = f"{calorie_goal} kcal" if calorie_goal else "unknown"
    remaining = (calorie_goal - today_kcal) if calorie_goal else None
    remaining_line = f"{remaining} kcal remaining" if remaining is not None else "goal unknown"

    chip_block = f"\n{PEER_CHIP_RULES}" if peer_section else ""
    skill_tail = _SKILL_TAIL.get(task, "")

    return (
        f"{IDENTITY['nutrition']}\n\n"
        f"## User profile\n{profile_text}\n\n"
        f"## {target_label} ({target_date}) intake (from Yazio)\n"
        f"- Eaten: {today_kcal} kcal | P:{today_protein}g C:{today_carbs}g F:{today_fat}g\n"
        f"- Goal: {goal_line}\n"
        f"- {remaining_line}\n\n"
        f"## Recent nutrition (last 10 meals, may span multiple days — each line shows its date)\n"
        f"{nutrition_text}\n"
        f"{peer_section}\n\n"
        f"## Latest body composition (cross-context)\n{body_text}\n\n"
        f"## Vocabulary you may invoke (only when grounded by data)\n"
        f"{VOCAB['nutrition']}\n\n"
        f"## Memories\n{memories_text}\n\n"
        f"## User request\n"
        f"Task: {task}\n"
        f"Params: {params}\n"
        f"{chip_block}\n"
        f"{skill_tail}\n\n"
        f"{GROUNDING_RULES}"
    )
