# agents/sleep/app/tasks.py
import asyncio
import json
import uuid

from shared.a2a import A2ATask, Artifact, TaskStatus, TextPart
from shared.claude_runner import run_claude
from shared.db import insert_task
from shared.vector import upsert_memory
from .prompt import build_sleep_prompt

SUPPORTED_TASKS = {"analyze_sleep", "log_sleep", "get_recommendations"}


async def handle_task(task: str, params: dict) -> A2ATask:
    task_id = str(uuid.uuid4())

    if task not in SUPPORTED_TASKS:
        return A2ATask(
            id=task_id,
            status=TaskStatus.now("failed"),
            artifacts=[Artifact(name="error", parts=[TextPart(text=f"Unknown task: {task}")])],
        )

    try:
        prompt = await build_sleep_prompt(task, params)
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
