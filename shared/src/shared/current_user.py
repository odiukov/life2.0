"""User identity resolution for A2A peer calls.

`user_id_from_message(message)` reads A2A Message.metadata["user_id"] and
raises ValueError on missing/malformed metadata. Every peer call must
supply user_id (see shared/peer.py::call_peer).
"""
from __future__ import annotations

from uuid import UUID


async def user_id_from_message(message) -> UUID:
    """Extract user_id from A2A Message.metadata. Strict — raises rather than
    falling back to a default tenant; missing/malformed metadata is a wiring bug.
    """
    md = getattr(message, "metadata", None) or {}
    raw = md.get("user_id") if isinstance(md, dict) else None
    if not raw:
        raise ValueError("A2A Message.metadata missing user_id")
    try:
        return UUID(str(raw))
    except ValueError as e:
        raise ValueError(f"malformed user_id in Message.metadata: {raw!r}") from e
