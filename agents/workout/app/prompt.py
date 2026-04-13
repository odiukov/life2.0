# agents/workout/app/prompt.py
from shared.db import fetch_recent_logs
from shared.vector import search_memories


async def build_workout_prompt(task: str, params: dict, peer_artifacts: dict | None = None) -> str:
    workout_logs = await fetch_recent_logs("workout", limit=10)
    memories = await search_memories("workout_memories", task, limit=5)

    workout_text = "\n".join(
        f"- {r['recorded_at'].date()} | {r['type']} | {r['data']}"
        for r in workout_logs
    ) or "No recent workout logs."

    memories_text = "\n".join(
        f"- {m.get('text', '')}" for m in memories
    ) or "No relevant memories."

    peer = peer_artifacts or {}
    sleep_section = (
        f"\n## Sleep context (from sleep-agent):\n{peer['sleep']}"
        if peer.get("sleep") else ""
    )
    nutrition_section = (
        f"\n## Nutrition context (from nutrition-agent):\n{peer['nutrition']}"
        if peer.get("nutrition") else ""
    )

    return f"""You are a personal workout and training assistant. You have access to the user's training history and context from peer agents.

## Recent workouts (last 10):
{workout_text}
{sleep_section}{nutrition_section}

## Relevant memories:
{memories_text}

## User request:
Task: {task}
Params: {params}

Respond in the user's language. Be concise, specific, and actionable. Reference actual data when relevant.
Workout types tracked: strength (exercises/sets/reps/weight_kg), cycling (distance_km/duration_min/avg_hr), combat (discipline: boxing|mma|muay_thai, duration_min, intensity).
For log_workout: confirm what was logged and note any recovery considerations.
For analyze_workout: identify trends in volume, intensity, and recovery across workout types.
For get_recommendations: suggest next session type and intensity based on recent training load and nutrition intake.
If peer context sections are present, synthesize a grouped response covering Workout, Sleep, Nutrition, and Recommendations."""
