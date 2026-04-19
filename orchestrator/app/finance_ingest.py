"""CSV ingest + LLM categorization.

Kept separate from the parser and the queries modules so it can be mocked
cleanly in tests (see `_get_llm`). `ingest_rows` is idempotent; `categorize_new`
is best-effort and never raises — rows with failed LLM / bad JSON stay NULL
and get another chance on the next upload.
"""
from __future__ import annotations

import json
import logging
import re
from decimal import Decimal
from typing import Any

from shared.llm import build_llm
from shared.db import (
    fetch_descriptions_for,
    get_category_cache,
    set_transaction_categories,
    upsert_category_cache,
    upsert_finance_rows,
)

logger = logging.getLogger(__name__)

_BATCH_SIZE = 50
_LLM = None


def _get_llm():
    """Lazy LLM accessor — kept as a module function so tests can patch it."""
    global _LLM
    if _LLM is None:
        _LLM = build_llm()
    return _LLM


_CATEGORIES = [
    "food", "housing", "transport", "subscriptions", "software",
    "entertainment", "travel", "health", "utilities", "income",
    "transfer", "fee", "other",
]

_PROMPT_TMPL = (
    "Classify each merchant description into ONE of these categories:\n"
    + ", ".join(_CATEGORIES)
    + ".\n\n"
    "Rules:\n"
    "- 'income' for incoming client payments.\n"
    "- 'transfer' for moving money between own accounts.\n"
    "- 'fee' for bank/platform fees.\n"
    "- 'other' only as last resort.\n\n"
    "Return STRICT JSON object where the KEYS are the exact 'key' strings from\n"
    "the listing below, and values are category names. No prose, no code fences.\n\n"
    "Listing (format: `- key: example description`):\n{listing}\n"
)


_NORM_STRIP_NUM = re.compile(r"[\d\-_/]+")
_NORM_WS = re.compile(r"\s+")


def _desc_key(description: str) -> str:
    """Normalize a Payoneer description to a cache key.

    Lowercase, strip dates + numeric IDs, collapse whitespace, join words
    with hyphens. Two descriptions that differ only by dates/ids should map
    to the same key.
    """
    s = (description or "").lower()
    s = _NORM_STRIP_NUM.sub(" ", s)
    s = _NORM_WS.sub(" ", s).strip()
    s = s.replace(" ", "-")
    return s or "__empty__"


async def ingest_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """UPSERT parsed rows and return a summary of what landed.

    Result shape:
      {
        "inserted": int,
        "skipped": int,          # rows already present by txn_id
        "uncategorized_ids": list[str],
      }
    """
    inserted, skipped = await upsert_finance_rows(rows)

    from shared.db import fetch_uncategorized_ids
    uncat_all = await fetch_uncategorized_ids()
    incoming_ids = {r["txn_id"] for r in rows}
    # Only IDs from THIS upload that are uncategorized — not the full DB table.
    uncategorized = [tid for tid in uncat_all if tid in incoming_ids]
    return {
        "inserted": inserted,
        "skipped": skipped,
        "uncategorized_ids": uncategorized,
    }


async def categorize_new(uncategorized_ids: list[str]) -> None:
    """Best-effort LLM categorization for the given txn_ids.

    1. Pull descriptions.
    2. Compute desc_keys.
    3. Apply cache hits directly.
    4. Batch remaining misses to the LLM, parse JSON, upsert cache + rows.
    5. On any LLM / JSON error: log and return. Leaves rows NULL.
    """
    if not uncategorized_ids:
        return

    desc_by_id = await fetch_descriptions_for(uncategorized_ids)
    if not desc_by_id:
        return

    key_by_id = {tid: _desc_key(desc) for tid, desc in desc_by_id.items()}
    unique_keys = sorted(set(key_by_id.values()))

    cached = await get_category_cache(unique_keys)
    # Apply cache hits right away.
    cache_updates: dict[str, str] = {
        tid: cached[k] for tid, k in key_by_id.items() if k in cached
    }
    if cache_updates:
        await set_transaction_categories(cache_updates)

    missing_keys = [k for k in unique_keys if k not in cached]
    if not missing_keys:
        return

    # Keep a stable key→first-seen-description listing so the LLM has context.
    desc_for_key: dict[str, str] = {}
    for tid, k in key_by_id.items():
        if k in missing_keys and k not in desc_for_key:
            desc_for_key[k] = desc_by_id[tid]

    new_mappings: dict[str, str] = {}
    for i in range(0, len(missing_keys), _BATCH_SIZE):
        batch = missing_keys[i:i + _BATCH_SIZE]
        listing = "\n".join(f"- {k}: {desc_for_key[k]}" for k in batch)
        prompt = _PROMPT_TMPL.format(listing=listing)

        try:
            llm = _get_llm()
            resp = await llm.ainvoke(prompt)
            content = getattr(resp, "content", "")
            if isinstance(content, list):
                content = "".join(
                    b.get("text", "") for b in content
                    if isinstance(b, dict) and b.get("type") == "text"
                )
            parsed = json.loads(content.strip())
        except Exception as e:
            logger.warning("categorize_new LLM/JSON failure: %s", e)
            continue

        if not isinstance(parsed, dict):
            continue
        for k in batch:
            cat = parsed.get(k)
            if isinstance(cat, str) and cat in _CATEGORIES:
                new_mappings[k] = cat

    if new_mappings:
        await upsert_category_cache(new_mappings)
        row_updates = {
            tid: new_mappings[k]
            for tid, k in key_by_id.items() if k in new_mappings
        }
        if row_updates:
            await set_transaction_categories(row_updates)


# ---------------------------------------------------------------------------
# Upload summary formatting
# ---------------------------------------------------------------------------

_CCY_SYMBOL = {"USD": "$", "EUR": "€", "GBP": "£"}


def _fmt_amount(currency: str, amount: Decimal, sign: str = "") -> str:
    sym = _CCY_SYMBOL.get(currency, "")
    if sym:
        body = f"{sym}{amount:,.2f}".replace(",", " ")
        return f"{sign}{body} {currency}" if sign else f"{body} {currency}"
    body = f"{amount:,.2f}".replace(",", " ")
    return f"{sign}{body} {currency}"


def build_upload_summary(
    *,
    inserted: int,
    skipped: int,
    income_by_currency: dict[str, Decimal],
    spending_by_currency: dict[str, Decimal],
    top_categories: list[tuple[str, Decimal, str]],
) -> str:
    """Build Telegram-ready summary string from ingest + query outputs."""
    parts: list[str] = []
    parts.append(f"✓ CSV обработан ({inserted} новых, {skipped} пропущено)")

    if income_by_currency:
        items = [_fmt_amount(c, v, sign="+") for c, v in sorted(income_by_currency.items())]
        parts.append("Пришло: " + ", ".join(items))
    if spending_by_currency:
        items = [_fmt_amount(c, v, sign="−") for c, v in sorted(spending_by_currency.items())]
        parts.append("Ушло: " + ", ".join(items))

    if top_categories:
        bits = [
            f"{name} {_fmt_amount(currency, amount)}"
            for name, amount, currency in top_categories
        ]
        parts.append("Топ категории: " + " · ".join(bits))

    return "\n".join(parts)
