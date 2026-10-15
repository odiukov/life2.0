from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Protocol
from uuid import UUID

from finance.domain.figures import Transaction
from finance.domain.statement import StatementRow


class UnreadablePdf(Exception):
    """The upload is not a readable PDF (or has too many pages)."""


class PdfText(Protocol):
    def extract(self, data: bytes) -> str:
        """The text layer of every page; raises UnreadablePdf."""
        ...


class TransactionRepository(Protocol):
    async def add_new(self, user_id: UUID, rows: Sequence[StatementRow]) -> int:
        """Insert rows whose txn_id is new for this user; returns how many were inserted."""
        ...

    async def uncategorized(self, user_id: UUID, txn_ids: Sequence[str]) -> dict[str, str]:
        """txn_id → description for those of txn_ids that still have no category."""
        ...

    async def set_categories(self, user_id: UUID, categories: Mapping[str, str]) -> None: ...

    async def between(self, user_id: UUID, start: datetime, end: datetime) -> list[Transaction]:
        """start <= ts < end, oldest first."""
        ...

    async def all(self, user_id: UUID) -> list[Transaction]:
        """Every transaction, oldest first."""
        ...


class CategoryCache(Protocol):
    async def get(self, user_id: UUID, keys: Sequence[str]) -> dict[str, str]: ...

    async def put(self, user_id: UUID, categories: Mapping[str, str]) -> None: ...
