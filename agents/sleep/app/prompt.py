from shared.db import fetch_recent_logs
from shared.vector import search_memories


async def build_sleep_prompt(task: str, params: dict, peer_artifacts: dict | None = None) -> str:
    recent_logs = await fetch_recent_logs("sleep", limit=10)
    memories = await search_memories("sleep_memories", task, limit=5)

    logs_text = "\n".join(
        f"- {r['recorded_at'].date()} | {r['type']} | {r['data']}"
        for r in recent_logs
    ) or "No recent sleep logs."

    memories_text = "\n".join(
        f"- {m.get('text', '')}" for m in memories
    ) or "No relevant memories."

    peer = peer_artifacts or {}
    workout_section = (
        f"\n## Workout context (from workout-agent):\n{peer['workout']}"
        if peer.get("workout") else ""
    )
    nutrition_section = (
        f"\n## Nutrition context (from nutrition-agent):\n{peer['nutrition']}"
        if peer.get("nutrition") else ""
    )

    return f"""You are a personal sleep health assistant. You have access to the user's sleep history and context from peer agents.

## Recent sleep logs (last 10 entries):
{logs_text}
{workout_section}{nutrition_section}

## Relevant memories:
{memories_text}

## User request:
Task: {task}
Params: {params}

Respond in the user's language. Be concise, specific, and actionable. Reference actual data from the logs when relevant.
If peer context sections are present, synthesize a grouped response covering Sleep, and relevant insights from the peer domains."""
