"""A change an agent proposes instead of making it; the orchestrator asks the user first."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

MAX_SUMMARY = 500


@dataclass(frozen=True, slots=True)
class Proposal:
    action: str  # e.g. "calendar.delete", "home.call_tool"
    summary: str  # the confirmation card text, already in the user's language
    payload: Mapping[str, object]  # everything the agent's apply skill needs, nothing secret


def to_data(proposal: Proposal) -> dict[str, object]:
    return {
        "kind": "proposal",
        "action": proposal.action,
        "summary": proposal.summary,
        "payload": dict(proposal.payload),
    }


def from_data(data: Mapping[str, object] | None) -> Proposal | None:
    if not isinstance(data, Mapping) or data.get("kind") != "proposal":
        return None
    action, summary, payload = data.get("action"), data.get("summary"), data.get("payload")
    if not isinstance(action, str) or not action:
        return None
    if not isinstance(summary, str) or not summary or len(summary) > MAX_SUMMARY:
        return None
    if not isinstance(payload, Mapping):
        return None
    return Proposal(action=action, summary=summary, payload=dict(payload))
