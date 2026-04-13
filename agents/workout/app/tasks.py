import asyncio
import json
import uuid

from shared.claude_runner import run_claude
from shared.db import insert_task
from shared.vector import upsert_memory
from .prompt import build_workout_prompt

SUPPORTED_TASKS = {"log_workout", "analyze_workout", "get_recommendations"}


async def handle_task(task: str, params: dict) -> dict:
    if task not in SUPPORTED_TASKS:
        return {"status": "error", "output": f"Unknown task: {task}"}

    try:
        prompt = await build_workout_prompt(task, params)
        output = await asyncio.to_thread(run_claude, prompt)
        await insert_task("workout", task, params, output)
        await upsert_memory(
            collection="workout_memories",
            id_=str(uuid.uuid4()),
            text=output,
            metadata={"task": task, "params": json.dumps(params)},
        )
        return {"status": "completed", "output": output}
    except Exception as e:
        return {"status": "error", "output": str(e)}
