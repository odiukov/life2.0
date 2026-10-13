from __future__ import annotations

from datetime import date
from typing import Literal, Protocol

DateStyle = Literal["short", "medium", "long"]


class Translator(Protocol):
    def t(self, key: str, locale: str, /, **params: object) -> str:
        """Localized string; a `count` param selects a plural form."""
        ...

    def number(self, value: float, locale: str, *, digits: int = 0) -> str: ...

    def date(self, value: date, locale: str, *, style: DateStyle = "medium") -> str: ...
