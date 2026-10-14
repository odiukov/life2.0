"""First-request authentication must bootstrap before either real chat route runs."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID, uuid4

import httpx
import pytest

from household.application.service import HouseholdService
from household.domain.errors import NoHousehold
from household.testing import InMemoryHouseholds, in_memory_uow
from shared.testing.fakes import FixedClock


@pytest.mark.parametrize("path", ["/chat/stream", "/agent/kitchen/stream"])
@pytest.mark.parametrize("mode", ["dev", "supabase"])
async def test_post_auth_hook_runs_for_legacy_routes(monkeypatch, path, mode):
    from gateway.hooks import HouseholdEnsurer
    from orchestrator.app import auth, main, agent_passthrough

    clock = FixedClock(datetime(2026, 10, 14, 12, tzinfo=UTC))
    repo = InMemoryHouseholds(clock)
    service = HouseholdService(in_memory_uow(repo), clock)
    user = uuid4()
    events = []

    async def ensure_household(user_id):
        events.append("ensure_started")
        await asyncio.sleep(0)
        result = await service.ensure(user_id)
        events.append("ensure_completed")
        return result

    class Ensures:
        ensure = staticmethod(ensure_household)

    monkeypatch.setattr(auth, "AUTH_MODE", mode)
    monkeypatch.setattr(auth, "POST_AUTH_HOOKS", [HouseholdEnsurer(Ensures())])
    monkeypatch.setattr(auth, "verify_jwt", lambda _: user)

    async def ensure_user_row(user_id):
        events.append("user_row")

    monkeypatch.setattr(auth, "_ensure_user_row", ensure_user_row)
    monkeypatch.setattr(agent_passthrough, "get_agent_url", lambda _: "http://kitchen:8009")

    async def graph(text, user_id, thread_id, timezone):
        household = await service.get(UUID(user_id))
        assert household.role_of(user) is not None
        events.append("agent")
        yield "kitchen", [], "ok"

    async def peer(*, agent, message, user_id):
        household = await service.get(UUID(user_id))
        assert household.role_of(user) is not None
        events.append("agent")
        yield {"type": "text", "delta": "ok"}

    monkeypatch.setattr(main, "_run_graph_with_routing", graph)
    monkeypatch.setattr(agent_passthrough, "stream_peer_call", peer)
    headers = {"X-User-Id": str(user)} if mode == "dev" else {"Authorization": "Bearer test"}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=main.app), base_url="http://t"
    ) as client:
        response = await client.post(
            path, headers=headers, json={"messages": [{"role": "user", "content": "bought milk"}]}
        )
    assert response.status_code == 200
    assert '"delta": "ok"' in response.text
    assert events == (["user_row"] if mode == "supabase" else []) + [
        "ensure_started",
        "ensure_completed",
        "agent",
    ]
    assert len(repo.households) == 1


@pytest.mark.parametrize("path", ["/chat/stream", "/agent/kitchen/stream"])
async def test_failed_bootstrap_retries_and_kitchen_boundary_rejects_without_writes(
    monkeypatch, path
):
    from gateway.hooks import HouseholdEnsurer
    from orchestrator.app import auth, main, agent_passthrough

    clock = FixedClock(datetime(2026, 10, 14, 12, tzinfo=UTC))
    service = HouseholdService(in_memory_uow(InMemoryHouseholds(clock)), clock)
    user = uuid4()
    attempts, writes, failures = [], [], []

    class Broken:
        async def ensure(self, user_id):
            attempts.append(user_id)
            raise RuntimeError("db down")

    monkeypatch.setattr(auth, "AUTH_MODE", "dev")
    monkeypatch.setattr(auth, "POST_AUTH_HOOKS", [HouseholdEnsurer(Broken())])
    monkeypatch.setattr(agent_passthrough, "get_agent_url", lambda _: "http://kitchen:8009")

    async def kitchen(user_id):
        try:
            await service.get(UUID(user_id))
        except NoHousehold as error:
            failures.append(error.code)
            return error.code
        writes.append(user_id)
        return "unexpected_write"

    async def graph(text, user_id, thread_id, timezone):
        yield "kitchen", [], await kitchen(user_id)

    async def peer(*, agent, message, user_id):
        yield {"type": "text", "delta": await kitchen(user_id)}

    monkeypatch.setattr(main, "_run_graph_with_routing", graph)
    monkeypatch.setattr(agent_passthrough, "stream_peer_call", peer)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=main.app), base_url="http://t"
    ) as client:
        for _ in range(2):
            response = await client.post(
                path,
                headers={"X-User-Id": str(user)},
                json={"messages": [{"role": "user", "content": "bought milk"}]},
            )
            assert response.status_code == 200
            assert '"delta": "no_household"' in response.text
    assert attempts == [user, user]
    assert failures == ["no_household", "no_household"]
    assert writes == []


async def test_failing_hook_does_not_block_later_hooks_or_legacy_auth(monkeypatch):
    from orchestrator.app import auth, main

    seen = []

    async def boom(user_id):
        raise RuntimeError("db down")

    async def later(user_id):
        seen.append(user_id)

    monkeypatch.setattr(auth, "AUTH_MODE", "dev")
    monkeypatch.setattr(auth, "POST_AUTH_HOOKS", [boom, later])
    user = uuid4()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=main.app), base_url="http://t"
    ) as client:
        response = await client.post(
            "/chat/stream", headers={"X-User-Id": str(user)}, json={"messages": []}
        )
    assert response.status_code == 400
    assert seen == [user]


@pytest.mark.parametrize("header", [None, "invalid"])
async def test_failed_authentication_does_not_run_hooks(monkeypatch, header):
    from orchestrator.app import auth, main

    seen = []

    async def hook(user_id):
        seen.append(user_id)

    monkeypatch.setattr(auth, "AUTH_MODE", "dev")
    monkeypatch.setattr(auth, "POST_AUTH_HOOKS", [hook])
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=main.app), base_url="http://t"
    ) as client:
        response = await client.post(
            "/chat/stream",
            headers={} if header is None else {"X-User-Id": header},
            json={"messages": []},
        )
    assert response.status_code == 401
    assert seen == []
