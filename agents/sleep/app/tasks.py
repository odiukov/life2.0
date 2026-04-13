from shared.claude_runner import run_claude
from shared.db import insert_task, insert_log
from shared.vector import upsert_memory
from .prompt import build_sleep_prompt
import uuid

SUPPORTED_TASKS = {"analyze_sleep", "log_sleep", "get_recommendations"}


async def handle_task(task: str, params: dict) -> dict:
    if task not in SUPPORTED_TASKS:
        return {"status": "error", "output": f"Unknown task: {task}"}

    prompt = await build_sleep_prompt(task, params)
    output = run_claude(prompt)

    await insert_task("sleep", task, params, output)
    await upsert_memory(
        collection="sleep_memories",
        id_=str(uuid.uuid4()),
        text=output,
        metadata={"task": task, "params": str(params)},
    )

    return {"status": "completed", "output": output}
