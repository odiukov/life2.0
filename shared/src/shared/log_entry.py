"""Helper to construct the canonical `log_entry` A2A artifact.

Centralizes the shape that orchestrator's `_extract_log_entry_from_task`
(in health_agent.py) expects: an Artifact named "log_entry" with one
DataPart carrying `{summary: str, timestamp: ISO-8601 str}`.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from a2a.types import Artifact, DataPart, Part


_LOG_ENTRY_SUMMARY_MAX = 120


def _clip_summary(text: str) -> str:
    cleaned = (text or "").strip()
    if len(cleaned) <= _LOG_ENTRY_SUMMARY_MAX:
        return cleaned
    return cleaned[: _LOG_ENTRY_SUMMARY_MAX - 1] + "…"


def make_log_entry_artifact(
    summary: str, recorded_at: datetime | None = None
) -> Artifact:
    """Build a `log_entry` artifact with the canonical shape.

    `summary` is auto-clipped to 120 chars (with ellipsis) so callers can
    pass raw user input directly. `recorded_at` defaults to UTC now.
    """
    timestamp = (recorded_at or datetime.now(timezone.utc)).isoformat()
    return Artifact(
        artifact_id=str(uuid.uuid4()),
        name="log_entry",
        parts=[Part(root=DataPart(data={
            "summary": _clip_summary(summary),
            "timestamp": timestamp,
        }))],
    )
