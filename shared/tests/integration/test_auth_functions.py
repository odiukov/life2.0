"""app_rw reaches auth_* only through the functions; the functions keep the flow's guarantees."""

import hashlib
from uuid import uuid4

import pytest
from shared.schema import metadata
from shared.testing.pytest_plugin import PostgresUrls
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.integration


def h(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


@pytest.fixture
async def rw(clean_db: PostgresUrls):
    engine = create_async_engine(clean_db.rw)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.mark.parametrize(
    "table", ["auth_flows", "auth_tickets", "auth_identities", "auth_sessions"]
)
@pytest.mark.parametrize(
    "statement",
    [
        "SELECT 1 FROM {table}",
        "INSERT INTO {table} DEFAULT VALUES",
        "UPDATE {table} SET expires_at = expires_at WHERE false",
        "DELETE FROM {table} WHERE false",
    ],
)
async def test_tables_are_closed_to_app_rw(rw, table: str, statement: str) -> None:
    if table == "auth_identities" and statement.startswith("UPDATE"):
        statement = "UPDATE {table} SET email = email WHERE false"
    async with rw.connect() as conn:
        with pytest.raises(DBAPIError, match="permission denied"):
            await conn.execute(text(statement.format(table=table)))


async def test_full_flow(rw) -> None:
    async with rw.begin() as conn:
        await conn.execute(
            text("SELECT auth_begin_flow(:s, 'google', 'verifier', 'nonce', :c, 600)"),
            {"s": h("state"), "c": h("app")},
        )
        flow = (
            await conn.execute(
                text("SELECT * FROM auth_take_flow(:s, 'google')"), {"s": h("state")}
            )
        ).one()
        again = (
            await conn.execute(
                text("SELECT * FROM auth_take_flow(:s, 'google')"), {"s": h("state")}
            )
        ).all()
        user = (
            await conn.execute(
                text("SELECT auth_link_identity('google', 'sub-1', 'a@example.test', 'Ana')")
            )
        ).scalar_one()
        same = (
            await conn.execute(
                text("SELECT auth_link_identity('google', 'sub-1', 'a@example.test', 'Ana')")
            )
        ).scalar_one()
        apple = (
            await conn.execute(
                text("SELECT auth_link_identity('apple', 'sub-1', 'a@example.test', NULL)")
            )
        ).scalar_one()
        await conn.execute(
            text("SELECT auth_issue_ticket(:t, :u, :c, 120)"),
            {"t": h("ticket"), "u": user, "c": h("app")},
        )
        wrong = (
            await conn.execute(
                text("SELECT * FROM auth_exchange_ticket(:t, :c, :sid, :r, 3600)"),
                {"t": h("ticket"), "c": h("other"), "sid": uuid4(), "r": h("r0")},
            )
        ).all()
        sid = uuid4()
        profile = (
            await conn.execute(
                text("SELECT * FROM auth_exchange_ticket(:t, :c, :sid, :r, 3600)"),
                {"t": h("ticket"), "c": h("app"), "sid": sid, "r": h("r0")},
            )
        ).one()
        replay = (
            await conn.execute(
                text("SELECT * FROM auth_exchange_ticket(:t, :c, :sid, :r, 3600)"),
                {"t": h("ticket"), "c": h("app"), "sid": uuid4(), "r": h("r0")},
            )
        ).all()
        active = (
            await conn.execute(
                text("SELECT auth_session_active(:sid, :u)"), {"sid": sid, "u": user}
            )
        ).scalar_one()
        ok = (
            await conn.execute(
                text("SELECT * FROM auth_rotate_session(:sid, :old, :new, 3600)"),
                {"sid": sid, "old": h("r0"), "new": h("r1")},
            )
        ).one()
        reused = (
            await conn.execute(
                text("SELECT * FROM auth_rotate_session(:sid, :old, :new, 3600)"),
                {"sid": sid, "old": h("r0"), "new": h("r2")},
            )
        ).one()
        after_reuse = (
            await conn.execute(
                text("SELECT auth_session_active(:sid, :u)"), {"sid": sid, "u": user}
            )
        ).scalar_one()
    assert (flow.out_verifier, flow.out_nonce, flow.out_challenge) == (
        "verifier",
        "nonce",
        h("app"),
    )
    assert again == []
    assert user == same
    assert apple != user
    assert wrong == []
    assert replay == []
    assert (profile.out_user, profile.out_name, profile.out_email) == (
        user,
        "Ana",
        "a@example.test",
    )
    assert active is True
    assert (ok.out_status, ok.out_user) == ("ok", user)
    assert reused.out_status == "reused"
    assert after_reuse is False


async def test_expired_flows_and_tickets_are_refused(rw) -> None:
    async with rw.begin() as conn:
        await conn.execute(
            text("SELECT auth_begin_flow(:s, 'apple', 'v', 'n', :c, -1)"),
            {"s": h("old"), "c": h("app")},
        )
        assert (
            await conn.execute(text("SELECT * FROM auth_take_flow(:s, 'apple')"), {"s": h("old")})
        ).all() == []
        user = (
            await conn.execute(text("SELECT auth_link_identity('apple', 'sub-9', NULL, NULL)"))
        ).scalar_one()
        await conn.execute(
            text("SELECT auth_issue_ticket(:t, :u, :c, -1)"),
            {"t": h("late"), "u": user, "c": h("app")},
        )
        assert (
            await conn.execute(
                text("SELECT * FROM auth_exchange_ticket(:t, :c, :sid, 'r', 3600)"),
                {"t": h("late"), "c": h("app"), "sid": uuid4()},
            )
        ).all() == []


async def test_new_users_get_a_name_and_utc(rw, clean_db: PostgresUrls) -> None:
    async with rw.begin() as conn:
        user = (
            await conn.execute(text("SELECT auth_link_identity('apple', 'sub-2', NULL, NULL)"))
        ).scalar_one()
    admin = create_async_engine(clean_db.admin)
    async with admin.begin() as conn:
        row = (
            await conn.execute(text("SELECT name, timezone FROM users WHERE id = :u"), {"u": user})
        ).one()
    await admin.dispose()
    assert (row.name, row.timezone) == ("Apple", "UTC")


def test_auth_tables_have_identity_and_rotating_session_keys():
    assert {"auth_identities", "auth_flows", "auth_tickets", "auth_sessions"} <= set(
        metadata.tables
    )
    identities = metadata.tables["auth_identities"]
    assert {"provider", "subject", "user_id"} <= set(identities.c.keys())
    sessions = metadata.tables["auth_sessions"]
    assert {"user_id", "refresh_hash", "expires_at", "revoked_at"} <= set(sessions.c.keys())
    assert "app_challenge" in metadata.tables["auth_flows"].c
    assert "app_challenge" in metadata.tables["auth_tickets"].c


async def test_internal_auth_profile_is_not_executable_by_app_rw(rw):
    async with rw.connect() as conn:
        with pytest.raises(DBAPIError, match="permission denied for function auth_profile"):
            await conn.execute(text("SELECT * FROM auth_profile(:user)"), {"user": uuid4()})
