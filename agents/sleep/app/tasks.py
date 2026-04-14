# agents/sleep/app/tasks.py
import asyncio
import json
import uuid

from shared.a2a import A2ATask, Artifact, TaskStatus, TextPart
from shared.claude_runner import run_claude
from shared.db import insert_task
from shared.peer import fetch_peer_artifacts
from shared.vector import upsert_memory
from .prompt import build_sleep_prompt

SUPPORTED_TASKS = {"analyze_sleep", "log_sleep", "get_recommendations", "briefing"}

_PEER_TASK_NAMES: dict[str, str] = {
    "workout": "analyze_workout",
    "nutrition": "analyze_nutrition",
}

_WORKOUT_KEYWORDS = {
    "тренировк", "трениров", "workout", "exercise", "нагрузк", "training",
    "физ", "спорт", "sport", "run", "бег", "кардио", "cardio",
}
_NUTRITION_KEYWORDS = {
    "питани", "еда", "еде", "калори", "nutrition", "food", "calorie",
    "protein", "белок", "алкогол", "alcohol", "кофе", "coffee",
    "ужин", "dinner", "поздн", "late",
}


def _decide_peer_consultation(task: str, message: str) -> set[str]:
    """Return set of peer names to consult for this request.

    Rules:
    - log_sleep: never needs peers — just recording data
    - get_recommendations: always consult workout (training load shapes sleep advice)
    - analyze_sleep: consult relevant peers based on message keywords
    """
    if task == "log_sleep":
        return set()

    if task == "get_recommendations":
        return {"workout"}

    # analyze_sleep — consult only if message mentions the domain
    msg_lower = message.lower()
    needed: set[str] = set()
    if any(kw in msg_lower for kw in _WORKOUT_KEYWORDS):
        needed.add("workout")
    if any(kw in msg_lower for kw in _NUTRITION_KEYWORDS):
        needed.add("nutrition")
    return needed


def _build_briefing_prompt(params: dict) -> str:
    dur = params.get("duration_seconds", 0)
    hours = dur // 3600
    minutes = (dur % 3600) // 60
    deep = params.get("deep_sleep_seconds", 0)
    deep_hours = deep // 3600
    deep_minutes = (deep % 3600) // 60
    hrv = params.get("hrv")

    data_lines = [
        f"- Duration: {hours}h {minutes}m",
        f"- Deep sleep: {deep_hours}h {deep_minutes}m",
    ]
    if hrv:
        data_lines.append(f"- HRV: {hrv} ms")

    return (
        "You are a personal sleep health assistant providing a morning briefing.\n"
        "Yesterday's sleep data:\n"
        + "\n".join(data_lines)
        + "\n\nWrite a 2-3 sentence plain-text summary (no markdown) of yesterday's sleep quality.\n"
        "Focus on what stands out and how it may affect today's energy and recovery."
    )


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

        prompt = await build_sleep_prompt(task, params, peer_artifacts)
        output = await asyncio.to_thread(run_claude, prompt)
        await insert_task("sleep", task, params, output)
        await upsert_memory(
            collection="sleep_memories",
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
