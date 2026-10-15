"""Database roles. `app_owner` migrates, `app_rw` is tenant-scoped."""

from __future__ import annotations

import re
from dataclasses import dataclass

_SAFE = re.compile(r"^[A-Za-z0-9_-]+$")
ROLES = ("app_owner", "app_rw")


@dataclass(frozen=True, slots=True)
class RolePasswords:
    owner: str
    rw: str


def _safe(value: str, what: str) -> str:
    if not _SAFE.fullmatch(value):
        raise ValueError(f"{what} may contain only letters, digits, '_' and '-'")
    return value


def role_statements(database: str, passwords: RolePasswords) -> list[str]:
    """Idempotent SQL, run as a superuser, that creates/updates the two roles."""
    db = _safe(database, "database name")
    owner = _safe(passwords.owner, "APP_OWNER_PASSWORD")
    rw = _safe(passwords.rw, "APP_RW_PASSWORD")
    create = [
        f"DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{role}') "
        f"THEN CREATE ROLE {role} LOGIN; END IF; END $$"
        for role in ROLES
    ]
    return [
        *create,
        f"ALTER ROLE app_owner LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD '{owner}'",
        f"ALTER ROLE app_rw LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD '{rw}'",
        f'GRANT CONNECT ON DATABASE "{db}" TO app_owner, app_rw',
        "ALTER SCHEMA public OWNER TO app_owner",
        "REVOKE CREATE ON SCHEMA public FROM PUBLIC, app_rw",
        "GRANT USAGE ON SCHEMA public TO app_rw",
        *RETIRE_LEGACY,
    ]


# Preserve old runtime-owned objects before revoking grants and retiring the role.
RETIRE_LEGACY = [
    "DO $$ BEGIN "
    "IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_legacy') THEN "
    "REASSIGN OWNED BY app_legacy TO app_owner; "
    "DROP OWNED BY app_legacy; "
    "DROP ROLE app_legacy; "
    "END IF; END $$",
]
