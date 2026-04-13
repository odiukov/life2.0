from shared.db import fetch_recent_logs
from shared.vector import search_memories


async def build_workout_prompt(task: str, params: dict) -> str:
    workout_logs = await fetch_recent_logs("workout", limit=10)
    nutrition_logs = await fetch_recent_logs("nutrition", limit=5)
    memories = await search_memories("workout_memories", task, limit=5)

    workout_text = "\n".join(
        f"- {r['recorded_at'].date()} | {r['type']} | {r['data']}"
        for r in workout_logs
    ) or "No recent workout logs."

    nutrition_text = "\n".join(
        f"- {r['recorded_at'].date()} | {r['type']} | {r['data']}"
        for r in nutrition_logs
    ) or "No recent nutrition logs."

    memories_text = "\n".join(
        f"- {m.get('text', '')}" for m in memories
    ) or "No relevant memories."

    return f"""You are a personal workout and training assistant. You have access to the user's training history and recent nutrition.

## Recent workouts (last 10):
{workout_text}

## Recent nutrition (last 5):
{nutrition_text}

## Relevant memories:
{memories_text}

## User request:
Task: {task}
Params: {params}

Respond in the user's language. Be concise, specific, and actionable. Reference actual data when relevant.
Workout types tracked: strength (exercises/sets/reps/weight_kg), cycling (distance_km/duration_min/avg_hr), combat (discipline: boxing|mma|muay_thai, duration_min, intensity).
For log_workout: confirm what was logged and note any recovery considerations given recent nutrition.
For analyze_workout: identify trends in volume, intensity, and recovery across workout types.
For get_recommendations: suggest next session type and intensity based on recent training load and nutrition intake."""
