"""Tests for shared.i18n — JSON bundle reader + interpolation."""
from __future__ import annotations

from shared.i18n import t, _interpolate


def test_returns_ru_string_for_known_key():
    assert t("tabs.today", locale="ru") == "Сегодня"


def test_returns_en_string_for_known_key():
    assert t("tabs.today", locale="en") == "Today"


def test_returns_key_when_not_found_in_either_bundle():
    assert t("nonexistent.deep.key") == "nonexistent.deep.key"


def test_falls_back_to_en_when_missing_in_ru():
    # _test.enOnly exists in en.json only (added in Task 1's fix commit).
    # Locale RU must fall back through EN.
    assert t("_test.enOnly", locale="ru") == "Englishfallback"


def test_returns_localized_string_when_present_in_target_bundle():
    assert t("tabs.today", locale="ru") == "Сегодня"


def test_interpolates_named_params():
    assert _interpolate("hello {name}", {"name": "world"}) == "hello world"
    assert _interpolate("a={a} b={b}", {"a": 1, "b": "x"}) == "a=1 b=x"


def test_interpolation_leaves_unknown_placeholders():
    assert _interpolate("hello {name}", {}) == "hello {name}"


def test_t_with_params_interpolates():
    assert t("_test.greeting", locale="en", name="world") == "Hi world"
