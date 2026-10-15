"""In-memory repositories with the same contract as the SQL ones (see tests/contract)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any
from uuid import UUID

from shared.ports.health_logs import HealthLogRepository
from shared.ports.users import UserSettingsRepository
from shared.testing.fakes import InMemoryHealthLogs, InMemoryUnitOfWorkFactory, InMemoryUserSettings

from finance.application.ports import CategoryCache, PdfText, TransactionRepository, UnreadablePdf
from finance.domain.figures import Transaction
from finance.domain.statement import StatementRow


class InMemoryTransactions:
    def __init__(self) -> None:
        self.rows: dict[UUID, dict[str, Transaction]] = {}

    async def add_new(self, user_id: UUID, rows: Sequence[StatementRow]) -> int:
        mine = self.rows.setdefault(user_id, {})
        added = 0
        for r in rows:
            if r.txn_id not in mine:
                mine[r.txn_id] = Transaction(
                    r.txn_id, r.ts, r.direction, r.amount, r.currency, r.description, None
                )
                added += 1
        return added

    async def uncategorized(self, user_id: UUID, txn_ids: Sequence[str]) -> dict[str, str]:
        mine = self.rows.get(user_id, {})
        return {t: mine[t].description for t in txn_ids if t in mine and mine[t].category is None}

    async def set_categories(self, user_id: UUID, categories: Mapping[str, str]) -> None:
        mine = self.rows.get(user_id, {})
        for txn, category in categories.items():
            if txn in mine:
                old = mine[txn]
                mine[txn] = Transaction(
                    old.txn_id,
                    old.ts,
                    old.direction,
                    old.amount,
                    old.currency,
                    old.description,
                    category,
                )

    async def between(self, user_id: UUID, start: datetime, end: datetime) -> list[Transaction]:
        return sorted(
            (t for t in self.rows.get(user_id, {}).values() if start <= t.ts < end),
            key=lambda t: (t.ts, t.txn_id),
        )

    async def all(self, user_id: UUID) -> list[Transaction]:
        return sorted(self.rows.get(user_id, {}).values(), key=lambda t: (t.ts, t.txn_id))


class InMemoryCategoryCache:
    def __init__(self) -> None:
        self.rows: dict[UUID, dict[str, str]] = {}

    async def get(self, user_id: UUID, keys: Sequence[str]) -> dict[str, str]:
        mine = self.rows.get(user_id, {})
        return {k: mine[k] for k in keys if k in mine}

    async def put(self, user_id: UUID, categories: Mapping[str, str]) -> None:
        self.rows.setdefault(user_id, {}).update(categories)


class FakePdfText:
    """Returns the given text for any upload that starts with %PDF-."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.calls = 0

    def extract(self, data: bytes) -> str:
        self.calls += 1
        if not data.startswith(b"%PDF-"):
            raise UnreadablePdf("not a pdf")
        return self.text


def in_memory_uow(
    transactions: InMemoryTransactions | None = None,
    cache: InMemoryCategoryCache | None = None,
    settings: InMemoryUserSettings | None = None,
    logs: InMemoryHealthLogs | None = None,
) -> InMemoryUnitOfWorkFactory:
    repositories: dict[type[Any], Any] = {
        TransactionRepository: transactions or InMemoryTransactions(),
        CategoryCache: cache or InMemoryCategoryCache(),
        UserSettingsRepository: settings or InMemoryUserSettings(),
        HealthLogRepository: logs or InMemoryHealthLogs(),
    }
    return InMemoryUnitOfWorkFactory(repositories)


__all__ = [
    "FakePdfText",
    "InMemoryCategoryCache",
    "InMemoryTransactions",
    "PdfText",
    "in_memory_uow",
]
