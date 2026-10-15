from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from gateway.auth.settings import AuthSettings
from gateway.settings import GatewaySettings
from orchestrator.composition import build_app
from orchestrator.settings import OrchestratorSettings


@pytest.mark.parametrize("fail_schema", [False, True])
async def test_lifespan_closes_resources_even_if_schema_check_fails(fail_schema):
    settings = OrchestratorSettings(
        database={"dsn": "postgresql+asyncpg://test:test@localhost/test"}
    )
    gateway_settings = GatewaySettings(
        database=settings.database, secrets={"key": "YWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWE="}
    )
    gateway = SimpleNamespace(routers=[], authenticate=AsyncMock(), aclose=AsyncMock())
    checkpoints = SimpleNamespace(open=AsyncMock(), verify_schema=AsyncMock(), close=AsyncMock())
    if fail_schema:
        checkpoints.verify_schema.side_effect = RuntimeError("checkpoint_schema_mismatch")
    engine = SimpleNamespace(dispose=AsyncMock())
    http = SimpleNamespace(aclose=AsyncMock())
    app = build_app(
        settings,
        gateway_settings,
        gateway=gateway,
        auth=AuthSettings(),
        engine=engine,
        http=http,
        checkpoints=checkpoints,
        graph=AsyncMock(),
        uow=AsyncMock(),
        households=AsyncMock(),
        consent=AsyncMock(),
        chat_models=AsyncMock(),
        tasks=AsyncMock(),
        post=AsyncMock(),
        resolve=AsyncMock(),
    )
    if fail_schema:
        with pytest.raises(RuntimeError, match="checkpoint_schema_mismatch"):
            async with app.router.lifespan_context(app):
                pytest.fail("Startup must fail")
    else:
        async with app.router.lifespan_context(app):
            pass
    checkpoints.close.assert_awaited_once()
    gateway.aclose.assert_awaited_once()
    engine.dispose.assert_awaited_once()
    http.aclose.assert_awaited_once()
