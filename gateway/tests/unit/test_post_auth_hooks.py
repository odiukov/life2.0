"""Authentication bootstraps households before serving protected gateway routes."""

from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from gateway.auth.authenticate import Authenticator
from gateway.auth.settings import AuthSettings
from gateway.auth.store import AuthStore, InMemoryAuthStore
from gateway.auth.tokens import issue_access
from gateway.hooks import HouseholdEnsurer
from gateway.kitchen import KitchenGateway
from gateway.kitchen import build_router as kitchen_router
from household.adapters.http import build_router
from household.application.service import HouseholdService
from household.testing import InMemoryHouseholds, in_memory_uow
from shared.ports.skills import SkillReply
from shared.testing.fakes import FakeSkillClient, FixedClock, InMemoryUnitOfWorkFactory


@pytest.mark.parametrize("path", ["/household", "/kitchen/inventory"])
@pytest.mark.parametrize("mode", ["dev", "oauth"])
async def test_post_auth_hook_runs_before_gateway_routes(path, mode):
    clock = FixedClock(datetime.now(UTC))
    repo = InMemoryHouseholds(clock)
    service = HouseholdService(in_memory_uow(repo), clock)
    auth = Authenticator(
        AuthSettings(auth_mode=mode, auth_jwt_secret="x" * 32, session_check=False),
        InMemoryUnitOfWorkFactory({AuthStore: InMemoryAuthStore()}),
    )
    auth.add_hook(HouseholdEnsurer(service))
    user = uuid4()
    events = []

    async def after_bootstrap(uid):
        assert (await service.get(uid)).role_of(uid) is not None
        events.append("ready")

    auth.add_hook(after_bootstrap)
    app = FastAPI()
    app.include_router(build_router(service, auth))
    app.include_router(
        kitchen_router(
            KitchenGateway(FakeSkillClient(lambda *args: SkillReply("", {"items": []}))), auth
        )
    )
    headers = (
        {"X-User-Id": str(user)}
        if mode == "dev"
        else {"Authorization": "Bearer " + issue_access(user, uuid4(), "x" * 32)}
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(path, headers=headers)
    assert response.status_code == 200
    assert events == ["ready"]
    assert len(repo.households) == 1


async def test_failing_hook_does_not_block_later_hooks(caplog):
    auth = Authenticator(
        AuthSettings(auth_mode="dev"), InMemoryUnitOfWorkFactory({AuthStore: InMemoryAuthStore()})
    )
    seen = []

    async def boom(uid):
        raise RuntimeError("private failure text")

    async def later(uid):
        seen.append(uid)

    auth.add_hook(boom)
    auth.add_hook(later)
    user = uuid4()
    assert await auth(None, str(user)) == user
    assert seen == [user]
    assert "private failure text" not in caplog.text


@pytest.mark.parametrize("header", [None, "invalid"])
async def test_failed_authentication_does_not_run_hooks(header):
    from fastapi import HTTPException

    auth = Authenticator(
        AuthSettings(auth_mode="dev"), InMemoryUnitOfWorkFactory({AuthStore: InMemoryAuthStore()})
    )
    seen = []

    async def hook(uid):
        seen.append(uid)

    auth.add_hook(hook)
    with pytest.raises(HTTPException):
        await auth(None, header)
    assert seen == []
