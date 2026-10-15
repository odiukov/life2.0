from __future__ import annotations

from decimal import Decimal

_SYMBOLS = {"USD": "$", "EUR": "€", "GBP": "£"}


def format_amount(currency: str, amount: Decimal, sign: str = "") -> str:
    """'+$4 000.00 USD' — the legacy upload-summary format (thin-space-free, plain spaces)."""
    body = f"{amount:,.2f}".replace(",", " ")
    symbol = _SYMBOLS.get(currency, "")
    return f"{sign}{symbol}{body} {currency}"
