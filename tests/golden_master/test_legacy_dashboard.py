"""Record (with --update-snapshots) or re-check the legacy dashboard outputs on the golden week.

Runs the OLD orchestrator. Deleted together with it in sub-project 3c Task 17.
"""

import json

import httpx
import pytest
import time_machine
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from shared.testing import dashboard_golden as g

pytestmark = pytest.mark.integration

SHADOW_NOW = (
    "CREATE OR REPLACE FUNCTION public.now() RETURNS timestamptz LANGUAGE sql STABLE "
    f"AS $$ SELECT TIMESTAMPTZ '{g.FROZEN_NOW.isoformat()}' $$"
)


async def _reset_legacy_pools() -> None:
    import shared.db as shared_db
    from orchestrator.app import db as orchestrator_db

    for module in (orchestrator_db, shared_db):
        if module._pool is not None:
            await module._pool.close()
            module._pool = None


async def _list_events(
    user_id, *, time_min, time_max, max_results=20, calendar_id="primary", timeout=10.0
):
    from datetime import datetime

    return g.google_events_for(datetime.fromisoformat(time_min).date())


@pytest.fixture
async def legacy_app(clean_db, monkeypatch):
    admin = create_async_engine(clean_db.admin)
    async with admin.begin() as conn:
        await conn.execute(text(SHADOW_NOW))
        await g.seed_postgres(conn)
    monkeypatch.setenv("POSTGRES_DSN", clean_db.legacy_plain + "?search_path=public%2Cpg_catalog")
    monkeypatch.setattr("orchestrator.app.auth.AUTH_MODE", "dev")
    monkeypatch.setattr("orchestrator.app.google_calendar_api.list_events", _list_events)
    await _reset_legacy_pools()
    from orchestrator.app.main import app

    try:
        yield app
    finally:
        await _reset_legacy_pools()
        async with admin.begin() as conn:
            await conn.execute(text("DROP FUNCTION IF EXISTS public.now()"))
        await admin.dispose()


async def _outputs(app) -> dict[str, object]:
    headers = {"X-User-Id": str(g.USER_ID)}
    out: dict[str, object] = {}
    with time_machine.travel(g.FROZEN_NOW, tick=False):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://golden") as client:
            response = await client.get("/dashboard/summary", headers=headers)
            assert response.status_code == 200, response.text
            out["dashboard_summary"] = response.json()
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
