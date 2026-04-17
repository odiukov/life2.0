"""Prompt builders for the 4 mood agent skills."""
from shared.db import fetch_mood_logs
from shared.vector import search_memories


def _format_mood(r: dict) -> str:
    date = r["recorded_at"].date()
    time = r["recorded_at"].strftime("%H:%M")
    d = r.get("data", {})
    fields = [
        ("mood_score", "", d.get("mood_score")),
        ("energy", "", d.get("energy")),
        ("stress", "", d.get("stress")),
        ("valence", "", d.get("valence")),
    ]
    parts = [f"{label}={value}{unit}" for label, unit, value in fields if value is not None]
    tags = d.get("tags") or []
    if tags:
        parts.append(f"tags=[{', '.join(tags)}]")
    text = d.get("raw_text") or ""
    raw = f' "{text[:60]}"' if text else ""
    return f"- {date} {time} | " + " | ".join(parts) + raw


_LOG_MOOD_INSTRUCTIONS = """You are a mood logging assistant. The user just sent a message describing
how they feel. Extract the following fields and respond with STRICT JSON only —
no prose, no markdown fences, no keys beyond the schema below.

Schema:
{
  "mood_score": integer 1-10 or null,    // general "how am I" score
  "energy":     integer 1-10 or null,    // energy / tiredness
  "stress":     integer 1-10 or null,    // stress / anxiety
  "valence":    "pos" | "neu" | "neg" | null,
  "tags":       [lowercase strings],     // free vocabulary, max 6 tags
  "summary":    short 1-line paraphrase
}

Rules:
- If the message does NOT express a mood or feeling, set every numeric field and valence to null and return tags=[] and summary="no mood signal".
- Never guess numeric values when the text is ambiguous — prefer null over a made-up number.
- tags are short lowercase descriptors like "anxiety", "focused", "tired", "calm", "lonely", "productive".
"""


_SYSTEM_TEMPLATE = """You are a personal mood and journal assistant. You have access to the user's
recent mood history and relevant memories from past sessions.

## Recent mood entries (latest 30):
{history}

## Relevant memories:
{memories}

## User request:
Task: {task}
Params: {params}
"""


async def build_mood_prompt(task: str, params: dict) -> str:
    history_rows = await fetch_mood_logs(limit=30)
    memories = await search_memories(task, limit=5)

    history_text = "\n".join(_format_mood(r) for r in history_rows) \
        or "No mood entries yet."

    memories_text = "\n".join(f"- {m.get('text', '')}" for m in memories) \
        or "No relevant memories."

    base = _SYSTEM_TEMPLATE.format(
        history=history_text,
        memories=memories_text,
        task=task,
        params=params,
    )

    if task == "log_mood":
        return base + "\n" + _LOG_MOOD_INSTRUCTIONS

    if task == "analyze_mood":
        if not history_rows:
            return base + "\nThere are not enough mood entries to analyze. Tell the user to log a few days first."
        return base + (
            "\nRespond in the user's language with: (1) 7-day trend (score/energy/stress), "
            "(2) dominant valence, (3) top 3 tags, (4) one concrete observation. "
            "Keep it to 4-6 lines. Plain text, no markdown."
        )

    if task == "get_recommendations":
        if not history_rows:
            return base + "\nThere is no mood history. Ask the user to log a few entries so you can recommend based on actual data."
        return base + (
            "\nRespond in the user's language with 2-3 short actionable recommendations "
            "based on the recent pattern. Be concrete, not generic. Plain text, no markdown."
        )

    if task == "coach_session":
        return base + (
            "\nThe params contain a completed coach-session transcript. Produce a 3-line "
            "plain-text summary of what the user worked through. Then on a new block labelled "
            "EXTRACT: emit the same strict JSON schema as log_mood summarizing the session."
        )

    return base
