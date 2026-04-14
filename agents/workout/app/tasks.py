# agents/workout/app/tasks.py
import asyncio
import json
import logging
import uuid

from shared.a2a import A2ATask, Artifact, TaskStatus, TextPart
from shared.claude_runner import run_claude
from shared.db import insert_task
from shared.peer import fetch_peer_artifacts
from shared.vector import upsert_memory
from .prompt import build_workout_prompt

logger = logging.getLogger(__name__)

SUPPORTED_TASKS = {"log_workout", "analyze_workout", "get_recommendations", "briefing"}

_PEER_TASK_NAMES: dict[str, str] = {
    "sleep": "analyze_sleep",
    "nutrition": "analyze_nutrition",
}

# Keywords that signal a peer agent's context is relevant
_SLEEP_KEYWORDS = {
    "сон", "сна", "сну", "sleep", "восстановлени", "усталост", "fatigue",
    "tired", "rest", "отдых", "recover", "hrv", "readiness",
}
_NUTRITION_KEYWORDS = {
    "питани", "еда", "еде", "калори", "nutrition", "food", "calorie",
    "protein", "белок", "energy", "энергия", "macro", "макро", "diet",
    "диет", "углевод", "carb", "жир", "fat",
}


def _decide_peer_consultation(task: str, message: str) -> set[str]:
    """Return set of peer names that should be consulted for this request.

    Rules:
    - log_workout: never needs peers — it's just recording data
    - get_recommendations: always needs all peers — full context improves suggestions
    - analyze_workout: check message for domain-specific keywords
    """
    if task == "log_workout":
        return set()

    if task == "get_recommendations":
        return {"sleep", "nutrition"}

    # analyze_workout — consult only if message is relevant
    msg_lower = message.lower()
    needed: set[str] = set()
    if any(kw in msg_lower for kw in _SLEEP_KEYWORDS):
        needed.add("sleep")
    if any(kw in msg_lower for kw in _NUTRITION_KEYWORDS):
        needed.add("nutrition")
    return needed


def _build_briefing_prompt(params: dict) -> str:
    name = params.get("first_name") or params.get("first_type") or "Workout"
    dist_km = params.get("total_distance_meters", 0) / 1000
    kcal = params.get("total_calories", 0)
    count = params.get("activity_count", 1)

    dist_line = f"- Distance: {dist_km:.1f} km" if dist_km > 0 else ""
    count_line = f"- Activities: {count}" if count > 1 else ""

    return f"""You are a personal fitness coach providing a morning briefing.
Yesterday's workout data:
- Activity: {name}
{dist_line}
- Calories burned: {kcal} kcal
{count_line}

Write a 2-3 sentence plain-text summary (no markdown) of yesterday's workout.
Note training load and how it may affect today's readiness."""


async def handle_task(
    task: str,
    params: dict,
    peer_artifacts: dict | None = None,
) -> A2ATask:
    task_id = str(uuid.uuid4())

    if task not in SUPPORTED_TASKS:
        return A2ATask(
            id=task_id,
            status=TaskStatus.now("failed"),
            artifacts=[Artifact(name="error", parts=[TextPart(text=f"Unknown task: {task}")])],
        )

    try:
        if task == "briefing":
            prompt = _build_briefing_prompt(params)
            output = await asyncio.to_thread(run_claude, prompt)
            return A2ATask(
                id=task_id,
                status=TaskStatus.now("completed"),
                artifacts=[Artifact(name="briefing", parts=[TextPart(text=output)])],
            )

        if peer_artifacts is None:
            message = params.get("message", "")
            needed = _decide_peer_consultation(task, message)
            peer_artifacts = await fetch_peer_artifacts(params.get("peer_agents", {}), _PEER_TASK_NAMES, needed=needed)

        prompt = await build_workout_prompt(task, params, peer_artifacts)
        output = await asyncio.to_thread(run_claude, prompt)
        await insert_task("workout", task, params, output)
        await upsert_memory(
            collection="workout_memories",
            id_=str(uuid.uuid4()),
            text=output,
            metadata={"task": task, "params": json.dumps(params)},
        )

        return A2ATask(
            id=task_id,
            status=TaskStatus.now("completed"),
            artifacts=[Artifact(name="analysis", parts=[TextPart(text=output)])],
        )
    except Exception as e:
        return A2ATask(
            id=task_id,
            status=TaskStatus.now("failed"),
            artifacts=[Artifact(name="error", parts=[TextPart(text=str(e))])],
        )
