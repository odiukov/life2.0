"""Persistence and actor isolation of the SQL household adapter."""

from datetime import timedelta
from uuid import uuid4

import pytest
from household.adapters.db import household_uow
from household.application.ports import HouseholdRepository
from household.application.service import HouseholdService
from household.domain.errors import InviteInvalid, InviteRateLimited, NoHousehold
from shared.adapters.clock import SystemClock
from shared.adapters.db.engine import create_engine
from shared.config import DatabaseSettings
from shared.schema.tables import household_invites
from shared.testing.pytest_plugin import PostgresUrls
from sqlalchemy import select

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("operation", ["preview", "join"])
@pytest.mark.parametrize("invalid_code", ["ZZZZ-ZZZ0", "malformed"])
async def test_failed_attempts_survive_the_error_and_trigger_the_limit(
    clean_db: PostgresUrls, operation: str, invalid_code: str
) -> None:
    engine = create_engine(DatabaseSettings.model_validate({"dsn": clean_db.rw}))
    try:
        svc = HouseholdService(household_uow(engine), SystemClock())
        owner, attacker, other = uuid4(), uuid4(), uuid4()
        await svc.ensure(owner)
        await svc.ensure(attacker)
        await svc.ensure(other)
        invite = await svc.create_invite(owner)
        action = getattr(svc, operation)
        for _ in range(5):
            with pytest.raises(InviteInvalid):
                await action(attacker, invalid_code)
        with pytest.raises(InviteRateLimited):
            await action(attacker, invite.code.value)
        # Another actor's valid preview still works: attempts are tenant-scoped.
        assert (await svc.preview(other, invite.code.value)).member_count == 1
    finally:
        await engine.dispose()


async def test_repository_uses_uow_actor_even_with_another_user_argument(
    clean_db: PostgresUrls,
) -> None:
    engine = create_engine(DatabaseSettings.model_validate({"dsn": clean_db.rw}))
    try:
        factory = household_uow(engine)
        svc = HouseholdService(factory, SystemClock())
        actor, other, unknown = uuid4(), uuid4(), uuid4()
        mine, theirs = await svc.ensure(actor), await svc.ensure(other)
        async with factory.for_user(unknown) as uow:
            with pytest.raises(NoHousehold):
                await uow.repo(HouseholdRepository).get(actor)
        async with factory.for_user(actor) as uow:
            repo = uow.repo(HouseholdRepository)
            assert await repo.ensure(other, name="ignored", timezone="UTC") == mine
            assert (await repo.get(other)).id == mine
            await repo.update(other, name="Actor home", timezone="Europe/Lisbon", digest_time=None)
            await repo.create_invite(
                other, code_hash=b"x" * 32, expires_at=SystemClock().now() + timedelta(days=2)
            )
            row = (await uow.connection.execute(select(household_invites))).one()
            assert row.household_id == mine
            assert row.created_by == actor
        assert (await svc.get(other)).id == theirs
        assert (await svc.get(other)).name != "Actor home"
        assert [m.user_id for m in (await svc.get(actor)).members] == [actor]
    finally:
        await engine.dispose()
