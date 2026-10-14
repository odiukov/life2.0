"""Database roles. `app_owner` migrates, `app_rw` is tenant-scoped, `app_legacy` bypasses RLS."""

from __future__ import annotations

import re
from dataclasses import dataclass

_SAFE = re.compile(r"^[A-Za-z0-9_-]+$")
ROLES = ("app_owner", "app_rw", "app_legacy")


@dataclass(frozen=True, slots=True)
class RolePasswords:
    owner: str
    rw: str
    legacy: str


def _safe(value: str, what: str) -> str:
    if not _SAFE.fullmatch(value):
        raise ValueError(f"{what} may contain only letters, digits, '_' and '-'")
    return value


def role_statements(database: str, passwords: RolePasswords) -> list[str]:
    """Idempotent SQL, run as a superuser, that creates/updates the three roles."""
    db = _safe(database, "database name")
    owner = _safe(passwords.owner, "APP_OWNER_PASSWORD")
    rw = _safe(passwords.rw, "APP_RW_PASSWORD")
    legacy = _safe(passwords.legacy, "APP_LEGACY_PASSWORD")
    create = [
        f"DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{role}') "
        f"THEN CREATE ROLE {role} LOGIN; END IF; END $$"
        for role in ROLES
    ]
    return [
        *create,
        f"ALTER ROLE app_owner LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD '{owner}'",
        f"ALTER ROLE app_rw LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD '{rw}'",
        f"ALTER ROLE app_legacy LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION BYPASSRLS PASSWORD '{legacy}'",
        f'GRANT CONNECT ON DATABASE "{db}" TO app_owner, app_rw, app_legacy',
        "ALTER SCHEMA public OWNER TO app_owner",
        "REVOKE CREATE ON SCHEMA public FROM PUBLIC, app_rw",
        "GRANT USAGE ON SCHEMA public TO app_rw, app_legacy",
        # The LangGraph checkpointer creates its own tables at runtime (setup()).
        "GRANT CREATE ON SCHEMA public TO app_legacy",
    ]
