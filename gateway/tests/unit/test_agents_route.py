from datetime import UTC, datetime
from uuid import UUID, uuid4

import httpx
import respx
from fastapi import FastAPI, HTTPException
from gateway.agents import CARD_PATH, AgentDirectory, TaskCounts, build_agents_router
from shared.ports.users import UserSettingsRepository
from shared.testing.fakes import FixedClock, InMemoryUnitOfWorkFactory, InMemoryUserSettings

USER = uuid4()
URLS = {"sleep": "http://agent-sleep:8001/", "home": "http://agent-home:8013/"}
CARD = {
    "name": "sleep-agent",
    "description": "Sleep.",
    "skills": [{"id": "log_sleep", "name": "Log Sleep"}],
}


class Counts:
    async def since(self, user_id: UUID, agent: str, start: datetime) -> int:
        return 3 if (user_id, agent) == (USER, "sleep") else 0


async def me() -> UUID:
    return USER


async def nobody() -> UUID:
    raise HTTPException(status_code=401, detail="missing_bearer_token")


@respx.mock
async def test_lists_every_configured_agent_with_live_status() -> None:
    card = respx.get(f"http://agent-sleep:8001/{CARD_PATH}").respond(json=CARD)
    respx.get("http://agent-sleep:8001/health").respond(json={"status": "ok"})
    respx.get(f"http://agent-home:8013/{CARD_PATH}").mock(side_effect=httpx.ConnectError("down"))
    respx.get("http://agent-home:8013/health").mock(side_effect=httpx.ConnectError("down"))
    async with httpx.AsyncClient() as http:
        directory = AgentDirectory(URLS, http)
        uow = InMemoryUnitOfWorkFactory(
            {UserSettingsRepository: InMemoryUserSettings(), TaskCounts: Counts()}
        )
        app = FastAPI()
        app.include_router(
            build_agents_router(
                directory, uow, FixedClock(datetime(2026, 10, 14, 9, tzinfo=UTC)), me
            )
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://t"
        ) as client:
            first = (await client.get("/agents")).json()["agents"]
            await client.get("/agents")
    assert [a["name"] for a in first] == ["sleep", "home"]
    assert first[0] == {
        "name": "sleep",
        "url": URLS["sleep"],
        "online": True,
        "skills": [{"id": "log_sleep", "name": "Log Sleep"}],
        "description": "Sleep.",
        "tasks_today": 3,
    }
    assert first[1]["online"] is False
    assert first[1]["skills"] == []
    assert card.call_count == 1  # cached for the TTL


async def test_requires_sign_in() -> None:
    async with httpx.AsyncClient() as http:
        app = FastAPI()
        app.include_router(
            build_agents_router(
                AgentDirectory(URLS, http),
                InMemoryUnitOfWorkFactory({}),
                FixedClock(datetime.now(UTC)),
                nobody,
            )
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://t"
        ) as client:
            assert (await client.get("/agents")).status_code == 401


@respx.mock
async def test_directory_recovers_late_agents_and_keeps_cards_during_outages() -> None:
    route = respx.get(f"http://agent-sleep:8001/{CARD_PATH}")
    route.mock(side_effect=httpx.ConnectError("down"))
    health = respx.get("http://agent-sleep:8001/health").respond(503)
    async with httpx.AsyncClient() as http:
        directory = AgentDirectory(URLS, http, card_ttl_s=0)
        assert await directory.card("sleep") is None
        assert await directory.online("sleep") is False
        route.respond(json=CARD)
        health.respond(200)
        assert await directory.card("sleep") == CARD
        assert await directory.online("sleep") is True
        route.respond(503)
        health.respond(503)
        assert await directory.card("sleep") == CARD
        assert await directory.online("sleep") is False


@respx.mock
async def test_invalid_card_is_unavailable() -> None:
    respx.get(f"http://agent-sleep:8001/{CARD_PATH}").respond(
        content="null", content_type="application/json"
    )
    async with httpx.AsyncClient() as http:
        assert await AgentDirectory(URLS, http).card("sleep") is None
