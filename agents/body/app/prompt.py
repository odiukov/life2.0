from shared.db import fetch_body_logs, fetch_recent_logs
from shared.vector import search_memories


def _format_body(r: dict) -> str:
    date = r["recorded_at"].date()
    d = r.get("data", {})
    parts = [
        f"weight={d.get('weight_kg')}kg",
        f"fat={d.get('body_fat_pct')}%",
        f"muscle={d.get('muscle_kg')}kg",
        f"skeletal_muscle={d.get('skeletal_muscle_kg')}kg",
        f"bmr={d.get('bmr_kcal')}kcal",
        f"visceral_fat={d.get('visceral_fat_grade')}",
        f"body_age={d.get('body_age')}",
        f"body_score={d.get('body_score')}",
    ]
    return f"- {date} | " + " | ".join(p for p in parts if "None" not in p)


def _format_cross(r: dict) -> str:
    return f"- {r['recorded_at'].date()} | {r['type']} | {r.get('data', {})}"


async def build_body_prompt(task: str, params: dict) -> str:
    body_logs = await fetch_body_logs(limit=30)
    memories = await search_memories(task, limit=5)

    if task == "analyze_body_trend":
        nutrition_logs = await fetch_recent_logs("nutrition", limit=20)
        workout_logs = await fetch_recent_logs("workout", limit=20)
    else:
        nutrition_logs = []
        workout_logs = []

    body_text = "\n".join(_format_body(r) for r in body_logs) \
        or "No body composition measurements yet — ask the user to upload a ViHealth PDF."

    nutrition_text = "\n".join(_format_cross(r) for r in nutrition_logs) \
        or "No recent nutrition logs."
    workout_text = "\n".join(_format_cross(r) for r in workout_logs) \
        or "No recent workout logs."

    memories_text = "\n".join(f"- {m.get('text', '')}" for m in memories) \
        or "No relevant memories."

    return f"""You are a personal body-composition assistant. You have access to the user's weigh-in history and context from peer agents.

## Body composition history (latest 30):
{body_text}

## Recent nutrition (cross-context):
{nutrition_text}

## Recent workouts (cross-context):
{workout_text}

## Relevant memories:
{memories_text}

## User request:
Task: {task}
Params: {params}

Respond in the user's language. Be concise and specific, reference actual numbers.
For get_latest_body: state the most recent weight, body fat %, and any standouts (score, visceral fat) in 1-3 sentences.
For analyze_body_trend: look at the weight/fat/muscle trend, correlate with calorie intake and training volume, and give 1-2 concrete recommendations.
If there is no body data, say so clearly and ask the user to upload a ViHealth PDF."""
