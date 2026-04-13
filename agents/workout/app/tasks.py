# agents/workout/app/tasks.py
import asyncio
import json
import logging
import uuid

import httpx

from shared.a2a import A2ATask, Artifact, TaskStatus, TextPart
from shared.claude_runner import run_claude
from shared.db import insert_task
from shared.vector import upsert_memory
from .prompt import build_workout_prompt

logger = logging.getLogger(__name__)

SUPPORTED_TASKS = {"log_workout", "analyze_workout", "get_recommendations"}

_PEER_TASK_NAMES: dict[str, str] = {
    "sleep": "analyze_sleep",
    "nutrition": "analyze_nutrition",
}


async def _call_peer(url: str, task_name: str) -> str:
    """POST to a peer agent's /tasks endpoint, return artifact text."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{url}/tasks",
                json={"task": task_name, "params": {"context": "summary requested by workout-agent"}},
            )
            resp.raise_for_status()
            data = resp.json()
            artifacts = data.get("artifacts", [])
            if artifacts and artifacts[0].get("parts"):
                return artifacts[0]["parts"][0].get("text", "(данные недоступны)")
    except Exception as e:
        logger.warning("Peer call to %s failed: %s", url, e)
    return "(данные недоступны)"


async def fetch_peer_artifacts(peer_agents: dict) -> dict[str, str]:
    """Call all known peer agents in parallel, return {name: text}."""
    coros = {
        name: _call_peer(info["url"], _PEER_TASK_NAMES[name])
        for name, info in peer_agents.items()
        if name in _PEER_TASK_NAMES and info.get("url")
    }
    if not coros:
        return {}
    texts = await asyncio.gather(*coros.values())
    return dict(zip(coros.keys(), texts))


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
        if peer_artifacts is None:
            peer_artifacts = await fetch_peer_artifacts(params.get("peer_agents", {}))

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
