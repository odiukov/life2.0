from datetime import UTC, datetime
from uuid import uuid4

import pytest
from shared.adapters.db.engine import create_engine
from shared.adapters.db.uow import SqlUnitOfWorkFactory
from shared.adapters.notifications import notification_repositories
from shared.config import DatabaseSettings
from shared.ports.notifications import Notification, NotificationInbox, PushTokens
from shared.testing.pytest_plugin import PostgresUrls
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.integration
T0 = datetime(2026, 10, 14, 18, 0, tzinfo=UTC)


async def test_users_see_only_their_notifications_and_tokens_move_between_users(
    clean_db: PostgresUrls,
) -> None:
    admin = create_async_engine(clean_db.admin)
    a, b = uuid4(), uuid4()
    async with admin.begin() as conn:
        await conn.execute(
            text("INSERT INTO users (id, name) VALUES (:a, 'a'), (:b, 'b')"), {"a": a, "b": b}
        )
    engine = create_engine(DatabaseSettings.model_validate({"dsn": clean_db.rw}))
    uow = SqlUnitOfWorkFactory(engine, notification_repositories())
    try:
        async with uow.for_user(a) as tx:
            await tx.repo(NotificationInbox).add(a, Notification("k", "t", "b"), created_at=T0)
            await tx.repo(PushTokens).upsert(a, "ExponentPushToken[phone]", "ios", at=T0)
        async with uow.for_user(b) as tx:
            assert await tx.repo(NotificationInbox).page(b, before=None, limit=10) == []
            assert await tx.repo(PushTokens).for_user(a) == []
            # b signs in on a's phone: the token now belongs to b only.
            await tx.repo(PushTokens).upsert(b, "ExponentPushToken[phone]", "ios", at=T0)
            assert await tx.repo(PushTokens).for_user(b) == ["ExponentPushToken[phone]"]
        async with uow.for_user(a) as tx:
            assert await tx.repo(PushTokens).for_user(a) == []
        async with engine.connect() as conn:  # no tenant
            assert (
                await conn.execute(text("SELECT count(*) FROM notifications"))
            ).scalar_one() == 0
    finally:
        await engine.dispose()
        await admin.dispose()


async def test_claim_permissions_and_direct_cross_tenant_writes(clean_db: PostgresUrls) -> None:
    admin = create_async_engine(clean_db.admin)
    rw = create_async_engine(clean_db.rw)
    legacy = create_async_engine(clean_db.legacy)
    a, b = uuid4(), uuid4()
    try:
        async with admin.begin() as conn:
            await conn.execute(
                text("INSERT INTO users (id, name) VALUES (:a, 'a'), (:b, 'b')"),
                {"a": a, "b": b},
            )
        async with rw.begin() as conn:
            await conn.execute(text("SELECT set_config('app.user_id', :u, true)"), {"u": str(a)})
            await conn.execute(
                text(
                    "INSERT INTO push_tokens (token, user_id, platform) VALUES ('device', :u, 'ios')"
                ),
                {"u": a},
            )
        async with rw.begin() as conn:
            await conn.execute(text("SELECT set_config('app.user_id', :u, true)"), {"u": str(a)})
            with pytest.raises(DBAPIError, match="row-level security"):
                await conn.execute(
                    text("UPDATE push_tokens SET user_id = :b WHERE token = 'device'"), {"b": b}
                )
        async with rw.begin() as conn:
            with pytest.raises(DBAPIError, match="no_tenant"):
                await conn.execute(text("SELECT public.push_token_claim('x'::text, 'ios'::text)"))
        async with legacy.connect() as conn:
            assert (
                await conn.execute(
                    text(
                        "SELECT has_function_privilege('app_legacy', 'public.push_token_claim(text,text)', 'EXECUTE')"
                    )
                )
            ).scalar_one() is False
    finally:
        await admin.dispose()
        await rw.dispose()
        await legacy.dispose()
