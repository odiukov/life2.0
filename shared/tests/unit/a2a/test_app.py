from datetime import UTC, datetime

import httpx
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from shared.a2a.app import create_agent_app
from shared.a2a.executor import SkillExecutor, SkillResult
from shared.testing.fakes import FakeLLM, FakeTaskRecords, FixedClock


class FakeEngine:
    disposed = False

    async def dispose(self) -> None:
        self.disposed = True


async def test_health_card_and_dispose() -> None:
    async def ok(request, consult):  # type: ignore[no-untyped-def]
        return SkillResult(output="ok")

    card = AgentCard(
        protocol_version="0.3.0",
        name="x-agent",
        description="d",
        url="http://x/",
        version="1",
        capabilities=AgentCapabilities(streaming=True),
        default_input_modes=["text"],
        default_output_modes=["text"],
        skills=[AgentSkill(id="s", name="s", description="s", tags=[])],
    )
    engine = FakeEngine()
    app = create_agent_app(
        title="X",
        card=card,
        task_store=InMemoryTaskStore(),
        engine=engine,  # type: ignore[arg-type]
        executor=SkillExecutor(
            agent="x",
            handlers={"s": ok},
            peers=[],
            llm=FakeLLM(),
            task_records=FakeTaskRecords(),
            clock=FixedClock(datetime(2026, 10, 13, tzinfo=UTC)),
        ),
    )
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://x") as http,
    ):
        assert (await http.get("/health")).json() == {"status": "ok"}
        assert (await http.get("/.well-known/agent-card.json")).json()["name"] == "x-agent"
    assert engine.disposed
