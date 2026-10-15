"""c0010: tasks, transcript and pending actions under tenant RLS; checkpoints keyed by user prefix."""

from uuid import uuid4

import pytest
from shared.testing.pytest_plugin import PostgresUrls
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.integration


async def _as(conn, user) -> None:  # type: ignore[no-untyped-def]
    await conn.execute(text("SELECT set_config('app.user_id', :u, true)"), {"u": str(user)})


@pytest.fixture
async def engines(clean_db: PostgresUrls):
    admin, rw = create_async_engine(clean_db.admin), create_async_engine(clean_db.rw)
    a, b = uuid4(), uuid4()
    async with admin.begin() as conn:
        await conn.execute(
            text("INSERT INTO users (id, name) VALUES (:a, 'a'), (:b, 'b')"), {"a": a, "b": b}
        )
    try:
        yield admin, rw, a, b
    finally:
        await admin.dispose()
        await rw.dispose()


async def test_checkpoints_are_visible_only_to_their_user(engines) -> None:
    _admin, rw, a, b = engines
    async with rw.begin() as conn:
        await _as(conn, a)
        await conn.execute(
            text(
                "INSERT INTO checkpoints (thread_id, checkpoint_id, checkpoint) VALUES (:t, 'c1', '{}')"
            ),
            {"t": f"{a}:task-1"},
        )
        with pytest.raises(DBAPIError):
            async with conn.begin_nested():
                await conn.execute(
                    text(
                        "INSERT INTO checkpoints (thread_id, checkpoint_id, checkpoint) VALUES (:t, 'c2', '{}')"
                    ),
                    {"t": f"{b}:task-1"},
                )
    async with rw.begin() as conn:
        await _as(conn, b)
        assert (await conn.execute(text("SELECT count(*) FROM checkpoints"))).scalar_one() == 0
    async with rw.begin() as conn:
        await _as(conn, a)
        assert (await conn.execute(text("SELECT count(*) FROM checkpoints"))).scalar_one() == 1


async def test_checkpoint_migrations_are_read_only_for_app_rw(engines) -> None:
    _, rw, _a, _ = engines
    async with rw.begin() as conn:
        versions = (
            await conn.execute(text("SELECT max(v) FROM checkpoint_migrations"))
        ).scalar_one()
    assert versions == 9
    async with rw.begin() as conn:
        with pytest.raises(DBAPIError, match="permission denied"):
            await conn.execute(text("INSERT INTO checkpoint_migrations VALUES (10)"))


