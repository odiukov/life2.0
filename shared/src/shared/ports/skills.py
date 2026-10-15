"""Calling one structured skill of another agent and getting its result back."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class Attachment:
    """A file sent along with a skill call (A2A FilePart with inline bytes). Never logged."""

    name: str
    mime: str
    data: bytes


@dataclass(frozen=True, slots=True)
class SkillReply:
    text: str
    data: Mapping[str, object] | None


class SkillCallError(Exception):
    """The skill ran and reported failure; `code` is its machine-readable reason."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class SkillUnavailable(Exception):
    """The agent could not be reached or answered with something that is not a task."""


class SkillClient(Protocol):
    async def call(
        self,
        *,
        skill_id: str,
        user_id: UUID,
        params: Mapping[str, object],
        text: str = "",
        attachments: Sequence[Attachment] = (),
    ) -> SkillReply: ...
