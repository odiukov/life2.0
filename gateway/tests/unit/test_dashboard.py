import asyncio
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI
from gateway.dashboard import build_router
from shared.ports.skills import SkillReply, SkillUnavailable
from shared.skill_ids import Dashboard
from shared.testing import dashboard_golden as g
from shared.testing.fakes import FakeSkillClient


async def me() -> UUID:
    return g.USER_ID


def clients(overrides: dict | None = None):  # type: ignore[no-untyped-def]
    def responder(agent: str):  # type: ignore[no-untyped-def]
        def answer(skill: str, user, params, text):  # type: ignore[no-untyped-def]
            if overrides and agent in overrides:
                return overrides[agent]
            return SkillReply(
                "", g.expected_card(agent) if skill == Dashboard.CARD else g.expected_detail(agent)
            )

        return answer

    fakes = {
        name: FakeSkillClient(responder(name)) for name in set(g.TILE_ORDER) | set(g.DETAIL_AGENTS)
    }
    return fakes.__getitem__, fakes


def api(lookup, timeout_s: float = 3.0) -> FastAPI:  # type: ignore[no-untyped-def]
    app = FastAPI()
    app.include_router(build_router(lookup, None, None, me, timeout_s=timeout_s))  # type: ignore[arg-type]
    return app


async def get(app: FastAPI, path: str) -> httpx.Response:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://t"
    ) as client:
        return await client.get(path)


async def test_summary_reassembles_the_golden() -> None:
    lookup, _ = clients()
    body = (await get(api(lookup), "/dashboard/summary")).json()
    assert body.pop("unavailable") == []
    assert body == g.golden("dashboard_summary")


async def test_a_dead_agent_drops_out_and_is_named() -> None:
    lookup, _ = clients({"recovery": SkillUnavailable("down")})
    body = (await get(api(lookup), "/dashboard/summary")).json()
    assert body["unavailable"] == ["recovery"]
    assert "recovery" not in [t["agent"] for t in body["agents"]]
    assert body["rings"]["readyPct"] is None
    assert body["rings"]["hrvPct"] is not None


async def test_a_slow_agent_does_not_stall_the_summary() -> None:
    lookup, fakes = clients()

    async def hang(*args, **kwargs):  # type: ignore[no-untyped-def]
        await asyncio.sleep(3600)

    fakes["calendar"].call = hang  # type: ignore[method-assign]
    body = (await get(api(lookup, timeout_s=0.05), "/dashboard/summary")).json()
    assert body["unavailable"] == ["calendar"]


async def test_detail_proxies_and_maps_errors() -> None:
    lookup, _ = clients({"mood": SkillUnavailable("down")})
    app = api(lookup)
    assert (await get(app, "/agents/sleep/detail")).json() == g.expected_detail("sleep")
    assert (await get(app, "/agents/body/detail")).status_code == 404  # body has no detail
    assert (await get(app, "/agents/mood/detail")).status_code == 503


@pytest.mark.parametrize("path", ["/dashboard/summary", "/agents/sleep/detail"])
async def test_dashboard_requires_sign_in(path: str) -> None:
    from fastapi import HTTPException

    async def nobody() -> UUID:
        raise HTTPException(status_code=401, detail="missing_bearer_token")

    lookup, _ = clients()
    app = FastAPI()
    app.include_router(build_router(lookup, None, None, nobody))
    assert (await get(app, path)).status_code == 401
