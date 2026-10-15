"""Public app with real SQL, checkpoints and A2A agents; external models/HA are scripted."""

import base64
from dataclasses import dataclass
from uuid import uuid4

import httpx
import pytest
from finance.composition import build_runtime as finance_runtime
from finance.main import create_app as finance_app
from finance.settings import FinanceSettings
from gateway.auth.settings import AuthSettings
from gateway.settings import GatewaySettings
from home.composition import build_runtime as home_runtime
from home.domain.actions import ToolCall
from home.main import create_app as home_app
from home.settings import HomeSettings
from home.testing import FakeHomeAgent, FakeHomeAssistant
from integration.agents_harness import HostRouter
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from orchestrator.composition import build_app
from orchestrator.settings import OrchestratorSettings
from orchestrator.testing import FakeImageDescriber
from shared.adapters.a2a.skill_client import A2ASkillClient
from shared.testing.fakes import FakeLLM


class Scripted(FakeMessagesListChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


class Models:
    def __init__(self):
        self.model = Scripted(responses=[AIMessage("Answer")])

    def chat_model(self, task):
        return self.model

    def script(self, *messages):
        self.model.responses = list(messages)
        self.model.i = 0


@dataclass
class Environment:
    http: httpx.AsyncClient
    models: Models
    assistant: FakeHomeAssistant
    user: str
    other: str

    @property
    def headers(self):
        return {"X-User-Id": self.user}

    async def open(self, lead=None):
        response = await self.http.post("/tasks", json={"lead_agent": lead}, headers=self.headers)
        assert response.status_code == 201, response.text
        return response.json()["id"]


@pytest.fixture
async def live(clean_db):
    key = base64.b64encode(bytes(range(32))).decode()
    db = {"database": {"dsn": clean_db.rw}, "secrets": {"key": key}}
    assistant = FakeHomeAssistant()
    home = home_runtime(
        HomeSettings.model_validate(db),
        assistant=assistant,
        agent=FakeHomeAgent(proposal=ToolCall("HassTurnOff", {"name": "Lamp"})),
    )
    finance = finance_runtime(FinanceSettings.model_validate(db), llm=FakeLLM())
    models = Models()
    async with HostRouter(
        {"agent-home": home_app(home), "agent-finance": finance_app(finance)}
    ) as transport:
        agent_http = httpx.AsyncClient(transport=transport)
        app = build_app(
            OrchestratorSettings.model_validate(db),
            GatewaySettings.model_validate(db),
            auth=AuthSettings(auth_mode="dev", env="dev"),
            http=agent_http,
            chat_models=models,
            vision=FakeImageDescriber(),
        )
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://chat"
            ) as http,
        ):
            env = Environment(http, models, assistant, str(uuid4()), str(uuid4()))
            # Gateway authentication creates the user's household server-side.
            response = await http.get("/tasks", headers=env.headers)
            assert response.status_code == 200
            await http.get("/tasks", headers={"X-User-Id": env.other})
            client = A2ASkillClient("http://agent-home:8013/", agent_http)
            from uuid import UUID

            await client.call(
                skill_id="home.connect",
                user_id=UUID(env.user),
                params={"base_url": "http://ha", "token": "synthetic-token"},
            )
            yield env
