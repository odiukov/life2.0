import hashlib
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from shared.schema import metadata
from shared.schema.tables import HOUSEHOLD_TABLES
from shared.testing.pytest_plugin import PostgresUrls
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

pytestmark = pytest.mark.integration

MEMBERSHIP_TABLES = {
    "households",
    "household_members",
    "household_join_attempts",
    "household_tables",
}


def code_hash(code: str) -> bytes:
    return hashlib.sha256(code.encode()).digest()


@pytest.fixture
async def engines(clean_db: PostgresUrls) -> AsyncIterator[tuple[AsyncEngine, AsyncEngine]]:
    admin = create_async_engine(clean_db.admin)
    rw = create_async_engine(clean_db.rw)
    yield admin, rw
    await admin.dispose()
    await rw.dispose()


async def as_user(conn: AsyncConnection, user: UUID) -> None:
    await conn.execute(text("SELECT set_config('app.user_id', :u, true)"), {"u": str(user)})


async def ensure(rw: AsyncEngine, user: UUID, name: str = "A", tz: str = "Europe/Lisbon") -> UUID:
    async with rw.begin() as conn:
        await as_user(conn, user)
        return (
            await conn.execute(text("SELECT household_ensure(:n, :tz)"), {"n": name, "tz": tz})
        ).scalar_one()


async def invite(
    rw: AsyncEngine, user: UUID, code: str, *, expires_in: timedelta = timedelta(hours=48)
) -> None:
    async with rw.begin() as conn:
        await as_user(conn, user)
        await conn.execute(
            text(
                "INSERT INTO household_invites (code_hash, created_by, expires_at) "
                "VALUES (:h, :u, :e)"
            ),
            {"h": code_hash(code), "u": user, "e": datetime.now(UTC) + expires_in},
        )


async def join(rw: AsyncEngine, user: UUID, code: str) -> tuple[str, UUID | None]:
    async with rw.begin() as conn:
        await as_user(conn, user)
        row = (
            await conn.execute(text("SELECT * FROM household_join(:h)"), {"h": code_hash(code)})
        ).one()
        return row.status, row.household_id


async def test_ensure_creates_user_household_and_owner_once(engines) -> None:
    _, rw = engines
    user = uuid4()
    first = await ensure(rw, user, "Олег")
    assert await ensure(rw, user, "ignored") == first
    async with rw.begin() as conn:
        await as_user(conn, user)
        row = (
            await conn.execute(
                text(
                    "SELECT h.name, h.timezone, h.digest_time::text AS t, m.role, m.display_name "
                    "FROM households h JOIN household_members m ON m.household_id = h.id"
                )
            )
        ).one()
        assert (row.name, row.timezone, row._mapping["t"], row.role, row.display_name) == (
            "Олег",
            "Europe/Lisbon",
            "18:00:00",
            "owner",
            "Олег",
        )
        assert (await conn.execute(text("SELECT current_household_id()"))).scalar_one() == first


async def test_ensure_keeps_an_existing_users_row(engines) -> None:
    admin, rw = engines
    user = uuid4()
    async with admin.begin() as conn:
        await conn.execute(
            text("INSERT INTO users (id, name, timezone) VALUES (:u, 'provider:1234', 'UTC')"),
            {"u": user},
        )
    await ensure(rw, user, "fallback", "Europe/Lisbon")
    async with rw.begin() as conn:
        await as_user(conn, user)
        row = (await conn.execute(text("SELECT name, timezone FROM households"))).one()
    assert (row.name, row.timezone) == ("provider:1234", "UTC")


async def test_app_rw_cannot_write_membership_directly(engines) -> None:
    _, rw = engines
    user = uuid4()
    household = await ensure(rw, user)
    for statement in (
        "INSERT INTO household_members (household_id, user_id, role, display_name) VALUES (:h, gen_random_uuid(), 'member', 'x')",
        "UPDATE household_members SET role = 'owner'",
        "UPDATE households SET name = 'x'",
        "DELETE FROM households",
    ):
        async with rw.connect() as conn:
            await conn.begin()
            await as_user(conn, user)
            with pytest.raises(DBAPIError, match="permission denied"):
                await conn.execute(text(statement), {"h": household})
            await conn.rollback()


