"""Typed view of an inbound A2A message."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from typing import Any
from uuid import UUID, uuid4

from a2a.server.agent_execution import RequestContext

_KNOWN_KEYS = ("skillId", "focus_sources", "is_peer_call", "for_date", "user_id", "params")


class InvalidRequest(ValueError):
    """The message cannot be served (for example, it carries no valid user_id)."""


@dataclass(frozen=True, slots=True)
class Envelope:
    task_id: str
    context_id: str
    text: str
    metadata: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class SkillRequest:
    task_id: str
    context_id: str
    text: str
    user_id: UUID
    skill_id: str
    for_date: date | None
    is_peer_call: bool
    params: Mapping[str, object] = field(default_factory=dict)

    def audit(self) -> dict[str, object]:
        """What the legacy executors stored as `tasks.input`."""
        out: dict[str, object] = {**self.params, "message": self.text, "user_id": str(self.user_id)}
        if self.for_date is not None:
            out["for_date"] = self.for_date.isoformat()
        return out


def _metadata(message: Any) -> dict[str, Any]:
    raw = getattr(message, "metadata", None)
    if isinstance(raw, Mapping):
        return dict(raw)
    if raw is None:
        return {}
    # The SDK sometimes hands over an object instead of a dict.
    return {key: getattr(raw, key, None) for key in _KNOWN_KEYS}


def _text(message: Any) -> str:
    texts = []
    for part in getattr(message, "parts", None) or []:
        root = getattr(part, "root", part)
        value = getattr(root, "text", None)
        if isinstance(value, str) and value:
            texts.append(value)
    return "\n".join(texts)


def read_envelope(context: RequestContext) -> Envelope:
    message = context.message
    return Envelope(
        task_id=context.task_id or str(uuid4()),
        context_id=context.context_id or str(uuid4()),
        text=_text(message) if message is not None else "",
        metadata=_metadata(message) if message is not None else {},
    )


def requested_skill(metadata: Mapping[str, Any]) -> str | None:
    value = metadata.get("skillId")
    return value if isinstance(value, str) and value else None


def focus_sources(metadata: Mapping[str, Any]) -> tuple[str, ...] | None:
    value = metadata.get("focus_sources")
    if not isinstance(value, list | tuple):
        return None
    return tuple(item for item in value if isinstance(item, str))


def _for_date(metadata: Mapping[str, Any]) -> date | None:
    value = metadata.get("for_date")
    if not isinstance(value, str) or not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def to_request(envelope: Envelope, *, skill_id: str) -> SkillRequest:
    raw = envelope.metadata.get("user_id")
    if raw is None or raw == "":
        raise InvalidRequest("A2A Message.metadata missing user_id")
    if not isinstance(raw, str | UUID):
        raise InvalidRequest("malformed user_id in Message.metadata")
    try:
        user_id = raw if isinstance(raw, UUID) else UUID(raw)
    except ValueError as exc:
        raise InvalidRequest("malformed user_id in Message.metadata") from exc
    params = envelope.metadata.get("params")
    return SkillRequest(
        task_id=envelope.task_id,
        context_id=envelope.context_id,
        text=envelope.text,
        user_id=user_id,
        skill_id=skill_id,
        for_date=_for_date(envelope.metadata),
        # Strict identity with True: wire-level "true" or stale flags must not activate it.
        is_peer_call=envelope.metadata.get("is_peer_call") is True,
        params=dict(params) if isinstance(params, Mapping) else {},
    )
