# agents/nutrition/app/tasks.py
import asyncio
import json
import os
import uuid

import httpx

from shared.a2a import A2ATask, Artifact, TaskStatus, TextPart
from shared.claude_runner import run_claude
from shared.db import insert_task
from shared.vector import upsert_memory
from .prompt import build_nutrition_prompt

SUPPORTED_TASKS = {"log_meal", "analyze_nutrition", "get_recommendations"}
_SYNC_TASKS = {"analyze_nutrition", "get_recommendations"}


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


async def handle_task(task: str, params: dict) -> A2ATask:
    task_id = str(uuid.uuid4())

    if task not in SUPPORTED_TASKS:
        return A2ATask(
            id=task_id,
            status=TaskStatus.now("failed"),
            artifacts=[Artifact(name="error", parts=[TextPart(text=f"Unknown task: {task}")])],
        )

    try:
        if task in _SYNC_TASKS:
            await _trigger_yazio_sync()

        prompt = await build_nutrition_prompt(task, params)
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
