from shared.db import fetch_recent_logs
from shared.vector import search_memories


async def build_nutrition_prompt(task: str, params: dict) -> str:
    nutrition_logs = await fetch_recent_logs("nutrition", limit=10)
    workout_logs = await fetch_recent_logs("workout", limit=3)
    memories = await search_memories("nutrition_memories", task, limit=5)

    nutrition_text = "\n".join(
        f"- {r['recorded_at'].date()} | {r['type']} | {r['data']}"
        for r in nutrition_logs
    ) or "No recent nutrition logs."

    workout_text = "\n".join(
        f"- {r['recorded_at'].date()} | {r['type']} | {r['data']}"
        for r in workout_logs
    ) or "No recent workout logs."

    memories_text = "\n".join(
        f"- {m.get('text', '')}" for m in memories
    ) or "No relevant memories."

    return f"""You are a personal nutrition assistant. You have access to the user's meal history and recent workouts.

## Recent nutrition (last 10 meals):
{nutrition_text}

## Recent workouts (last 3):
{workout_text}

## Relevant memories:
{memories_text}

## User request:
Task: {task}
Params: {params}

Respond in the user's language. Be concise, specific, and actionable. Reference actual data when relevant.
For log_meal: parse the free-text meal description from params['raw_text'], estimate КБЖУ (kcal, protein_g, carbs_g, fat_g), and confirm what was logged. If uncertain about macros, state your confidence level.
For analyze_nutrition: identify trends in daily calories, protein intake, and meal timing relative to workouts.
For get_recommendations: suggest nutrition adjustments based on recent workout intensity and current macro balance. Flag low protein on training days."""
