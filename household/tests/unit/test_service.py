from datetime import UTC, datetime, time
from uuid import uuid4

import pytest
from household.application.service import INVITE_TTL, HouseholdChanges, HouseholdService
from household.domain.errors import (
    InvalidSettings,
    InviteInvalid,
    InviteOwnHousehold,
    InviteRateLimited,
    NotOwner,
    SoleMember,
)
from household.domain.invite import InviteCode
from household.domain.model import Role
from household.testing import InMemoryHouseholds, in_memory_uow
from shared.testing.fakes import FixedClock

NOW = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)


def service(
    clock: FixedClock | None = None, **kw: object
) -> tuple[HouseholdService, InMemoryHouseholds]:
    clock = clock or FixedClock(NOW)
    repo = InMemoryHouseholds(clock, **kw)  # type: ignore[arg-type]
    codes = iter([InviteCode.parse(f"AAAA-AAA{i}") for i in range(10)])
    return HouseholdService(in_memory_uow(repo), clock, new_code=lambda: next(codes)), repo


async def test_ensure_is_idempotent_and_owner() -> None:
    svc, _ = service()
    user = uuid4()
    first = await svc.ensure(user)
    assert await svc.ensure(user) == first
    household = await svc.get(user)
    assert household.role_of(user) is Role.OWNER


async def test_invite_then_join_moves_items_of_a_sole_member() -> None:
    moved: list[tuple[object, object]] = []
    svc, _ = service(item_count=lambda h: 7, on_move=lambda old, new: moved.append((old, new)))
    owner, joiner = uuid4(), uuid4()
    target = await svc.ensure(owner)
    old = await svc.ensure(joiner)
    invite = await svc.create_invite(owner)
    assert invite.expires_at == NOW + INVITE_TTL
    preview = await svc.preview(joiner, invite.code.display.lower())
    assert (preview.member_count, preview.items_to_move) == (1, 7)
    assert await svc.join(joiner, invite.code.value) == target
    assert moved == [(old, target)]
    assert {m.user_id for m in (await svc.get(owner)).members} == {owner, joiner}


async def test_join_errors() -> None:
    clock = FixedClock(NOW)
    svc, _ = service(clock)
    owner, other = uuid4(), uuid4()
    await svc.ensure(owner)
    await svc.ensure(other)
    invite = await svc.create_invite(owner)
    with pytest.raises(InviteOwnHousehold):
        await svc.join(owner, invite.code.value)
    with pytest.raises(InviteInvalid):
        await svc.join(other, "not-a-code")
    clock.advance(hours=49)
    with pytest.raises(InviteInvalid):
        await svc.join(other, invite.code.value)


async def test_malformed_codes_count_towards_the_rate_limit() -> None:
    svc, _ = service()
    owner, attacker = uuid4(), uuid4()
    await svc.ensure(owner)
    await svc.ensure(attacker)
    invite = await svc.create_invite(owner)
    for i in range(5):
        with pytest.raises(InviteInvalid):
            await svc.join(attacker, f"ZZZZ-ZZZ{i}")
    with pytest.raises(InviteRateLimited):
        await svc.join(attacker, invite.code.value)


async def test_update_validates_and_requires_owner() -> None:
    svc, _ = service()
    owner, member = uuid4(), uuid4()
    await svc.ensure(owner)
    await svc.ensure(member)
    await svc.join(member, (await svc.create_invite(owner)).code.value)
    with pytest.raises(NotOwner):
        await svc.update(member, HouseholdChanges(name="X"))
    with pytest.raises(InvalidSettings):
        await svc.update(owner, HouseholdChanges(timezone="Mars/Olympus"))
    with pytest.raises(InvalidSettings):
        await svc.update(owner, HouseholdChanges(name="  "))
    await svc.update(
        owner, HouseholdChanges(name=" Дом ", timezone="Europe/Lisbon", digest_time=time(19, 30))
    )
    household = await svc.get(owner)
    assert (household.name, household.timezone, household.digest_time) == (
        "Дом",
        "Europe/Lisbon",
        time(19, 30),
    )


async def test_sole_member_cannot_leave_and_leaver_gets_fresh_household() -> None:
    svc, _ = service()
    a, b = uuid4(), uuid4()
    home = await svc.ensure(a)
    with pytest.raises(SoleMember):
        await svc.leave(a)
    await svc.ensure(b)
    await svc.join(b, (await svc.create_invite(a)).code.value)
    fresh = await svc.leave(a)
    assert fresh != home
    assert (await svc.get(b)).role_of(b) is Role.OWNER


