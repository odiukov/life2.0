from __future__ import annotations

from uuid import UUID

TITLE_MAX = 120


def task_key(user_id: UUID, task_id: UUID) -> str:
    """The checkpoint thread id. RLS on the checkpoint tables matches its user prefix."""
    return f"{user_id}:{task_id}"


def title_from(text: str) -> str:
    line = " ".join(text.split())
    return line if len(line) <= TITLE_MAX else line[: TITLE_MAX - 1] + "…"
