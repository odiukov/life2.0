"""Categorize new transactions: the per-user cache first, the model for the rest."""

from __future__ import annotations

from collections.abc import Mapping
from uuid import UUID

from pydantic import BaseModel
from shared.observability.logging import get_logger
from shared.ports.llm import LLMError, LLMProvider, LLMTask
from shared.ports.uow import UnitOfWorkFactory

from finance.application.ports import CategoryCache, TransactionRepository
from finance.domain.categories import CATEGORIES, Category, desc_key

BATCH_SIZE = 50
logger = get_logger(__name__)

SYSTEM = (
    "Classify each merchant description into exactly ONE of these categories: "
    + ", ".join(CATEGORIES)
    + ".\nRules:\n"
    "- 'income' for incoming client payments.\n"
    "- 'transfer' for moving money between the user's own accounts.\n"
    "- 'fee' for bank or platform fees.\n"
    "- 'other' only as a last resort.\n"
    "Return one item per listed key, using the key exactly as written."
)


class CategoryChoice(BaseModel):
    key: str
    category: Category


class CategoryBatch(BaseModel):
    items: list[CategoryChoice]


class Categorizer:
    def __init__(
        self, *, llm: LLMProvider, uow: UnitOfWorkFactory, batch_size: int = BATCH_SIZE
    ) -> None:
        self._llm = llm
        self._uow = uow
        self._batch = batch_size

    async def __call__(self, user_id: UUID, descriptions: Mapping[str, str]) -> int:
        """Best effort: rows the model cannot classify stay uncategorized for the next upload."""
        if not descriptions:
            return 0
        key_by_txn = {txn: desc_key(desc) for txn, desc in descriptions.items()}
        keys = sorted(set(key_by_txn.values()))
        example: dict[str, str] = {}
        for txn, key in key_by_txn.items():
            example.setdefault(key, descriptions[txn])
        async with self._uow.for_user(user_id) as tx:
            cached = await tx.repo(CategoryCache).get(user_id, keys)
        found = dict(cached)
        missing = [k for k in keys if k not in cached]
        for i in range(0, len(missing), self._batch):
            chunk = missing[i : i + self._batch]
            listing = "\n".join(f"- {k}: {example[k]}" for k in chunk)
            try:
                result = await self._llm.structured(
                    task=LLMTask.FAST, system=SYSTEM, user=listing, schema=CategoryBatch
                )
            except LLMError as exc:
                logger.warning("finance_categorize_failed", error_type=type(exc).__name__)
                continue
            wanted = set(chunk)
            for item in result.items:
                if item.key in wanted:
                    found[item.key] = item.category
        learned = {k: v for k, v in found.items() if k not in cached}
        updates = {txn: found[key] for txn, key in key_by_txn.items() if key in found}
        if learned or updates:
            async with self._uow.for_user(user_id) as tx:
                await tx.repo(CategoryCache).put(user_id, learned)
                await tx.repo(TransactionRepository).set_categories(user_id, updates)
        return len(updates)
