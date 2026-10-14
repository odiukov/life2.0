"""One behavior contract for every HouseholdRepository backend."""

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from uuid import UUID, uuid4

import pytest
from household.adapters.db import household_uow
from household.application.ports import HouseholdRepository
from household.domain.errors import (
    CannotRemoveSelf,
    InviteInvalid,
    InviteOwnHousehold,
    NotMember,
    NotOwner,
    SoleMember,
)
from household.domain.invite import InviteCode
from household.domain.model import Role
from household.testing import InMemoryHouseholds, in_memory_uow
from shared.adapters.db.engine import create_engine
from shared.config import DatabaseSettings
from shared.ports.uow import UnitOfWorkFactory
from shared.testing.fakes import FixedClock
from shared.testing.pytest_plugin import PostgresUrls

NOW = datetime.now(UTC)


@dataclass
class Backend:
    uow: UnitOfWorkFactory


async def memory_backend(request: pytest.FixtureRequest) -> AsyncIterator[Backend]:
    yield Backend(in_memory_uow(InMemoryHouseholds(FixedClock(NOW))))


async def sql_backend(request: pytest.FixtureRequest) -> AsyncIterator[Backend]:
    urls: PostgresUrls = request.getfixturevalue("clean_db")
    engine = create_engine(DatabaseSettings.model_validate({"dsn": urls.rw}))
    try:
        yield Backend(household_uow(engine))
    finally:
        await engine.dispose()


BACKENDS: dict[str, Callable[[pytest.FixtureRequest], AsyncIterator[Backend]]] = {
    "memory": memory_backend,
    "sql": sql_backend,
}


@pytest.fixture(params=["memory", pytest.param("sql", marks=pytest.mark.integration)])
async def backend(request: pytest.FixtureRequest) -> AsyncIterator[Backend]:
    generator = BACKENDS[request.param](request)
    try:
        yield await generator.__anext__()
    finally:
        await generator.aclose()


async def call(backend: Backend, user: UUID, op: Callable[[HouseholdRepository], object]) -> object:
    async with backend.uow.for_user(user) as uow:
        return await op(uow.repo(HouseholdRepository))  # type: ignore[misc]


def code(n: int) -> bytes:
    return InviteCode.parse(f"BBBB-BBB{n}").digest()


async def household_of(backend: Backend, user: UUID, name: str = "u") -> UUID:
    return await call(backend, user, lambda r: r.ensure(user, name=name, timezone="Europe/Lisbon"))  # type: ignore[return-value]


async def test_ensure_then_get(backend: Backend) -> None:
    user = uuid4()
    hid = await household_of(backend, user, "Олег")
    household = await call(backend, user, lambda r: r.get(user))
    assert household.id == hid  # type: ignore[attr-defined]
    assert household.timezone == "Europe/Lisbon"  # type: ignore[attr-defined]
    assert household.digest_time == time(18, 0)  # type: ignore[attr-defined]
    assert [(m.display_name, m.role) for m in household.members] == [("Олег", Role.OWNER)]  # type: ignore[attr-defined]


async def test_invite_preview_join_leave_remove(backend: Backend) -> None:
    a, b, c = uuid4(), uuid4(), uuid4()
    home = await household_of(backend, a, "A")
    await household_of(backend, b, "B")
    await household_of(backend, c, "C")
    await call(
        backend,
        a,
        lambda r: r.create_invite(a, code_hash=code(1), expires_at=NOW + timedelta(days=2)),
    )
    with pytest.raises(InviteOwnHousehold):
        await call(backend, a, lambda r: r.preview(a, code(1)))
    preview = await call(backend, b, lambda r: r.preview(b, code(1)))
    assert (preview.household_name, preview.member_count) == ("A", 1)  # type: ignore[attr-defined]
    assert await call(backend, b, lambda r: r.join(b, code(1))) == home
    with pytest.raises(InviteInvalid):
        await call(backend, c, lambda r: r.join(c, code(1)))
    with pytest.raises(NotOwner):
        await call(backend, b, lambda r: r.update(b, name="X", timezone=None, digest_time=None))
    with pytest.raises(CannotRemoveSelf):
        await call(backend, a, lambda r: r.remove_member(a, a))
    with pytest.raises(NotMember):
        await call(backend, a, lambda r: r.remove_member(a, c))
    fresh = await call(backend, b, lambda r: r.leave(b))
    assert fresh != home
    with pytest.raises(SoleMember):
        await call(backend, a, lambda r: r.leave(a))


async def test_owner_update_and_remove_member_preserve_display_names(backend: Backend) -> None:
    owner, member = uuid4(), uuid4()
    home = await household_of(backend, owner, "Owner")
    await household_of(backend, member, "Member")
    assert await household_of(backend, owner, "Ignored") == home
    await call(
        backend,
        owner,
        lambda r: r.update(owner, name="Shared", timezone="Asia/Tokyo", digest_time=time(19, 30)),
    )
    await call(
        backend,
        owner,
        lambda r: r.create_invite(owner, code_hash=code(2), expires_at=NOW + timedelta(days=2)),
    )
    await call(backend, member, lambda r: r.join(member, code(2)))
    await call(backend, owner, lambda r: r.remove_member(owner, member))
    own = await call(backend, owner, lambda r: r.get(owner))
    fresh = await call(backend, member, lambda r: r.get(member))
    assert own.name == "Shared"  # type: ignore[attr-defined]
    assert own.digest_time == time(19, 30)  # type: ignore[attr-defined]
    assert [m.user_id for m in own.members] == [owner]  # type: ignore[attr-defined]
    assert fresh.id != home  # type: ignore[attr-defined]
    assert fresh.timezone == "Asia/Tokyo"  # type: ignore[attr-defined]
    assert [(m.display_name, m.role) for m in fresh.members] == [("Member", Role.OWNER)]  # type: ignore[attr-defined]
