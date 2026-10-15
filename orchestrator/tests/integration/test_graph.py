from datetime import UTC, datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from orchestrator.adapters.langgraph.checkpoints import CheckpointPool
from orchestrator.adapters.langgraph.graph import LangGraphChat
from orchestrator.adapters.langgraph.tools import build_tools
from orchestrator.application.ports import FinalText, PeerReply, RunContext, ToolDone
from orchestrator.testing import FakeHealthSync, FakePeerAgents, RecordedProposals
from shared.ports.skills import SkillReply
from shared.testing.fakes import FakeSkillClient
from shared.testing.pytest_plugin import PostgresUrls
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.integration


class Scripted(FakeMessagesListChatModel):
    def bind_tools(self, tools, **kwargs):  # type: ignore[no-untyped-def]
        return self


class Models:
    def __init__(self, model):  # type: ignore[no-untyped-def]
        self.model = model

    def chat_model(self, task):  # type: ignore[no-untyped-def]
        return self.model


def chat(pool: CheckpointPool, responses: list[AIMessage], peers: FakePeerAgents) -> LangGraphChat:
    def tools(ctx, last_user_text):  # type: ignore[no-untyped-def]
        return build_tools(
            ctx,
            last_user_text=last_user_text,
            peers=peers,
            skills=lambda a: FakeSkillClient(lambda *x: SkillReply("", {})),
            proposals=RecordedProposals(),
            sync=FakeHealthSync(),
        )

    return LangGraphChat(Models(Scripted(responses=responses)), pool, tools, recursion_limit=25)


async def test_run_emits_tool_and_final_events_and_persists_under_the_users_key(
    clean_db: PostgresUrls,
) -> None:
    pool = CheckpointPool(clean_db.rw, max_size=2)
    await pool.open()
    user, task = uuid4(), uuid4()
    admin = create_async_engine(clean_db.admin)
    async with admin.begin() as conn:
        await conn.execute(text("INSERT INTO users (id, name) VALUES (:u, 'u')"), {"u": user})
    ctx = RunContext(user, task, None, None, ZoneInfo("Europe/Kyiv"), "ru", datetime.now(UTC))
    peers = FakePeerAgents({"sleep": PeerReply("sleep summary", consulted=("nutrition",))})
    graph = chat(
        pool,
        [
            AIMessage(
                "",
                tool_calls=[
                    {
                        "name": "ask_sleep_agent",
                        "args": {"message": "как спал?", "skill": "analyze_sleep"},
                        "id": "1",
                    }
                ],
            ),
            AIMessage("Спал 7 часов."),
        ],
        peers,
    )
    try:
        async with graph.session(ctx, "как спал?") as session:
            events = [e async for e in session.run("как спал?")]
        assert events == [ToolDone("sleep", ("nutrition",)), FinalText("Спал 7 часов.")]
        async with admin.begin() as conn:
            keys = {
                r[0] for r in await conn.execute(text("SELECT DISTINCT thread_id FROM checkpoints"))
            }
        assert keys == {f"{user}:{task}"}
        async with graph.session(ctx, "x") as session:
            await session.append("да", "Готово: свет выключен.")
            snapshot = await session._saver.aget({"configurable": {"thread_id": ctx.key}})
            assert snapshot is not None
            assert [m.content for m in snapshot["channel_values"]["messages"]][-2:] == [
                "да",
                "Готово: свет выключен.",
            ]
            await session.reset()
        async with admin.begin() as conn:
            assert (await conn.execute(text("SELECT count(*) FROM checkpoints"))).scalar_one() == 0
    finally:
        await pool.close()
        await admin.dispose()
