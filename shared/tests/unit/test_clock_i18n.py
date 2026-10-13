from datetime import UTC, date
from pathlib import Path

import pytest
from shared.adapters.clock import SystemClock
from shared.adapters.i18n import JsonTranslator
from shared.config import find_locales_dir

CATALOGS = {
    "ru": {
        "items": {
            "one": "{count} продукт",
            "few": "{count} продукта",
            "many": "{count} продуктов",
            "other": "{count} продукта",
        },
        "greet": "Привет, {name}!",
    },
    "en": {
        "items": {"one": "{count} item", "other": "{count} items"},
        "greet": "Hi, {name}!",
        "only_en": "fallback works",
    },
}


def test_system_clock_is_utc_aware() -> None:
    assert SystemClock().now().tzinfo is UTC


@pytest.mark.parametrize(
    ("count", "expected"),
    [(1, "1 продукт"), (3, "3 продукта"), (5, "5 продуктов"), (21, "21 продукт")],
)
def test_russian_plurals(count: int, expected: str) -> None:
    assert JsonTranslator(CATALOGS).t("items", "ru", count=count) == expected


def test_interpolation_and_fallbacks() -> None:
    tr = JsonTranslator(CATALOGS)
    assert tr.t("greet", "ru", name="Оля") == "Привет, Оля!"
    assert tr.t("only_en", "ru") == "fallback works"
    assert tr.t("missing.key", "ru") == "missing.key"
    assert tr.t("items", "en", count=2) == "2 items"


def _spaces(text: str) -> str:
    return text.replace("\xa0", " ").replace(" ", " ")


def test_number_and_date_formatting() -> None:
    tr = JsonTranslator(CATALOGS)
    assert _spaces(tr.number(1234.56, "ru", digits=1)) == "1 234,6"
    assert tr.number(420.4, "en") == "420"
    formatted = tr.date(date(2026, 10, 13), "ru")
    assert "2026" in formatted
    assert "окт" in formatted


def test_loads_the_repo_catalogs() -> None:
    tr = JsonTranslator.from_dir(find_locales_dir())
    assert {"ru", "en"} <= set(tr.locales)


@pytest.mark.parametrize(
    ("count", "expected"),
    [(0, "0 продуктов"), (11, "11 продуктов"), (22, "22 продукта"), (1.5, "1.5 продукта")],
)
def test_russian_plural_boundaries(count: float, expected: str) -> None:
    assert JsonTranslator(CATALOGS).t("items", "ru", count=count) == expected


def test_plural_fallback_uses_fallback_locale_rules() -> None:
    tr = JsonTranslator({"ru": {}, "en": CATALOGS["en"]})
    assert tr.t("items", "ru", count=21) == "21 items"
    assert tr.t("items", "missing", count=1) == "1 item"


def test_nested_plural_and_other_category_fallback() -> None:
    tr = JsonTranslator({"en": {"nested": {"items": {"other": "{count} items"}}}})
    assert tr.t("nested.items", "en", count=1) == "1 items"
    assert tr.t("nested", "en") == "nested"


def test_loads_utf8_catalog_and_interpolates(tmp_path: Path) -> None:
    (tmp_path / "ru.json").write_text('{"greet": "Привет, {name}!"}', encoding="utf-8")
    assert JsonTranslator.from_dir(tmp_path).t("greet", "ru", name="Оля") == "Привет, Оля!"