async def test_members_see_only_their_household(engines) -> None:
    _, rw = engines
    a, b = uuid4(), uuid4()
    await ensure(rw, a, "A")
    await ensure(rw, b, "B")
    async with rw.begin() as conn:
        await as_user(conn, a)
        assert (await conn.execute(text("SELECT name FROM households"))).scalars().all() == ["A"]
        assert (
            await conn.execute(text("SELECT count(*) FROM household_members"))
        ).scalar_one() == 1
    async with rw.begin() as conn:  # no tenant: nothing
        assert (await conn.execute(text("SELECT count(*) FROM households"))).scalar_one() == 0


async def test_preview_and_join_by_sole_member_moves_and_deletes_old_household(engines) -> None:
    _, rw = engines
    owner, joiner = uuid4(), uuid4()
    target = await ensure(rw, owner, "Дыковы")
    old = await ensure(rw, joiner, "Аня")
    await invite(rw, owner, "CODE1")
    async with rw.begin() as conn:
        await as_user(conn, joiner)
        preview = (
            await conn.execute(
                text("SELECT * FROM household_invite_preview(:h)"), {"h": code_hash("CODE1")}
            )
        ).one()
    assert (
        preview.status,
        preview.household_name,
        preview.member_count,
        preview.items_to_move,
    ) == ("ok", "Дыковы", 1, 0)
    assert await join(rw, joiner, "CODE1") == ("ok", target)
    async with rw.begin() as conn:
        await as_user(conn, joiner)
        members = (
            await conn.execute(
                text("SELECT display_name, role FROM household_members ORDER BY joined_at")
            )
        ).all()
        assert [tuple(m) for m in members] == [("Дыковы", "owner"), ("Аня", "member")]
        assert (await conn.execute(text("SELECT current_household_id()"))).scalar_one() == target
        assert old not in (await conn.execute(text("SELECT id FROM households"))).scalars().all()


async def test_invite_is_single_use_expires_and_cannot_target_own_household(engines) -> None:
    _, rw = engines
    owner, x, y = uuid4(), uuid4(), uuid4()
    await ensure(rw, owner)
    await ensure(rw, x)
    await ensure(rw, y)
    await invite(rw, owner, "ONCE")
    await invite(rw, owner, "OLD", expires_in=timedelta(seconds=-1))
    assert (await join(rw, owner, "ONCE"))[0] == "own"
    assert (await join(rw, x, "ONCE"))[0] == "ok"
    assert (await join(rw, y, "ONCE"))[0] == "invalid"
    assert (await join(rw, y, "OLD"))[0] == "invalid"
    assert (await join(rw, y, "NOPE"))[0] == "invalid"


async def test_five_failures_in_an_hour_rate_limit_the_actor(engines) -> None:
    _, rw = engines
    owner, attacker = uuid4(), uuid4()
    await ensure(rw, owner)
    await ensure(rw, attacker)
    await invite(rw, owner, "REAL")
    for attempt in range(5):
        assert (await join(rw, attacker, f"WRONG{attempt}"))[0] == "invalid"
    assert (await join(rw, attacker, "REAL"))[0] == "rate_limited"


async def test_non_sole_member_leaves_items_behind_and_owner_role_moves(engines) -> None:
    _, rw = engines
    a, b, c = uuid4(), uuid4(), uuid4()
    first = await ensure(rw, a, "A")
    await ensure(rw, b, "B")
    await ensure(rw, c, "C")
    await invite(rw, a, "AB")
    assert (await join(rw, b, "AB"))[0] == "ok"
    # c owns a different household and invites a: a was the owner of `first` with b inside.
    await invite(rw, c, "CA")
    assert (await join(rw, a, "CA"))[0] == "ok"
    async with rw.begin() as conn:
        await as_user(conn, b)
        assert (await conn.execute(text("SELECT current_household_id()"))).scalar_one() == first
        assert (
            await conn.execute(text("SELECT role FROM household_members"))
        ).scalar_one() == "owner"


