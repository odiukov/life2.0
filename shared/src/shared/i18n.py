"""i18n bundle reader shared between Python services and the JS monorepo.

Single source of truth: packages/i18n/locales/{en,ru}.json. Python and TS
consumers read the same files. Keys are dot-paths into nested objects.
Lookup order: requested locale → EN fallback → key string verbatim.
Interpolation: t('greeting', name='X') substitutes {name} → 'X'. Param values
are inserted as plain text — they are NOT escaped against containing
{otherKey} sequences. Callers must sanitize user-controlled input if more
than one param key is present.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

def _find_locales() -> Path:
    override = os.environ.get("LIFE_I18N_LOCALES_DIR")
    if override:
        return Path(override)
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "packages" / "i18n" / "locales"
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError(f"packages/i18n/locales not found above {here}")


_ROOT = _find_locales()


@lru_cache(maxsize=4)
def _bundle(locale: str) -> dict[str, Any]:
    path = _ROOT / f"{locale}.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _lookup(bundle: dict[str, Any], key: str) -> str | None:
    cur: Any = bundle
    for part in key.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
        if cur is None:
            return None
    return cur if isinstance(cur, str) else None


def _interpolate(template: str, params: dict[str, Any]) -> str:
    out = template
    for k, v in params.items():
        out = out.replace(f"{{{k}}}", str(v))
    return out


def t(key: str, locale: str = "ru", **params: Any) -> str:
    """Return the localized string for key, interpolating named params.

    Lookup order: locale bundle → EN bundle → key verbatim.
    """
    s = _lookup(_bundle(locale), key)
    if s is None and locale != "en":
        s = _lookup(_bundle("en"), key)
    if s is None:
        return key
    return _interpolate(s, params) if params else s
