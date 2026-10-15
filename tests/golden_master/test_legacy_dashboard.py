"""Record (with --update-snapshots) or re-check the legacy dashboard outputs on the golden week.

The Task 12 gateway and real agent runtimes preserve the Task 1 frozen contract.
"""

import json

import httpx
import pytest
import time_machine
from sqlalchemy.ext.asyncio import create_async_engine

from shared.testing import dashboard_golden as g

pytestmark = pytest.mark.integration


@pytest.fixture
async def legacy_app(clean_db):
    from integration.agents_harness import KEY, HostRouter, build_apps
    from fastapi import FastAPI
    from gateway.auth.settings import AuthSettings
    from gateway.composition import build_gateway, mount
    from gateway.settings import GatewaySettings
    from shared.adapters.a2a.skill_client import A2ASkillClient
    from shared.testing.fakes import FixedClock

    admin = create_async_engine(clean_db.admin)
    try:
        async with admin.begin() as conn:
            await g.seed_postgres(conn)
    finally:
        await admin.dispose()
    apps = build_apps(clean_db.rw)
    async with httpx.AsyncClient(transport=HostRouter(apps)) as http:
        await A2ASkillClient("http://agent-calendar:8012/", http).call(
            skill_id="calendar.connect",
            user_id=g.USER_ID,
            params={"code": "c", "code_verifier": "v"},
        )
        gateway = build_gateway(
            GatewaySettings.model_validate(
                {"database": {"dsn": clean_db.rw}, "secrets": {"key": KEY}}
            ),
            auth=AuthSettings(auth_mode="dev"),
            clock=FixedClock(g.FROZEN_NOW),
            http=http,
        )
        app = FastAPI()
        mount(app, gateway)
        try:
            yield app
        finally:
            await gateway.aclose()


async def _outputs(app) -> dict[str, object]:
    headers = {"X-User-Id": str(g.USER_ID)}
    out: dict[str, object] = {}
    with time_machine.travel(g.FROZEN_NOW, tick=False):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://golden") as client:
            response = await client.get("/dashboard/summary", headers=headers)
            assert response.status_code == 200, response.text
            out["dashboard_summary"] = response.json()
            assert out["dashboard_summary"].pop("unavailable") == []
            for agent in g.DETAIL_AGENTS:
                response = await client.get(f"/agents/{agent}/detail", headers=headers)
                assert response.status_code == 200, response.text
                out[f"detail_{agent}"] = response.json()
    return out


async def test_legacy_outputs_match_the_goldens(legacy_app, request) -> None:
    outputs = await _outputs(legacy_app)
    summary = outputs["dashboard_summary"]
    # The week must exercise every part, or the goldens would pin nothing.
    assert [t["agent"] for t in summary["agents"]] == list(g.TILE_ORDER)
    for key in g.FEATURED_OWNERS:
        assert summary[key] is not None, key
    assert all(summary["rings"][k] is not None for k in g.RING_OWNERS), summary["rings"]
    for agent in g.DETAIL_AGENTS:
        detail = outputs[f"detail_{agent}"]
        assert detail["metrics"], agent
    if request.config.getoption("--update-snapshots"):
        g.GOLDEN_DIR.mkdir(exist_ok=True)
        for name, value in outputs.items():
            (g.GOLDEN_DIR / f"{name}.json").write_text(
                json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n", "utf-8"
            )
        return
    for name, value in outputs.items():
        assert value == g.golden(name), name
