# agents/workout/app/prompt.py
from shared.db import fetch_recent_logs
from shared.vector import search_memories


async def build_workout_prompt(task: str, params: dict, peer_artifacts: dict | None = None) -> str:
    all_logs = await fetch_recent_logs("workout", limit=20)
    memories = await search_memories("workout_memories", task, limit=5)

    workout_logs = [r for r in all_logs if r["type"] != "body_composition"]
    body_logs = [r for r in all_logs if r["type"] == "body_composition"]

    workout_text = "\n".join(
        f"- {r['recorded_at'].date()} | {r['type']} | {r['data']}"
        for r in workout_logs[:10]
    ) or "No recent workout logs."

    body_text = "\n".join(
        f"- {r['recorded_at'].date()} | weight={r['data'].get('weight_kg')}kg"
        f" | fat={r['data'].get('body_fat_pct')}%"
        f" | muscle={r['data'].get('skeletal_muscle_kg')}kg"
        f" | lean={r['data'].get('lean_mass_kg')}kg"
        f" | bmi={r['data'].get('bmi')}"
        for r in body_logs[:5]
    ) or "No body composition data."

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

## Body composition (last 5 measurements):
{body_text}
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