async def test_leave_creates_a_fresh_household_and_sole_member_cannot_leave(engines) -> None:
    _, rw = engines
    a, b = uuid4(), uuid4()
    shared_home = await ensure(rw, a, "A")
    await ensure(rw, b, "B")
    async with rw.begin() as conn:
        await as_user(conn, a)
        assert (
            await conn.execute(text("SELECT status FROM household_leave()"))
        ).scalar_one() == "sole_member"
    await invite(rw, a, "AB")
    await join(rw, b, "AB")
    async with rw.begin() as conn:
        await as_user(conn, b)
        row = (await conn.execute(text("SELECT * FROM household_leave()"))).one()
        assert row.status == "ok"
        assert row.household_id != shared_home
        assert (
            await conn.execute(text("SELECT role FROM household_members"))
        ).scalar_one() == "owner"


async def test_remove_member_rules(engines) -> None:
    _, rw = engines
    a, b = uuid4(), uuid4()
    await ensure(rw, a, "A")
    await ensure(rw, b, "B")
    await invite(rw, a, "AB")
    await join(rw, b, "AB")
    async with rw.begin() as conn:
        await as_user(conn, b)
        assert (
            await conn.execute(text("SELECT household_remove_member(:u)"), {"u": a})
        ).scalar_one() == "not_owner"
    async with rw.begin() as conn:
        await as_user(conn, a)
        assert (
            await conn.execute(text("SELECT household_remove_member(:u)"), {"u": a})
        ).scalar_one() == "self"
        assert (
            await conn.execute(text("SELECT household_remove_member(:u)"), {"u": uuid4()})
        ).scalar_one() == "not_member"
        assert (
            await conn.execute(text("SELECT household_remove_member(:u)"), {"u": b})
        ).scalar_one() == "ok"
        assert (
            await conn.execute(text("SELECT count(*) FROM household_members"))
        ).scalar_one() == 1
    async with rw.begin() as conn:
        await as_user(conn, b)
        assert (
            await conn.execute(text("SELECT role FROM household_members"))
        ).scalar_one() == "owner"


async def test_update_requires_owner(engines) -> None:
    _, rw = engines
    a, b = uuid4(), uuid4()
    await ensure(rw, a, "A")
    await ensure(rw, b, "B")
    await invite(rw, a, "AB")
    await join(rw, b, "AB")
    async with rw.begin() as conn:
        await as_user(conn, b)
        status = (await conn.execute(text("SELECT household_update('X', NULL, NULL)"))).scalar_one()
        assert status == "not_owner"
    async with rw.begin() as conn:
        await as_user(conn, a)
        assert (
            await conn.execute(text("SELECT household_update('Дом', NULL, '19:30')"))
        ).scalar_one() == "ok"
        row = (
            await conn.execute(
                text("SELECT name, timezone, digest_time::text AS t FROM households")
            )
        ).one()
        assert (row.name, row.timezone, row._mapping["t"]) == ("Дом", "Europe/Lisbon", "19:30:00")


async def test_functions_require_a_tenant(engines) -> None:
    _, rw = engines
    async with rw.connect() as conn:
        await conn.begin()
        with pytest.raises(DBAPIError, match="no_tenant"):
            await conn.execute(text("SELECT household_ensure('x', 'UTC')"))
        await conn.rollback()


async def test_registry_matches_household_tables_and_every_household_column(engines) -> None:
    admin, _ = engines
    async with admin.connect() as conn:
        rows = (
            await conn.execute(text("SELECT table_name, move_on_join FROM household_tables"))
        ).all()
    assert {r.table_name: r.move_on_join for r in rows} == HOUSEHOLD_TABLES
    # These user-owned records retain household context; joining must not transfer them.
    user_scoped_context = {"chat_tasks", "pending_actions"}
    scoped = {
        name
        for name, table in metadata.tables.items()
        if "household_id" in table.c and name not in MEMBERSHIP_TABLES | user_scoped_context
    }
    assert scoped == set(HOUSEHOLD_TABLES)


