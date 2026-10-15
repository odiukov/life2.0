"""Payoneer monthly statements (text layer). Ported unchanged from the legacy orchestrator.

The table is a stream of 5-line groups after the header "Date / Description / Amount / Currency /
Running Balance". There is no transaction id in the PDF; a deterministic one is derived from the
period, the row and the running balance, so re-uploads are idempotent.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Literal

Direction = Literal["IN", "OUT"]
_TABLE_HEADER = ("Date", "Description", "Amount", "Currency", "Running Balance")
_FOOTER_PREFIX = "©"
_MARKER = "Account Statement"


class NotAStatement(Exception):
    """The text is not a Payoneer account statement."""


@dataclass(frozen=True, slots=True)
class StatementRow:
    txn_id: str
    ts: datetime
    direction: Direction
    amount: Decimal  # always positive; the direction carries the sign
    currency: str
    description: str
    raw: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class ParsedStatement:
    rows: tuple[StatementRow, ...]
    skipped: int


def _clean_lines(text: str) -> list[str]:
    return [
        s for line in text.splitlines() if (s := line.strip()) and not s.startswith(_FOOTER_PREFIX)
    ]


def _find_table_start(lines: list[str]) -> int | None:
    width = len(_TABLE_HEADER)
    for i in range(len(lines) - width + 1):
        if tuple(lines[i : i + width]) == _TABLE_HEADER:
            return i + width
    return None


def _find_period(lines: list[str], limit: int) -> str:
    for i in range(min(limit, len(lines) - 1)):
        if lines[i] == "Period":
            return lines[i + 1]
    return ""


def _amount(raw: str) -> Decimal:
    return Decimal(raw.replace(",", "").replace(" ", "").strip())


def _txn_id(
    period: str, day: str, desc: str, amount: Decimal, currency: str, running: Decimal
) -> str:
    key = f"{period}|{day}|{desc}|{amount}|{currency}|{running}"
    return "pyn-pdf-" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def parse_statement_text(text: str) -> ParsedStatement:
    lines = _clean_lines(text)
    if not any(line.startswith(_MARKER) for line in lines[:30]):
        raise NotAStatement("missing marker")
    start = _find_table_start(lines)
    if start is None:
        raise NotAStatement("missing table header")
    period = _find_period(lines, limit=start)
    rows: list[StatementRow] = []
    skipped = 0
    i = start
    while i + 4 < len(lines):
        day, desc, amount_raw, currency, running_raw = lines[i : i + 5]
        i += 5
        try:
            ts = datetime.strptime(day, "%d %b, %Y").replace(tzinfo=UTC)
            amount = _amount(amount_raw)
            running = _amount(running_raw)
        except (ValueError, InvalidOperation):
            skipped += 1
            continue
        absolute = abs(amount)
        rows.append(
            StatementRow(
                txn_id=_txn_id(period, day, desc, absolute, currency, running),
                ts=ts,
                direction="IN" if amount >= 0 else "OUT",
                amount=absolute,
                currency=currency,
                description=desc,
                raw={
                    "date": day,
                    "amount": amount_raw,
                    "currency": currency,
                    "running_balance": running_raw,
                    "period": period,
                },
            )
        )
    return ParsedStatement(tuple(rows), skipped)
