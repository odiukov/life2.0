"""Prompt builders for each medication skill."""
from __future__ import annotations

from shared.grounding import GROUNDING_RULES
from shared.peer_chip_rules import PEER_CHIP_RULES
from shared.personas import IDENTITY, VOCAB


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
    if skill_id == "log_medication":
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
        peer = params.get("peer_artifacts") or {}
        peer_section = ""
        if peer:
            chunks = []
            for name in ("mood", "sleep", "recovery"):
                text = peer.get(name)
                if text and text.strip() and text != "(данные недоступны)":
                    chunks.append(f"### {name}\n{text}")
            if chunks:
                peer_section = "\n## Peer context\n" + "\n\n".join(chunks)
        chip_block = f"\n{PEER_CHIP_RULES}" if peer_section else ""
        return (
            f"{IDENTITY['medication']}\n\n"
            f"## Adherence window: last {window} days\n"
            f"## Per-medication summary (JSON: name, schedule, actual_logs)\n"
            f"{params.get('data', '[]')}\n"
            f"{peer_section}\n\n"
            f"## Vocabulary you may invoke (only when grounded by data)\n"
            f"{VOCAB['medication']}\n\n"
            f"## User request\n"
            f"Asked: {message}\n"
            f"{chip_block}\n"
            "Respond in 4–6 lines plain text: adherence rate per medication, "
            "miss streaks, dose-timing pattern. Redirect mood / sleep / "
            "recovery effects to the relevant peer. No markdown.\n\n"
            + GROUNDING_RULES
        )
    raise ValueError(f"unknown skill_id: {skill_id}")