async def test_every_household_table_has_rls_and_a_policy(engines) -> None:
    admin, _ = engines
    async with admin.connect() as conn:
        for table in [*HOUSEHOLD_TABLES, "households", "household_members"]:
            enabled = (
                await conn.execute(
                    text("SELECT relrowsecurity FROM pg_class WHERE relname = :t"), {"t": table}
                )
            ).scalar_one()
            policies = (
                await conn.execute(
                    text("SELECT count(*) FROM pg_policies WHERE tablename = :t"), {"t": table}
                )
            ).scalar_one()
            assert enabled, table
            assert policies >= 1, table


async def test_legacy_role_has_no_access_to_household_tables(clean_db: PostgresUrls) -> None:
    legacy = create_async_engine(clean_db.legacy)
    try:
        async with legacy.connect() as conn:
            with pytest.raises(DBAPIError, match="permission denied"):
                await conn.execute(text("SELECT count(*) FROM household_members"))
    finally:
        await legacy.dispose()


async def test_concurrent_redemption_has_one_winner(engines) -> None:
    import asyncio

    _, rw = engines
    owner, a, b = uuid4(), uuid4(), uuid4()
    home = await ensure(rw, owner)
    for user in (a, b):
        await ensure(rw, user)
    await invite(rw, owner, "RACE")
    results = await asyncio.wait_for(asyncio.gather(join(rw, a, "RACE"), join(rw, b, "RACE")), 10)
    assert sorted(status for status, _ in results) == ["invalid", "ok"]
    assert next(hid for status, hid in results if status == "ok") == home


async def test_concurrent_failures_serialize_rate_limit_and_cleanup(engines) -> None:
    import asyncio

    admin, rw = engines
    actor = uuid4()
    await ensure(rw, actor)
    async with admin.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO household_join_attempts (user_id, succeeded, attempted_at) "
                "VALUES (:u, false, now() - interval '25 hours')"
            ),
            {"u": actor},
        )
    results = await asyncio.wait_for(
        asyncio.gather(*(join(rw, actor, f"BAD{i}") for i in range(12))), 10
    )
    assert sorted(status for status, _ in results) == ["invalid"] * 5 + ["rate_limited"] * 7
    async with admin.connect() as conn:
        assert (
            await conn.execute(
                text("SELECT count(*) FROM household_join_attempts WHERE user_id = :u"),
                {"u": actor},
            )
        ).scalar_one() == 5


async def test_concurrent_leaves_keep_one_owner_and_membership_per_user(engines) -> None:
    import asyncio

    admin, rw = engines
    a, b, c = uuid4(), uuid4(), uuid4()
    home = await ensure(rw, a)
    for user, code in ((b, "B"), (c, "C")):
        await ensure(rw, user)
        await invite(rw, a, code)
        await join(rw, user, code)

    async def leave(user: UUID) -> str:
        async with rw.begin() as conn:
            await as_user(conn, user)
            return (await conn.execute(text("SELECT status FROM household_leave()"))).scalar_one()

    assert await asyncio.wait_for(asyncio.gather(leave(a), leave(b)), 10) == ["ok", "ok"]
    async with admin.connect() as conn:
        assert (
            await conn.execute(
                text("SELECT user_id, role FROM household_members WHERE household_id = :h"),
                {"h": home},
            )
        ).all() == [(c, "owner")]
        assert (
            await conn.execute(text("SELECT count(*) FROM household_members"))
        ).scalar_one() == 3


async def test_opposite_household_moves_do_not_deadlock(engines) -> None:
    import asyncio

    admin, rw = engines
    a, b, c, d = uuid4(), uuid4(), uuid4(), uuid4()
    first, second = await ensure(rw, a), await ensure(rw, c)
    for user, owner, code in ((b, a, "AB"), (d, c, "CD")):
        await ensure(rw, user)
        await invite(rw, owner, code)
        await join(rw, user, code)
    await invite(rw, a, "TO_A")
    await invite(rw, c, "TO_C")
    assert await asyncio.wait_for(asyncio.gather(join(rw, a, "TO_C"), join(rw, c, "TO_A")), 10) == [
        ("ok", second),
        ("ok", first),
    ]
    async with admin.connect() as conn:
        assert (
            await conn.execute(text("SELECT count(*) FROM household_members WHERE role = 'owner'"))
        ).scalar_one() == 2


