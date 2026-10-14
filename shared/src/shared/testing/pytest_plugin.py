"""Pytest plugin: a disposable PostgreSQL 16 with roles and migrations applied.

Loaded for every run via `-p shared.testing.pytest_plugin` (see pyproject.toml).
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, TypeVar

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from shared.schema.migrate import ensure_roles, upgrade
from shared.schema.roles import RolePasswords

T = TypeVar("T")
TEST_PASSWORDS = RolePasswords(owner="owner-pw", rw="rw-pw", legacy="legacy-pw")
TRUNCATE = (
    "TRUNCATE users, health_logs, tasks, habits, medications, finance_transactions, "
    "finance_category_cache, integrations_credentials, oauth_state, telemetry_consent, "
    "households, household_members, household_invites, household_join_attempts RESTART IDENTITY CASCADE"
)


def run_blocking(coro: Coroutine[Any, Any, T]) -> T:
    """Run a coroutine to completion from sync code, even if an event loop is running."""
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


@dataclass(frozen=True, slots=True)
class PostgresUrls:
    admin: str
    owner: str
    rw: str
    legacy: str
    legacy_plain: str  # postgresql:// form for legacy asyncpg.connect / POSTGRES_DSN
    database: str


def _as(url: str, user: str, password: str, driver: str = "postgresql+asyncpg") -> str:
    return (
        make_url(url)
        .set(drivername=driver, username=user, password=password)
        .render_as_string(hide_password=False)
    )


async def _truncate(admin_url: str) -> None:
    engine = create_async_engine(admin_url)
    try:
        async with engine.begin() as conn:
            await conn.execute(text(TRUNCATE))
            await conn.execute(
                text("INSERT INTO telemetry_consent (user_id, bodies_ok) VALUES ('owner', true)")
            )
    finally:
        await engine.dispose()


@pytest.fixture(scope="session")
def postgres_urls() -> Iterator[PostgresUrls]:
    import docker  # type: ignore[import-untyped]

    try:
        client = docker.from_env()
        client.ping()
        client.close()
    except Exception as exc:
        pytest.fail(f"Integration tests require Docker: {exc}", pytrace=False)
    from testcontainers.community.postgres import PostgresContainer

    container = PostgresContainer("postgres:16-alpine", driver=None)
    container.start()
    try:
        raw = container.get_connection_url()
        parsed = make_url(raw)
        admin = _as(raw, parsed.username or "test", parsed.password or "test")
        database = parsed.database or "test"
        run_blocking(ensure_roles(admin, database, TEST_PASSWORDS))
        owner = _as(raw, "app_owner", TEST_PASSWORDS.owner)
        upgrade(owner)
        yield PostgresUrls(
            admin=admin,
            owner=owner,
            rw=_as(raw, "app_rw", TEST_PASSWORDS.rw),
            legacy=_as(raw, "app_legacy", TEST_PASSWORDS.legacy),
            legacy_plain=_as(raw, "app_legacy", TEST_PASSWORDS.legacy, driver="postgresql"),
            database=database,
        )
    finally:
        container.stop()


@pytest.fixture
def clean_db(postgres_urls: PostgresUrls) -> Iterator[PostgresUrls]:
    yield postgres_urls
    run_blocking(_truncate(postgres_urls.admin))


@pytest.fixture(autouse=True)
def _legacy_dsn_for_integration(request: pytest.FixtureRequest) -> Iterator[None]:
    """Legacy DB tests read POSTGRES_DSN; point it at the container (role app_legacy)."""
    if request.node.get_closest_marker("integration") is None:
        yield
        return
    urls: PostgresUrls = request.getfixturevalue("clean_db")
    patch = pytest.MonkeyPatch()
    patch.setenv("POSTGRES_DSN", urls.legacy_plain)
    try:
        yield
    finally:
        patch.undo()
