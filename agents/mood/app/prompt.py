"""Prompt builders for the 5 mood agent skills."""
from uuid import UUID

from shared.db import fetch_mood_logs
from shared.grounding import GROUNDING_RULES
from shared.peer_chip_rules import PEER_CHIP_RULES
from shared.personas import IDENTITY, VOCAB
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


async def build_mood_prompt(
    task: str,
    params: dict,
    peer_artifacts: dict | None = None,
) -> str:
    user_id = UUID(params["user_id"])
    history_rows = await fetch_mood_logs(user_id, limit=30)
    memories = await search_memories(user_id, task, limit=5)

    history_text = "\n".join(_format_mood(r) for r in history_rows) \
        or "No mood entries yet."
    memories_text = "\n".join(f"- {m.get('text', '')}" for m in memories) \
        or "No relevant memories."

    peer = peer_artifacts if peer_artifacts is not None else (params.get("peer_artifacts") or {})
    peer_section = ""
    if peer:
        chunks = []
        for name in ("sleep", "recovery", "workout", "habits", "medication"):
            text = peer.get(name)
            if text and text.strip() and text != "(данные недоступны)":
                chunks.append(f"### {name}\n{text}")
        if chunks:
            peer_section = "\n## Peer context\n" + "\n\n".join(chunks)
    chip_block = f"\n{PEER_CHIP_RULES}" if peer_section else ""

    base = (
        f"{IDENTITY['mood']}\n\n"
        f"## Recent mood entries (latest 30)\n{history_text}\n"
        f"{peer_section}\n\n"
        f"## Vocabulary you may invoke (only when grounded by data)\n"
        f"{VOCAB['mood']}\n\n"
        f"## Memories\n{memories_text}\n\n"
        f"## User request\n"
        f"Task: {task}\n"
        f"Params: {params}\n"
        f"{chip_block}"
    )

    # Inline branched tails (vs the _SKILL_TAIL table used in
    # sleep/workout/body/nutrition): each branch here has its own empty-state
    # handling that returns a special message when history is missing. A flat
    # table can't express "if no data, return special message" — so the inline
    # form is the right fit and is kept by design (see review notes).

    if task == "log_mood":
        # log_mood is a JSON-emitting parser — keep its structured tail.
        # Persona prefix is harmless because the LOG_MOOD_INSTRUCTIONS
        # below explicitly instructs strict JSON output.
        return base + "\n" + _LOG_MOOD_INSTRUCTIONS

    if task == "analyze_mood":
        if not history_rows:
            return base + (
                "\nThere are not enough mood entries to analyze. Tell the "
                "user to log a few days first.\n\n" + GROUNDING_RULES
            )
        return base + (
            "\nRespond in 6–10 lines plain text: (1) 7-day trend "
            "(score/energy/stress) grounded in the data, (2) dominant "
            "valence + top 3 tags, (3) one mechanism (e.g. mood–energy "
            "decoupling, diurnal pattern). Redirect cross-domain prescriptions "
            "to peers. No markdown.\n\n" + GROUNDING_RULES
        )

    if task == "get_mood_recommendations":
        if not history_rows:
            return base + (
                "\nThere is no mood history. Ask the user to log a few "
                "entries so you can recommend based on actual data.\n\n"
                + GROUNDING_RULES
            )
        return base + (
            "\nRespond in 4–6 lines plain text with 2–3 concrete mood-domain "
            "actions + the 'why' grounded in the recent pattern. Redirect "
            "training, sleep, or medication asks to the relevant peer. "
            "No markdown.\n\n" + GROUNDING_RULES
        )

    if task == "coach_session":
        return base + (
            "\nThe params contain a completed coach-session transcript. "
            "Produce a 3-line plain-text summary of what the user worked "
            "through. Then on a new block labelled EXTRACT: emit the same "
            "strict JSON schema as log_mood summarizing the session.\n\n"
            + GROUNDING_RULES
        )

    return base + "\n\n" + GROUNDING_RULES
