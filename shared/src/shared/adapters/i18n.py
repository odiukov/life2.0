"""Translator over the JSON catalogs shared with the mobile app (packages/i18n/locales)."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import date
from pathlib import Path

from babel import Locale
from babel.dates import format_date
from babel.numbers import format_decimal

from shared.ports.translator import DateStyle

PLURAL_FORMS = frozenset({"zero", "one", "two", "few", "many", "other"})


class JsonTranslator:
    def __init__(
        self, catalogs: Mapping[str, Mapping[str, object]], *, fallback: str = "en"
    ) -> None:
        self._catalogs = catalogs
        self._fallback = fallback

    @classmethod
    def from_dir(cls, path: Path) -> JsonTranslator:
        catalogs = {
            file.stem: json.loads(file.read_text(encoding="utf-8"))
            for file in sorted(path.glob("*.json"))
        }
        return cls(catalogs)

    @property
    def locales(self) -> frozenset[str]:
        return frozenset(self._catalogs)

    def t(self, key: str, locale: str, /, **params: object) -> str:
        used = locale
        entry = self._lookup(locale, key)
        if entry is None:
            used = self._fallback
            entry = self._lookup(self._fallback, key)
        if isinstance(entry, Mapping) and entry and set(entry) <= PLURAL_FORMS:
            count = params.get("count")
            number = count if isinstance(count, int | float) else 1
            form = Locale.parse(used).plural_form(number)
            entry = entry.get(form, entry.get("other"))
        if not isinstance(entry, str):
            return key
        for name, value in params.items():
            entry = entry.replace(f"{{{name}}}", str(value))
        return entry

    def number(self, value: float, locale: str, *, digits: int = 0) -> str:
        pattern = "#,##0" + ("." + "0" * digits if digits > 0 else "")
        return format_decimal(value, format=pattern, locale=locale)

    def date(self, value: date, locale: str, *, style: DateStyle = "medium") -> str:
        return format_date(value, format=style, locale=locale)

    def _lookup(self, locale: str, key: str) -> object | None:
        node: object = self._catalogs.get(locale)
        for part in key.split("."):
            if not isinstance(node, Mapping) or part not in node:
                return None
            node = node[part]
        return node
