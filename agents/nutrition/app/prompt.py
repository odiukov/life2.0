from shared.db import fetch_recent_logs
from shared.vector import search_memories


def _format_log(r: dict) -> str:
    """Format a single health_log row for the prompt."""
    date = r["recorded_at"].date()
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
        return f"- {date} | {meal_type} | {items_str} → {kcal} kcal | P:{protein}g C:{carbs}g F:{fat}g"

    return f"- {date} | {log_type} | {data}"


async def build_nutrition_prompt(task: str, params: dict, peer_artifacts: dict | None = None) -> str:
    nutrition_logs = await fetch_recent_logs("nutrition", limit=10)
    workout_logs = await fetch_recent_logs("workout", limit=3)
    memories = await search_memories("nutrition_memories", task, limit=5)

    nutrition_text = "\n".join(_format_log(r) for r in nutrition_logs) or "No recent nutrition logs."

    workout_text = "\n".join(
        f"- {r['recorded_at'].date()} | {r['type']} | {r['data']}"
        for r in workout_logs
    ) or "No recent workout logs."

    memories_text = "\n".join(
        f"- {m.get('text', '')}" for m in memories
    ) or "No relevant memories."

    peer = peer_artifacts or {}
    workout_peer_section = (
        f"\n## Workout analysis (from workout-agent):\n{peer['workout']}"
        if peer.get("workout") else ""
    )
    sleep_section = (
        f"\n## Sleep context (from sleep-agent):\n{peer['sleep']}"
        if peer.get("sleep") else ""
    )

    return f"""You are a personal nutrition assistant. You have access to the user's meal history and context from peer agents.

## Recent nutrition (last 10 meals):
{nutrition_text}

## Recent workouts (last 3):
{workout_text}
{workout_peer_section}{sleep_section}

## Relevant memories:
{memories_text}

## User request:
Task: {task}
Params: {params}

Respond in the user's language. Be concise, specific, and actionable. Reference actual data when relevant.
For log_meal: parse the free-text meal description from params['raw_text'], estimate КБЖУ (kcal, protein_g, carbs_g, fat_g), and confirm what was logged. If uncertain about macros, state your confidence level.
For analyze_nutrition: identify trends in daily calories, protein intake, and meal timing relative to workouts.
For get_recommendations: suggest nutrition adjustments based on recent workout intensity and current macro balance. Flag low protein on training days.
If peer context sections are present, synthesize a grouped response covering Nutrition and relevant insights from the peer domains."""
