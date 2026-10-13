from __future__ import annotations

from pathlib import Path


def find_locales_dir(start: Path | None = None) -> Path:
    """First packages/i18n/locales directory above start (default: this file)."""
    here = (start or Path(__file__)).resolve()
    for parent in [here, *here.parents]:
        candidate = parent / "packages" / "i18n" / "locales"
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError(f"packages/i18n/locales not found above {here}")
