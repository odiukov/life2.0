"""Income, spending, balance and runway per currency. Currencies are never converted."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo

CENT = Decimal("0.01")


@dataclass(frozen=True, slots=True)
class Transaction:
    txn_id: str
    ts: datetime
    direction: Literal["IN", "OUT"]
    amount: Decimal
    currency: str
    description: str
    category: str | None


@dataclass(frozen=True, slots=True)
class Runway:
    balance: Decimal
    avg_daily_burn: Decimal
    days: int | None


def _sum(rows: Iterable[Transaction], direction: str) -> dict[str, Decimal]:
    out: dict[str, Decimal] = {}
    for r in rows:
        if r.direction == direction:
            out[r.currency] = out.get(r.currency, Decimal(0)) + r.amount
    return {k: v.quantize(CENT) for k, v in out.items()}


def income(rows: Iterable[Transaction]) -> dict[str, Decimal]:
    return _sum(rows, "IN")


def spending(rows: Iterable[Transaction]) -> dict[str, Decimal]:
    return _sum(rows, "OUT")


def spending_by_category(rows: Iterable[Transaction]) -> list[tuple[str, str, Decimal]]:
    acc: dict[tuple[str, str], Decimal] = {}
    for r in rows:
        if r.direction == "OUT" and r.category:
            key = (r.category, r.currency)
            acc[key] = acc.get(key, Decimal(0)) + r.amount
    items = [(cat, cur, amount.quantize(CENT)) for (cat, cur), amount in acc.items()]
    items.sort(key=lambda t: t[2], reverse=True)
    return items


def balance(rows: Iterable[Transaction]) -> dict[str, Decimal]:
    out: dict[str, Decimal] = {}
    for r in rows:
        delta = r.amount if r.direction == "IN" else -r.amount
        out[r.currency] = out.get(r.currency, Decimal(0)) + delta
    return {k: v.quantize(CENT) for k, v in out.items()}


def runway(
    all_rows: Iterable[Transaction], window_rows: Iterable[Transaction], window_days: int = 30
) -> dict[str, Runway]:
    burn = spending(window_rows)
    out: dict[str, Runway] = {}
    for currency, bal in balance(all_rows).items():
        total = burn.get(currency, Decimal(0))
        if total == 0:
            out[currency] = Runway(bal, Decimal(0), None)
            continue
        avg = (total / Decimal(window_days)).quantize(CENT)
        days = int((bal / avg).to_integral_value()) if avg > 0 else None
        out[currency] = Runway(bal, avg, days)
    return out


def month_of(ts: datetime, zone: ZoneInfo) -> str:
    return ts.astimezone(zone).strftime("%Y-%m")


def month_bounds(month: str, zone: ZoneInfo) -> tuple[datetime, datetime]:
    year, number = (int(part) for part in month.split("-"))
    start = datetime(year, number, 1, tzinfo=zone)
    end = datetime(year + number // 12, number % 12 + 1, 1, tzinfo=zone)
    return start.astimezone(UTC), end.astimezone(UTC)
