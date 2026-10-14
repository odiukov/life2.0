from datetime import UTC, datetime
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI, Header
from household.adapters.http import build_router
from household.application.service import HouseholdService
from household.domain.invite import InviteCode
from household.testing import InMemoryHouseholds, in_memory_uow
from shared.testing.fakes import FixedClock

NOW = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)


async def dev_user(x_user_id: str = Header(alias="X-User-Id")) -> UUID:
    return UUID(x_user_id)


@pytest.fixture
def env() -> tuple[httpx.AsyncClient, HouseholdService]:
    codes = iter([InviteCode.parse("CCCC-CCC1"), InviteCode.parse("CCCC-CCC2")])
    svc = HouseholdService(
        in_memory_uow(InMemoryHouseholds(FixedClock(NOW))),
        FixedClock(NOW),
        new_code=lambda: next(codes),
    )
    app = FastAPI()
    app.include_router(build_router(svc, dev_user))
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t"), svc


def h(user: UUID) -> dict[str, str]:
    return {"X-User-Id": str(user)}


async def test_get_404s_without_household(env: tuple[httpx.AsyncClient, HouseholdService]) -> None:
    client, _ = env
    response = await client.get("/household", headers=h(uuid4()))
    assert (response.status_code, response.json()) == (404, {"detail": "no_household"})


async def test_full_flow(env: tuple[httpx.AsyncClient, HouseholdService]) -> None:
    client, svc = env
    a, b = uuid4(), uuid4()
    for user in (a, b):  # in production the post-auth hook does this
        await svc.ensure(user)
    created = (await client.post("/household/invites", headers=h(a))).json()
    assert created["code"] == "CCCC-CCC1"
    preview = await client.post("/household/join/preview", headers=h(b), json={"code": "cccc ccc1"})
    assert preview.status_code == 200
    assert preview.json()["member_count"] == 1
    joined = await client.post("/household/join", headers=h(b), json={"code": "CCCC-CCC1"})
    assert joined.status_code == 200
    assert {m["user_id"] for m in joined.json()["members"]} == {str(a), str(b)}
    assert joined.json()["my_role"] == "member"
    forbidden = await client.patch("/household", headers=h(b), json={"name": "X"})
    assert (forbidden.status_code, forbidden.json()) == (403, {"detail": "not_owner"})
    bad = await client.patch("/household", headers=h(a), json={"timezone": "Nowhere/City"})
    assert (bad.status_code, bad.json()) == (422, {"detail": "invalid_settings"})
    ok = await client.patch(
        "/household", headers=h(a), json={"name": "Дом", "digest_time": "19:30"}
    )
    assert ok.json()["name"] == "Дом"
    assert ok.json()["digest_time"] == "19:30"
    again = await client.post("/household/join", headers=h(b), json={"code": "CCCC-CCC1"})
    assert (again.status_code, again.json()) == (404, {"detail": "invite_invalid"})
    removed = await client.delete(f"/household/members/{b}", headers=h(a))
    assert removed.status_code == 204
    left = await client.post("/household/leave", headers=h(a))
    assert (left.status_code, left.json()) == (409, {"detail": "household_sole_member"})


@pytest.mark.parametrize(
    "digest_time",
    ["19:30:00", "19:30:01", "19:30:00.5", "19:30Z", "19:30+01:00", "7:30", "24:00", "bad", 3600],
)
async def test_digest_time_requires_minute_only_local_time(
    env: tuple[httpx.AsyncClient, HouseholdService], digest_time: object
) -> None:
    client, svc = env
    user = uuid4()
    await svc.ensure(user)
    previous = (await svc.get(user)).digest_time
    response = await client.patch("/household", headers=h(user), json={"digest_time": digest_time})
    assert (response.status_code, response.json()) == (422, {"detail": "invalid_settings"})
    assert (await svc.get(user)).digest_time == previous


async def test_all_household_error_statuses(
    env: tuple[httpx.AsyncClient, HouseholdService],
) -> None:
    client, svc = env
    owner, outsider = uuid4(), uuid4()
    await svc.ensure(owner)
    await svc.ensure(outsider)
    invite = (await client.post("/household/invites", headers=h(owner))).json()["code"]
    response = await client.post("/household/join", headers=h(owner), json={"code": invite})
    assert (response.status_code, response.json()) == (409, {"detail": "invite_own"})
    response = await client.delete(f"/household/members/{owner}", headers=h(owner))
    assert (response.status_code, response.json()) == (409, {"detail": "cannot_remove_self"})
    response = await client.delete(f"/household/members/{outsider}", headers=h(owner))
    assert (response.status_code, response.json()) == (404, {"detail": "not_member"})
    for _ in range(5):
        response = await client.post(
            "/household/join/preview", headers=h(outsider), json={"code": "bad"}
        )
        assert response.status_code == 404
    response = await client.post(
        "/household/join/preview", headers=h(outsider), json={"code": "bad"}
    )
    assert (response.status_code, response.json()) == (429, {"detail": "invite_rate_limited"})
