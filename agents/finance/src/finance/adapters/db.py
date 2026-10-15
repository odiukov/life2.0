"""Finance repositories over Postgres; RLS scopes every row to the tenant."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from typing import Any
from uuid import UUID

from shared.schema.tables import finance_category_cache as cache_table
from shared.schema.tables import finance_transactions as txn
from sqlalchemy import RowMapping, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncConnection

from finance.application.ports import CategoryCache, TransactionRepository
from finance.domain.figures import Transaction
from finance.domain.statement import StatementRow

SOURCE = "payoneer_pdf"
_COLUMNS = (
    txn.c.txn_id,
    txn.c.ts,
    txn.c.direction,
    txn.c.amount,
    txn.c.currency,
    txn.c.description,
    txn.c.category,
)


def _transaction(r: RowMapping) -> Transaction:
    return Transaction(
        r.txn_id, r.ts, r.direction, r.amount, r.currency, r.description or "", r.category
    )


class SqlTransactions:
    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    async def add_new(self, user_id: UUID, rows: Sequence[StatementRow]) -> int:
        if not rows:
            return 0
        statement = (
            insert(txn)
            .values(
                [
                    {
                        "user_id": user_id,
                        "txn_id": r.txn_id,
                        "ts": r.ts,
                        "direction": r.direction,
                        "amount": r.amount,
                        "currency": r.currency,
                        "description": r.description,
                        "source": SOURCE,
                        "raw": dict(r.raw),
                    }
                    for r in rows
                ]
            )
            .on_conflict_do_nothing(index_elements=[txn.c.user_id, txn.c.txn_id])
            .returning(txn.c.txn_id)
        )
        return len((await self._conn.execute(statement)).all())

    async def uncategorized(self, user_id: UUID, txn_ids: Sequence[str]) -> dict[str, str]:
        if not txn_ids:
            return {}
        result = await self._conn.execute(
            select(txn.c.txn_id, txn.c.description).where(
                txn.c.user_id == user_id, txn.c.txn_id.in_(list(txn_ids)), txn.c.category.is_(None)
            )
        )
        return {r.txn_id: r.description or "" for r in result}

    async def set_categories(self, user_id: UUID, categories: Mapping[str, str]) -> None:
        for txn_id, category in categories.items():
            await self._conn.execute(
                update(txn)
                .where(txn.c.user_id == user_id, txn.c.txn_id == txn_id)
                .values(category=category)
            )

    async def between(self, user_id: UUID, start: datetime, end: datetime) -> list[Transaction]:
        result = await self._conn.execute(
            select(*_COLUMNS)
            .where(txn.c.user_id == user_id, txn.c.ts >= start, txn.c.ts < end)
            .order_by(txn.c.ts, txn.c.txn_id)
        )
        return [_transaction(r) for r in result.mappings()]

    async def all(self, user_id: UUID) -> list[Transaction]:
        result = await self._conn.execute(
            select(*_COLUMNS).where(txn.c.user_id == user_id).order_by(txn.c.ts, txn.c.txn_id)
        )
        return [_transaction(r) for r in result.mappings()]


class SqlCategoryCache:
    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    async def get(self, user_id: UUID, keys: Sequence[str]) -> dict[str, str]:
        if not keys:
            return {}
        result = await self._conn.execute(
            select(cache_table.c.desc_key, cache_table.c.category).where(
                cache_table.c.user_id == user_id, cache_table.c.desc_key.in_(list(keys))
            )
        )
        return {r.desc_key: r.category for r in result}

    async def put(self, user_id: UUID, categories: Mapping[str, str]) -> None:
        if not categories:
            return
        statement = insert(cache_table).values(
            [{"user_id": user_id, "desc_key": k, "category": v} for k, v in categories.items()]
        )
        await self._conn.execute(
            statement.on_conflict_do_update(
                index_elements=[cache_table.c.user_id, cache_table.c.desc_key],
                set_={
                    "category": statement.excluded.category,
                    "updated_at": statement.excluded.updated_at,
                },
            )
        )


def finance_repositories() -> dict[type[Any], Callable[[AsyncConnection], Any]]:
    return {TransactionRepository: SqlTransactions, CategoryCache: SqlCategoryCache}
