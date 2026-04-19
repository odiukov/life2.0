"""Read-only finance queries backed by SQL on finance_transactions.

Currency is never converted — aggregations are keyed per-currency dicts.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from shared.db import (
    finance_rows_all,
    finance_rows_for_month,
    finance_rows_in_window,
)


async def income_for_month(month_str: str) -> dict[str, Decimal]:
    """Sum of IN amounts for the calendar month, per currency.

    `month_str` is `YYYY-MM` (e.g. "2026-04").
    """
    rows = await finance_rows_for_month(month_str)
    out: dict[str, Decimal] = {}
    for r in rows:
        if r["direction"] != "IN":
            continue
        cur = r["currency"]
        out[cur] = out.get(cur, Decimal("0")) + r["amount"]
    return {k: v.quantize(Decimal("0.01")) for k, v in out.items()}


async def spending_by_category(
    month_str: str,
) -> list[tuple[str, str, Decimal]]:
    """List of (category, currency, amount) for OUT rows with non-null
    category in a given calendar month. Sorted by amount desc."""
    rows = await finance_rows_for_month(month_str)
    acc: dict[tuple[str, str], Decimal] = {}
    for r in rows:
        if r["direction"] != "OUT":
            continue
        cat = r["category"]
        if not cat:
            continue
        key = (cat, r["currency"])
        acc[key] = acc.get(key, Decimal("0")) + r["amount"]
    items = [(cat, cur, amt.quantize(Decimal("0.01"))) for (cat, cur), amt in acc.items()]
    items.sort(key=lambda t: t[2], reverse=True)
    return items


async def current_balance() -> dict[str, Decimal]:
    """Signed running balance per currency: sum(IN) − sum(OUT)."""
    rows = await finance_rows_all()
    out: dict[str, Decimal] = {}
    for r in rows:
        cur = r["currency"]
        amt = r["amount"]
        delta = amt if r["direction"] == "IN" else -amt
        out[cur] = out.get(cur, Decimal("0")) + delta
    return {k: v.quantize(Decimal("0.01")) for k, v in out.items()}


async def runway(avg_window_days: int = 30) -> dict[str, dict[str, Any]]:
    """Runway estimation per currency.

    Returns `{currency: {"balance": Decimal, "avg_daily_burn": Decimal, "days": int | None}}`.
    `days` is None when there's no spending in the window (avg_daily_burn == 0).
    """
    balance = await current_balance()
    window = await finance_rows_in_window(avg_window_days)

    burn: dict[str, Decimal] = {}
    for r in window:
        if r["direction"] != "OUT":
            continue
        cur = r["currency"]
        burn[cur] = burn.get(cur, Decimal("0")) + r["amount"]

    out: dict[str, dict[str, Any]] = {}
    for cur, bal in balance.items():
        total_burn = burn.get(cur, Decimal("0"))
        if total_burn == 0:
            out[cur] = {
                "balance": bal,
                "avg_daily_burn": Decimal("0"),
                "days": None,
            }
            continue
        avg = (total_burn / Decimal(avg_window_days)).quantize(Decimal("0.01"))
        days = int((bal / avg).to_integral_value()) if avg > 0 else None
        out[cur] = {"balance": bal, "avg_daily_burn": avg, "days": days}
    return out
