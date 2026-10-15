"""Pytest plugin: a disposable PostgreSQL 16 with roles and migrations applied.

Loaded for every run via `-p shared.testing.pytest_plugin` (see pyproject.toml).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Coroutine, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from shared.schema.migrate import ensure_roles, upgrade
from shared.schema.roles import RolePasswords

T = TypeVar("T")
TEST_PASSWORDS = RolePasswords(owner="owner-pw", rw="rw-pw")
TRUNCATE = (
    "TRUNCATE users, health_logs, tasks, habits, medications, finance_transactions, "
    "finance_category_cache, integration_sync_state, integrations_credentials, oauth_state, telemetry_consent, "
    "households, household_credentials, household_members, household_invites, household_join_attempts, "
    "kitchen_batches, kitchen_operation_groups, kitchen_clarifications, kitchen_digest_runs, "
    "notifications, push_tokens, auth_flows, auth_tickets, auth_identities, auth_sessions, "
    "chat_tasks, chat_messages, pending_actions, checkpoints, checkpoint_blobs, checkpoint_writes "
    "RESTART IDENTITY CASCADE"
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
            database=database,
        )
    finally:
        container.stop()


@pytest.fixture
def clean_db(postgres_urls: PostgresUrls) -> Iterator[PostgresUrls]:
    yield postgres_urls
    run_blocking(_truncate(postgres_urls.admin))


@pytest.fixture(autouse=True)
def _clean_integration_database(request: pytest.FixtureRequest) -> None:
    """Keep each integration test isolated, including tests using postgres_urls directly."""
    if request.node.get_closest_marker("integration") is not None:
        request.getfixturevalue("clean_db")


async def _fresh_database(
    urls: PostgresUrls, *, with_old_role: bool
) -> AsyncIterator[AsyncConnection]:
    database = "migration_probe_" + uuid4().hex
    admin_url = make_url(urls.admin).set(database=database).render_as_string(hide_password=False)
    owner_url = make_url(urls.owner).set(database=database).render_as_string(hide_password=False)
    cluster = create_async_engine(urls.admin, isolation_level="AUTOCOMMIT")
    engine = create_async_engine(admin_url)
    try:
        async with cluster.connect() as conn:
            await conn.execute(text(f'CREATE DATABASE "{database}" TEMPLATE template0'))
        if with_old_role:
            async with engine.begin() as conn:
                await conn.execute(text("CREATE ROLE app_legacy LOGIN BYPASSRLS"))
                await conn.execute(text("CREATE TABLE legacy_scratch (id integer)"))
                await conn.execute(text("ALTER TABLE legacy_scratch OWNER TO app_legacy"))
                await conn.execute(text("CREATE TABLE grant_probe (id integer)"))
                await conn.execute(text("ALTER TABLE grant_probe OWNER TO app_owner"))
                await conn.execute(
                    text("GRANT SELECT, INSERT, UPDATE, DELETE ON grant_probe TO app_legacy")
                )
        await ensure_roles(admin_url, database, TEST_PASSWORDS)
        await asyncio.to_thread(upgrade, owner_url)
        async with engine.connect() as conn:
            yield conn
    finally:
        await engine.dispose()
        async with cluster.connect() as conn:
            await conn.execute(text(f'DROP DATABASE IF EXISTS "{database}" WITH (FORCE)'))
            if with_old_role:
                await conn.execute(text("DROP ROLE IF EXISTS app_legacy"))
        await cluster.dispose()


@pytest.fixture
async def fresh_database(postgres_urls: PostgresUrls) -> AsyncIterator[AsyncConnection]:
    async for conn in _fresh_database(postgres_urls, with_old_role=False):
        yield conn


@pytest.fixture
async def fresh_database_with_legacy_role(
    postgres_urls: PostgresUrls,
) -> AsyncIterator[AsyncConnection]:
    async for conn in _fresh_database(postgres_urls, with_old_role=True):
        yield conn


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--update-snapshots",
        action="store_true",
        default=False,
        help="Write prompt snapshot files instead of comparing against them.",
    )


@pytest.fixture
def snapshot(request: pytest.FixtureRequest) -> Callable[[str, str], None]:
    """Compare text with <test dir>/snapshots/<name>.txt (use --update-snapshots to write)."""
    folder = Path(str(request.node.path)).parent / "snapshots"
    update = bool(request.config.getoption("--update-snapshots"))

    def check(name: str, text: str) -> None:
        path = folder / f"{name}.txt"
        if update:
            folder.mkdir(exist_ok=True)
            path.write_text(text, "utf-8")
            return
        assert path.exists(), (
            f"missing snapshot {path}; run pytest --update-snapshots and review the diff"
        )
        assert path.read_text("utf-8") == text, (
            f"snapshot {path} differs; review, then --update-snapshots"
        )

    return check
