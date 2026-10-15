import asyncio
from datetime import UTC, datetime
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from gateway.feed import FEED_AGENTS, build_router
from shared.ports.skills import SkillCallError, SkillReply, SkillUnavailable
from shared.ports.users import UserSettingsRepository
from shared.skill_ids import Feed
from shared.testing.fakes import (
    FakeSkillClient,
    FixedClock,
    InMemoryUnitOfWorkFactory,
    InMemoryUserSettings,
)

USER = uuid4()
NOW = datetime(2026, 10, 13, 22, 30, tzinfo=UTC)


async def me() -> UUID:
    return USER


def item(**changes):  # type: ignore[no-untyped-def]
    return {
        "id": "one",
        "at": "2026-10-14T08:00:00+03:00",
        "kind": "event",
        "text": "event",
        **changes,
    }


def clients(overrides=None):  # type: ignore[no-untyped-def]
    seen = {}

    def responder(agent):  # type: ignore[no-untyped-def]
        def answer(skill, user, params, text):  # type: ignore[no-untyped-def]
            assert skill == Feed.EVENTS
            assert user == USER
            seen.setdefault(agent, []).append(dict(params))
            if overrides and agent in overrides:
                return overrides[agent]
            minute = FEED_AGENTS.index(agent)
            return SkillReply(
                "",
                {
                    "items": [
                        item(
                            id=f"{agent}:1",
                            at=f"{params['date']}T08:{minute:02d}:00+03:00",
                            text=agent,
                        )
                    ]
                },
            )

        return answer

    fakes = {a: FakeSkillClient(responder(a)) for a in FEED_AGENTS}
    return fakes.__getitem__, fakes, seen


def api(lookup, timeout_s=3.0, authenticate=me, timezone="Europe/Kyiv"):  # type: ignore[no-untyped-def]
    settings = InMemoryUserSettings()
    settings.seed(USER, timezone=timezone)
    app = FastAPI()
    app.include_router(
        build_router(
            lookup,
            InMemoryUnitOfWorkFactory({UserSettingsRepository: settings}),
            FixedClock(NOW),
            authenticate,
            timeout_s=timeout_s,
        )
    )
    return app


async def get(app: FastAPI, path: str = "/me/feed") -> httpx.Response:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://t"
    ) as client:
        return await client.get(path)


async def test_merges_every_agent_newest_first_and_uses_local_day() -> None:
    lookup, _, seen = clients()
    response = await get(api(lookup))
    assert response.status_code == 200
    body = response.json()
    assert body["unavailable"] == []
    assert body["date"] == "2026-10-14"
    assert [i["agent"] for i in body["items"]] == list(reversed(FEED_AGENTS))
    assert body["items"][0] == {
        "agent": "calendar",
        "id": "calendar:1",
        "at": "2026-10-14T08:08:00+03:00",
        "kind": "event",
        "text": "calendar",
    }
    assert set(seen) == set(FEED_AGENTS)
    assert all(calls == [{"date": "2026-10-14"}] for calls in seen.values())


@pytest.mark.parametrize("day", ["2026-10-15", "2026-09-13"])
async def test_out_of_range(day: str) -> None:
    lookup, _, seen = clients()
    response = await get(api(lookup), f"/me/feed?date={day}")
    assert response.status_code == 422
    assert response.json() == {"detail": "date_out_of_range"}
    assert not seen


async def test_oldest_allowed_day() -> None:
    lookup, _, _ = clients()
    assert (await get(api(lookup), "/me/feed?date=2026-09-14")).status_code == 200


@pytest.mark.parametrize(
    "day", ["", "tomorrow", "2026-02-30", "20261014", "2026-W42-3", "2026-10-14T00:00:00Z"]
)
async def test_invalid_date_is_machine_code(day: str) -> None:
    lookup, _, seen = clients()
    response = await get(api(lookup), f"/me/feed?date={day}")
    assert response.status_code == 422
    assert response.json() == {"detail": "invalid_params"}
    assert not seen


async def test_dead_failed_and_slow_agents_are_unavailable() -> None:
    lookup, fakes, _ = clients({"mood": SkillUnavailable("down"), "body": SkillCallError("failed")})

    async def hang(*args, **kwargs):  # type: ignore[no-untyped-def]
        await asyncio.sleep(3600)

    fakes["calendar"].call = hang  # type: ignore[method-assign]
    body = (await get(api(lookup, timeout_s=0.02))).json()
    assert body["unavailable"] == ["body", "mood", "calendar"]
    assert {i["agent"] for i in body["items"]} == set(FEED_AGENTS) - {"body", "mood", "calendar"}


@pytest.mark.parametrize(
    "data",
    [
        None,
        [],
        "junk",
        {},
        {"items": {}},
        {"items": [item(), "junk"]},
        {"items": [item(id=1)]},
        {"items": [item(at="2026-10-14T08:00:00")]},
        {"items": [item(at="bad")]},
        {"items": [item(at=1)]},
        {"items": [item(at="2026-10-14T22:00:00Z")]},
        {"items": [item(text="x" * 141)]},
        {"items": [item(text="")]},
        {"items": [item(text=" ")]},
        {"items": [item(kind="other")]},
        {"items": [item()] * 51},
    ],
)
async def test_malformed_peer_batch_is_isolated(data: object) -> None:
    lookup, _, _ = clients({"sleep": SkillReply("", data)})  # type: ignore[arg-type]
    response = await get(api(lookup))
    assert response.status_code == 200
    body = response.json()
    assert body["unavailable"] == ["sleep"]
    assert len(body["items"]) == 8


async def test_trusted_attribution_and_limit_boundaries() -> None:
    lookup, _, _ = clients(
        {"sleep": SkillReply("", {"items": [item(agent="mood", text="x" * 140)] * 50})}
    )
    body = (await get(api(lookup))).json()
    assert body["unavailable"] == []
    assert len([i for i in body["items"] if i["agent"] == "sleep"]) == 50


async def test_requires_authentication() -> None:
    async def nobody() -> UUID:
        raise HTTPException(401, "missing_bearer_token")

    lookup, _, seen = clients()
    assert (await get(api(lookup, authenticate=nobody))).status_code == 401
    assert not seen


async def test_utc_default_and_explicit_offsets_use_settings_day() -> None:
    lookup, _, seen = clients()
    body = (await get(api(lookup, timezone=None))).json()
    assert body["date"] == "2026-10-13"
    assert all(calls == [{"date": "2026-10-13"}] for calls in seen.values())


@pytest.mark.parametrize("at", ["2026-10-13T21:00:00Z", "2026-10-14T20:59:59Z"])
async def test_local_day_bounds_accept_different_offsets(at: str) -> None:
    lookup, _, _ = clients({"sleep": SkillReply("", {"items": [item(at=at)]})})
    body = (await get(api(lookup))).json()
    assert body["unavailable"] == []
    assert len(body["items"]) == 9
