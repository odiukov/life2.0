# agents/nutrition/app/tasks.py
import asyncio
import json
import os
import uuid

import httpx

from shared.a2a import A2ATask, Artifact, TaskStatus, TextPart
from shared.claude_runner import run_claude
from shared.db import insert_task
from shared.peer import fetch_peer_artifacts
from shared.vector import upsert_memory
from .prompt import build_nutrition_prompt

SUPPORTED_TASKS = {"log_meal", "analyze_nutrition", "get_recommendations", "briefing"}
_SYNC_TASKS = {"analyze_nutrition", "get_recommendations"}

_PEER_TASK_NAMES: dict[str, str] = {
    "workout": "analyze_workout",
    "sleep": "analyze_sleep",
}

_WORKOUT_KEYWORDS = {
    "тренировк", "трениров", "workout", "exercise", "нагрузк", "training",
    "физ", "спорт", "sport", "run", "бег", "восстановлени", "recover",
}
_SLEEP_KEYWORDS = {
    "сон", "сна", "сну", "sleep", "усталост", "fatigue", "tired",
    "отдых", "rest", "hrv", "readiness", "восстановл",
}


def _decide_peer_consultation(task: str, message: str) -> set[str]:
    """Return set of peer names to consult for this request.

    Rules:
    - log_meal: never needs peers — just recording data
    - get_recommendations: always consult workout (training load shapes nutrition advice)
    - analyze_nutrition: consult relevant peers based on message keywords
    """
    if task == "log_meal":
        return set()

    if task == "get_recommendations":
        return {"workout"}

    # analyze_nutrition — consult only if message mentions the domain
    msg_lower = message.lower()
    needed: set[str] = set()
    if any(kw in msg_lower for kw in _WORKOUT_KEYWORDS):
        needed.add("workout")
    if any(kw in msg_lower for kw in _SLEEP_KEYWORDS):
        needed.add("sleep")
    return needed


async def _trigger_yazio_sync() -> None:
    """Fire-and-forget call to sync-service. Failure is logged, never raised."""
    url = os.environ.get("SYNC_SERVICE_URL", "")
    if not url:
        return
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(f"{url}/sync/nutrition")
    except Exception:
        pass  # stale data is acceptable; sync failure must not block analysis


def _build_briefing_prompt(params: dict) -> str:
    kcal = params.get("kcal", 0)
    protein = params.get("protein_g", 0)
    carbs = params.get("carbs_g", 0)
    fat = params.get("fat_g", 0)

    return f"""You are a personal nutrition coach providing a morning briefing.
Yesterday's nutrition data:
- Total calories: {kcal} kcal
- Protein: {protein}g
- Carbohydrates: {carbs}g
- Fat: {fat}g

Write a 2-3 sentence plain-text summary (no markdown) of yesterday's nutrition.
Note any standouts (high/low protein, surplus/deficit) and implications for today."""


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

        if task in _SYNC_TASKS:
            await _trigger_yazio_sync()

        if peer_artifacts is None:
            message = params.get("message", "")
            needed = _decide_peer_consultation(task, message)
            peer_artifacts = await fetch_peer_artifacts(params.get("peer_agents", {}), _PEER_TASK_NAMES, needed=needed)

        prompt = await build_nutrition_prompt(task, params, peer_artifacts)
        output = await asyncio.to_thread(run_claude, prompt)
        await insert_task("nutrition", task, params, output)
        await upsert_memory(
            collection="nutrition_memories",
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
