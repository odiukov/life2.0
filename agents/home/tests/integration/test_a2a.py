import base64
from uuid import uuid4

import httpx
import pytest
from home.composition import build_runtime
from home.domain.actions import ToolCall
from home.main import create_app
from home.settings import HomeSettings
from home.testing import FakeHomeAgent, FakeHomeAssistant
from household.adapters.db import household_uow
from household.application.service import HouseholdService
from shared.a2a.proposals import from_data
from shared.adapters.a2a.skill_client import A2ASkillClient
from shared.adapters.clock import SystemClock
from shared.ports.skills import SkillCallError
from shared.testing.pytest_plugin import PostgresUrls
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.integration


async def test_household_confirmation_and_encryption(clean_db: PostgresUrls) -> None:
    a, b = uuid4(), uuid4()
    admin = create_async_engine(clean_db.admin)
    async with admin.begin() as conn:
        await conn.execute(
            text("INSERT INTO users (id, name) VALUES (:a, 'Ana'), (:b, 'Bo')"), {"a": a, "b": b}
        )
    assistant = FakeHomeAssistant()
    runtime = build_runtime(
        HomeSettings.model_validate(
            {
                "database": {"dsn": clean_db.rw},
                "secrets": {"key": base64.b64encode(bytes(range(32))).decode()},
            }
        ),
        assistant=assistant,
        agent=FakeHomeAgent(proposal=ToolCall("HassTurnOn", {"name": "Heater"})),
    )
    households = HouseholdService(household_uow(runtime.engine), SystemClock())
    await households.ensure(a)
    await households.ensure(b)
    invite = await households.create_invite(a)
    await households.join(b, invite.code.value)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=create_app(runtime)), base_url="http://home"
        ) as http:
            client = A2ASkillClient("http://home/", http)
            connected = await client.call(
                skill_id="home.connect",
                user_id=a,
                params={"base_url": "http://ha", "token": "secret-token"},
            )
            assert connected.data["version"] >= 1
            status = await client.call(skill_id="home.status", user_id=b, params={})
            assert status.data["connected_by"] == "Ana"
            reply = await client.call(
                skill_id="home.ask", user_id=b, params={}, text="turn on the heater"
            )
            proposal = from_data(reply.data)
            assert proposal is not None
            await households.leave(b)
            with pytest.raises(SkillCallError) as error:
                await client.call(
                    skill_id="home.apply_action",
                    user_id=b,
                    params={"payload": dict(proposal.payload)},
                )
            assert error.value.code == "household_changed"
            assert assistant.calls == []
            for _ in range(2):
                applied = await client.call(
                    skill_id="home.apply_action",
                    user_id=a,
                    params={"payload": dict(proposal.payload)},
                )
                assert applied.data == {"status": "applied"}
            assert assistant.calls == [("HassTurnOn", {"name": "Heater"})] * 2
        async with admin.begin() as conn:
            sealed = (
                await conn.execute(text("SELECT payload_enc FROM household_credentials"))
            ).scalar_one()
            assert b"secret-token" not in bytes(sealed)
    finally:
        await runtime.pool.aclose()
        await runtime.http.aclose()
        await runtime.engine.dispose()
        await admin.dispose()