async def test_membership_move_waits_for_shared_household_lock(engines) -> None:
    import asyncio

    _, rw = engines
    a, b = uuid4(), uuid4()
    await ensure(rw, a)
    old = await ensure(rw, b)
    await invite(rw, a, "MOVE")
    async with rw.connect() as conn:
        await conn.begin()
        await as_user(conn, b)
        await conn.execute(text("SELECT household_lock(:h)"), {"h": old})
        started = asyncio.Event()

        async def move() -> tuple[str, UUID | None]:
            started.set()
            return await join(rw, b, "MOVE")

        task = asyncio.create_task(move())
        try:
            await started.wait()
            await asyncio.sleep(0.1)
            assert not task.done()
        finally:
            await conn.rollback()
        assert (await asyncio.wait_for(task, 10))[0] == "ok"


async def test_security_definer_grants_search_path_and_enable_only_rls(engines) -> None:
    admin, _ = engines
    async with admin.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT p.proname, p.prosecdef, p.proconfig, r.rolname, "
                    "has_function_privilege('app_legacy', p.oid, 'EXECUTE') AS legacy, "
                    "has_function_privilege('app_rw', p.oid, 'EXECUTE') AS rw "
                    "FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
                    "JOIN pg_roles r ON r.oid = p.proowner "
                    "WHERE n.nspname = 'public' AND (p.proname LIKE 'household_%' OR p.proname = 'current_household_id')"
                )
            )
        ).all()
        public = {
            "current_household_id",
            "household_ensure",
            "household_update",
            "household_invite_preview",
            "household_join",
            "household_leave",
            "household_remove_member",
            "household_lock_key",
            "household_lock",
        }
        assert rows
        for row in rows:
            assert row.prosecdef
            assert row.rolname == "app_owner"
            assert row.proconfig == ["search_path=public, pg_temp"]
            assert not row.legacy
            assert row.rw == (row.proname in public)
        assert (
            await conn.execute(
                text(
                    "SELECT bool_and(relrowsecurity AND NOT relforcerowsecurity) FROM pg_class "
                    "WHERE relname IN ('households','household_members','household_invites','household_join_attempts')"
                )
            )
        ).scalar_one()


async def test_join_purges_old_attempts_for_inactive_actors(engines) -> None:
    admin, rw = engines
    inactive, actor = uuid4(), uuid4()
    await ensure(rw, inactive)
    await ensure(rw, actor)
    async with admin.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO household_join_attempts (user_id, succeeded, attempted_at) "
                "VALUES (:u, false, now() - interval '25 hours')"
            ),
            {"u": inactive},
        )
    assert (await join(rw, actor, "BAD"))[0] == "invalid"
    async with admin.connect() as conn:
        assert (
            await conn.execute(
                text("SELECT count(*) FROM household_join_attempts WHERE user_id = :u"),
                {"u": inactive},
            )
        ).scalar_one() == 0


async def test_concurrent_sole_member_moves_use_registry_and_delete_old_homes(engines) -> None:
    import asyncio

    admin, rw = engines
    owner, a, b = uuid4(), uuid4(), uuid4()
    target = await ensure(rw, owner)
    old_a, old_b = await ensure(rw, a), await ensure(rw, b)
    async with admin.begin() as conn:
        await conn.execute(
            text(
                "CREATE TABLE household_move_probe (household_id uuid NOT NULL "
                "REFERENCES households(id) ON DELETE CASCADE, payload text NOT NULL)"
            )
        )
        await conn.execute(text("ALTER TABLE household_move_probe OWNER TO app_owner"))
        await conn.execute(
            text("INSERT INTO household_tables VALUES ('household_move_probe', true, 'true')")
        )
        await conn.execute(
            text("INSERT INTO household_move_probe VALUES (:a, 'a'), (:b, 'b')"),
            {"a": old_a, "b": old_b},
        )
    try:
        await invite(rw, owner, "JOIN_A")
        await invite(rw, owner, "JOIN_B")
        async with rw.begin() as conn:
            await as_user(conn, a)
            assert (
                await conn.execute(
                    text("SELECT items_to_move FROM household_invite_preview(:h)"),
                    {"h": code_hash("JOIN_A")},
                )
            ).scalar_one() == 1
        assert await asyncio.wait_for(
            asyncio.gather(join(rw, a, "JOIN_A"), join(rw, b, "JOIN_B")), 10
        ) == [("ok", target), ("ok", target)]
        async with admin.connect() as conn:
            assert (
                await conn.execute(
                    text("SELECT household_id, payload FROM household_move_probe ORDER BY payload")
                )
            ).all() == [(target, "a"), (target, "b")]
            assert (await conn.execute(text("SELECT id FROM households"))).scalars().all() == [
                target
            ]
            assert (
                await conn.execute(
                    text("SELECT count(*) FROM household_members WHERE household_id = :h"),
                    {"h": target},
                )
            ).scalar_one() == 3
    finally:
        async with admin.begin() as conn:
            await conn.execute(
                text("DELETE FROM household_tables WHERE table_name = 'household_move_probe'")
            )
            await conn.execute(text("DROP TABLE household_move_probe"))