@pytest.mark.parametrize("operation", ["preview", "join"])
async def test_domain_errors_commit_invite_attempts(operation: str) -> None:
    clock = FixedClock(NOW)
    repo = InMemoryHouseholds(clock)
    uow = in_memory_uow(repo)
    svc = HouseholdService(uow, clock)
    user = uuid4()
    with pytest.raises(InviteInvalid):
        await getattr(svc, operation)(user, "!")
    assert uow.commits == [user]
    assert uow.rollbacks == []
    assert repo.failures[user] == [NOW]


async def test_rate_limit_expires_and_old_attempts_are_pruned() -> None:
    clock = FixedClock(NOW)
    svc, repo = service(clock)
    user = uuid4()
    for _ in range(5):
        with pytest.raises(InviteInvalid):
            await svc.preview(user, "!")
    with pytest.raises(InviteRateLimited):
        await svc.join(user, "!")
    clock.advance(hours=1)
    with pytest.raises(InviteInvalid):
        await svc.join(user, "!")
    clock.advance(hours=24, seconds=1)
    with pytest.raises(InviteInvalid):
        await svc.preview(user, "!")
    assert repo.failures[user] == [clock.now()]


async def test_invites_from_deleted_sole_household_are_invalid() -> None:
    svc, _ = service()
    target, joiner, outsider = uuid4(), uuid4(), uuid4()
    await svc.ensure(target)
    await svc.ensure(joiner)
    abandoned = await svc.create_invite(joiner)
    await svc.join(joiner, (await svc.create_invite(target)).code.value)
    with pytest.raises(InviteInvalid):
        await svc.preview(outsider, abandoned.code.value)


@pytest.mark.parametrize("digest_time", [time(0, 0), time(19, 30), time(23, 59)])
async def test_update_accepts_digest_time_with_minute_precision(digest_time: time) -> None:
    svc, _ = service()
    user = uuid4()
    await svc.ensure(user)
    await svc.update(user, HouseholdChanges(digest_time=digest_time))
    assert (await svc.get(user)).digest_time == digest_time


@pytest.mark.parametrize(
    "digest_time",
    [time(19, 30, 1), time(19, 30, microsecond=1), time(19, 30, tzinfo=UTC)],
)
async def test_update_rejects_unsupported_digest_time_without_mutation(digest_time: time) -> None:
    svc, _ = service()
    user = uuid4()
    await svc.ensure(user)
    before = await svc.get(user)
    with pytest.raises(InvalidSettings):
        await svc.update(user, HouseholdChanges(name="Changed", digest_time=digest_time))
    assert await svc.get(user) == before


async def test_removal_creates_fresh_owner_household_without_moving_items() -> None:
    moved: list[tuple[object, object]] = []
    svc, _ = service(on_move=lambda old, new: moved.append((old, new)))
    owner, member = uuid4(), uuid4()
    home = await svc.ensure(owner)
    await svc.update(owner, HouseholdChanges(timezone="Europe/Lisbon"))
    await svc.ensure(member)
    await svc.join(member, (await svc.create_invite(owner)).code.value)
    before = await svc.get(member)
    display_name = next(m.display_name for m in before.members if m.user_id == member)
    moved.clear()
    await svc.remove_member(owner, member)
    fresh = await svc.get(member)
    assert fresh.id != home
    assert fresh.name == display_name
    assert fresh.timezone == "Europe/Lisbon"
    assert fresh.role_of(member) is Role.OWNER
    assert (await svc.get(owner)).role_of(member) is None
    assert moved == []


async def test_owner_join_from_shared_household_promotes_successor_without_moving_items() -> None:
    moved: list[tuple[object, object]] = []
    svc, _ = service(on_move=lambda old, new: moved.append((old, new)))
    owner, successor, target_owner = uuid4(), uuid4(), uuid4()
    old = await svc.ensure(owner)
    await svc.ensure(successor)
    await svc.join(successor, (await svc.create_invite(owner)).code.value)
    target = await svc.ensure(target_owner)
    moved.clear()
    assert await svc.join(owner, (await svc.create_invite(target_owner)).code.value) == target
    remaining = await svc.get(successor)
    assert remaining.id == old
    assert remaining.role_of(successor) is Role.OWNER
    assert remaining.role_of(owner) is None
    assert (await svc.get(owner)).role_of(owner) is Role.MEMBER
    assert moved == []