async def test_tasks_messages_and_actions_are_tenant_scoped_and_cascade(engines) -> None:
    admin, rw, a, b = engines
    async with rw.begin() as conn:
        await _as(conn, a)
        task = (
            await conn.execute(
                text(
                    "INSERT INTO chat_tasks (user_id, lead_agent) VALUES (:u, 'sleep') RETURNING id"
                ),
                {"u": a},
            )
        ).scalar_one()
        await conn.execute(
            text(
                "INSERT INTO chat_messages (task_id, seq, user_id, role, text) VALUES (:t, 1, :u, 'user', 'hi')"
            ),
            {"t": task, "u": a},
        )
        await conn.execute(
            text(
                "INSERT INTO pending_actions (user_id, task_id, agent, kind, payload, summary, expires_at) VALUES (:u, :t, 'home', 'home.call_tool', '{}', 'Turn off?', now() + interval '5 minutes')"
            ),
            {"u": a, "t": task},
        )
        with pytest.raises(DBAPIError):
            async with conn.begin_nested():
                await conn.execute(
                    text("INSERT INTO chat_tasks (user_id, lead_agent) VALUES (:u, 'astrology')"),
                    {"u": a},
                )
    async with rw.begin() as conn:
        await _as(conn, b)
        for table in ("chat_tasks", "chat_messages", "pending_actions"):
            assert (await conn.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one() == 0, (
                table
            )
    async with rw.begin() as conn:
        await _as(conn, a)
        await conn.execute(text("DELETE FROM chat_tasks WHERE id = :t"), {"t": task})
    async with admin.begin() as conn:
        left = (
            await conn.execute(
                text(
                    "SELECT (SELECT count(*) FROM chat_messages) + (SELECT count(*) FROM pending_actions)"
                )
            )
        ).scalar_one()
    assert left == 0


async def test_one_pending_action_per_task(engines) -> None:
    _, rw, a, _ = engines
    async with rw.begin() as conn:
        await _as(conn, a)
        task = (
            await conn.execute(
                text("INSERT INTO chat_tasks (user_id) VALUES (:u) RETURNING id"), {"u": a}
            )
        ).scalar_one()
        insert = text(
            "INSERT INTO pending_actions (user_id, task_id, agent, kind, payload, summary, expires_at) VALUES (:u, :t, 'calendar', 'calendar.delete', '{}', 'x', now() + interval '5 minutes')"
        )
        await conn.execute(insert, {"u": a, "t": task})
        with pytest.raises(DBAPIError):
            async with conn.begin_nested():
                await conn.execute(insert, {"u": a, "t": task})


async def test_telemetry_consent_is_per_user(engines) -> None:
    _, rw, a, b = engines
    async with rw.begin() as conn:
        await _as(conn, a)
        await conn.execute(
            text("INSERT INTO telemetry_consent (user_id, bodies_ok) VALUES (:u, true)"), {"u": a}
        )
    async with rw.begin() as conn:
        await _as(conn, b)
        assert (
            await conn.execute(text("SELECT count(*) FROM telemetry_consent"))
        ).scalar_one() == 0


@pytest.mark.parametrize("table", ["chat_messages", "pending_actions"])
async def test_children_require_the_same_task_owner(engines, table):
    _, rw, a, b = engines
    async with rw.begin() as conn:
        await _as(conn, a)
        task = (
            await conn.execute(
                text("INSERT INTO chat_tasks (user_id) VALUES (:u) RETURNING id"), {"u": a}
            )
        ).scalar_one()
    async with rw.begin() as conn:
        await _as(conn, b)
        sql = (
            "INSERT INTO chat_messages (task_id, user_id, seq, role) VALUES (:t, :u, 1, 'user')"
            if table == "chat_messages"
            else "INSERT INTO pending_actions (task_id, user_id, agent, kind, payload, summary, expires_at) VALUES (:t, :u, 'home', 'home.call_tool', '{}', 'x', now())"
        )
        with pytest.raises(DBAPIError):
            async with conn.begin_nested():
                await conn.execute(text(sql), {"t": task, "u": b})


@pytest.mark.parametrize(
    ("table", "columns", "values"),
    [
        ("checkpoints", "checkpoint_id,checkpoint", "'c1','{}'"),
        ("checkpoint_blobs", "channel,version,type,blob", "'x','1','bytes',NULL"),
        (
            "checkpoint_writes",
            "checkpoint_id,task_id,idx,channel,blob",
            "'c1','t1',0,'x',decode('00','hex')",
        ),
    ],
)
async def test_all_checkpoint_tables_enforce_owner(engines, table, columns, values):
    _, rw, a, b = engines
    async with rw.begin() as conn:
        await _as(conn, a)
        await conn.execute(
            text(f"INSERT INTO {table} (thread_id,{columns}) VALUES (:t,{values})"),
            {"t": f"{a}:task"},
        )
    for user in (b, ""):
        async with rw.begin() as conn:
            await _as(conn, user)
            assert (await conn.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one() == 0
            with pytest.raises(DBAPIError):
                async with conn.begin_nested():
                    await conn.execute(
                        text(f"INSERT INTO {table} (thread_id,{columns}) VALUES (:t,{values})"),
                        {"t": f"{a}:other"},
                    )
    async with rw.begin() as conn:
        await _as(conn, a)
        assert (await conn.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one() == 1


@pytest.mark.parametrize("table", ["chat_messages", "pending_actions"])
async def test_children_cannot_be_moved_to_another_users_task(engines, table):
    _, rw, a, b = engines
    tasks = []
    for user in (a, b):
        async with rw.begin() as conn:
            await _as(conn, user)
            tasks.append(
                (
                    await conn.execute(
                        text("INSERT INTO chat_tasks (user_id) VALUES (:u) RETURNING id"),
                        {"u": user},
                    )
                ).scalar_one()
            )
    async with rw.begin() as conn:
        await _as(conn, a)
        sql = (
            "INSERT INTO chat_messages (task_id, user_id, seq, role) VALUES (:t, :u, 1, 'user')"
            if table == "chat_messages"
            else "INSERT INTO pending_actions (task_id, user_id, agent, kind, payload, summary, expires_at) VALUES (:t, :u, 'home', 'home.call_tool', '{}', 'x', now())"
        )
        await conn.execute(text(sql), {"t": tasks[0], "u": a})
        with pytest.raises(DBAPIError, match="row-level security"):
            async with conn.begin_nested():
                await conn.execute(text(f"UPDATE {table} SET task_id = :t"), {"t": tasks[1]})
        with pytest.raises(DBAPIError, match="row-level security"):
            async with conn.begin_nested():
                await conn.execute(text(f"UPDATE {table} SET user_id = :u"), {"u": b})


async def test_role_bootstrap_keeps_checkpoint_versions_read_only(clean_db):
    from shared.schema.migrate import ensure_roles
    from shared.testing.pytest_plugin import TEST_PASSWORDS

    for _ in range(2):
        await ensure_roles(clean_db.admin, clean_db.database, TEST_PASSWORDS)
    rw = create_async_engine(clean_db.rw)
    try:
        async with rw.begin() as conn:
            assert (
                await conn.execute(text("SELECT max(v) FROM checkpoint_migrations"))
            ).scalar_one() == 9
            for statement in (
                "INSERT INTO checkpoint_migrations VALUES (10)",
                "UPDATE checkpoint_migrations SET v = 10",
                "DELETE FROM checkpoint_migrations",
            ):
                with pytest.raises(DBAPIError, match="permission denied"):
                    async with conn.begin_nested():
                        await conn.execute(text(statement))
    finally:
        await rw.dispose()