@pytest.mark.parametrize("attack", ["actor_null", "unnest", "preview_format", "move_format"])
async def test_legacy_overloads_cannot_execute_with_household_definer_privileges(
    engines, clean_db: PostgresUrls, attack: str
) -> None:
    admin, rw = engines
    owner, joiner = uuid4(), uuid4()
    home = await ensure(rw, owner, "protected-owner")
    await ensure(rw, joiner, "protected-joiner")
    await invite(rw, owner, "SAFE")
    payload = "UPDATE public.households SET name = 'compromised by ' || current_user;"
    attacks = {
        "actor_null": (
            "household_lock_actors(uuid, text)",
            "CREATE FUNCTION public.household_lock_actors(uuid, text) RETURNS void "
            f"LANGUAGE plpgsql AS $$ BEGIN {payload} END $$",
        ),
        "unnest": (
            "unnest(uuid[])",
            "CREATE FUNCTION public.unnest(uuid[]) RETURNS SETOF uuid "
            f"LANGUAGE plpgsql AS $$ BEGIN {payload} "
            "RETURN QUERY SELECT pg_catalog.unnest($1); END $$",
        ),
        "preview_format": (
            "format(text, text, text)",
            "CREATE FUNCTION public.format(text, text, text) RETURNS text "
            f"LANGUAGE plpgsql AS $$ BEGIN {payload} "
            "RETURN pg_catalog.format($1, $2, $3); END $$",
        ),
        "move_format": (
            "format(text, text)",
            "CREATE FUNCTION public.format(text, text) RETURNS text "
            f"LANGUAGE plpgsql AS $$ BEGIN {payload} "
            "RETURN pg_catalog.format($1, $2); END $$",
        ),
    }
    signature, ddl = attacks[attack]
    legacy = create_async_engine(clean_db.legacy)
    # New backends resolve definer expressions after the malicious overload exists.
    await rw.dispose()
    try:
        async with legacy.begin() as conn:
            await conn.execute(text(ddl))
        async with admin.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE household_tables SET move_on_join = true, item_filter = 'true' "
                    "WHERE table_name = 'household_invites'"
                )
            )
        assert await ensure(rw, owner, "ignored") == home
        async with rw.begin() as conn:
            await as_user(conn, joiner)
            assert (
                await conn.execute(
                    text("SELECT status FROM household_invite_preview(:h)"),
                    {"h": code_hash("SAFE")},
                )
            ).scalar_one() == "ok"
        assert await join(rw, joiner, "SAFE") == ("ok", home)
        async with admin.connect() as conn:
            assert (
                await conn.execute(text("SELECT name FROM households WHERE id = :h"), {"h": home})
            ).scalar_one() == "protected-owner"
    finally:
        async with legacy.begin() as conn:
            await conn.execute(text(f"DROP FUNCTION IF EXISTS public.{signature}"))
        async with admin.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE household_tables SET move_on_join = false, item_filter = NULL "
                    "WHERE table_name = 'household_invites'"
                )
            )
        await legacy.dispose()
