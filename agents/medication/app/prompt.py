"""Prompt builders for each medication skill."""
from __future__ import annotations


async def build_medication_prompt(skill_id: str, params: dict) -> str:
    message = params.get("message", "")
    if skill_id == "define_medication":
        return (
            "Extract a medication definition from the user message. "
            "Respond with strict JSON, no prose, keys: "
            '{"name": str (lowercase kebab-case, single token), '
            '"dose": str | null, '
            '"schedule": str (free-text, e.g. "daily 21:00" or "mon,wed,fri morning"), '
            '"notes": str | null}. '
            "If a field is unknown, use null.\n\n"
            f"User message: {message}"
        )
    if skill_id == "log_taken":
        return (
            "The user just took a medication. Extract only the name as a "
            "lowercase kebab-case single token. Respond with strict JSON: "
            '{"name": str}. '
            "If the message contains no medication name, respond "
            '{"name": null}.\n\n'
            f"User message: {message}"
        )
    if skill_id == "list_active":
        return "no LLM input needed — deterministic path."
    if skill_id == "archive_medication":
        return "no LLM input needed — deterministic path."
    if skill_id == "analyze_adherence":
        window = params.get("window_days", 14)
        return (
            f"Summarise medication adherence over the last {window} days. "
            "Input below is JSON with per-medication expected and actual counts. "
            "Return 2-4 concise sentences focusing on misses and streaks.\n\n"
            f"Data: {params.get('data', '[]')}\n\n"
            f"User asked: {message}"
        )
    raise ValueError(f"unknown skill_id: {skill_id}")
