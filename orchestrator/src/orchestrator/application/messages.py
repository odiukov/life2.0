from __future__ import annotations

from shared.ports.translator import Translator

FAILURES = frozenset(
    {
        "changed_since_proposal",
        "connection_changed",
        "household_changed",
        "home_unavailable",
        "calendar_unavailable",
        "not_connected",
        "rejected_by_home",
        "rejected_by_google",
        "not_found",
        "agent_unavailable",
    }
)


def failure(tr: Translator, locale: str, code: str | None) -> str:
    return tr.t(f"actions.failed.{code}" if code in FAILURES else "actions.failed.generic", locale)
