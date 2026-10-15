import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4
from zoneinfo import ZoneInfo

from langchain_core.messages import AIMessage
from orchestrator.adapters.langgraph.graph import LangGraphSession
from orchestrator.application.ports import FinalText, RunContext


async def test_session_close_awaits_underlying_langgraph_stream_finalizer():
    order = []

    async def astream(*args, **kwargs):
        try:
            yield {"agent": {"messages": [AIMessage("Answer")]}}
        finally:
            await asyncio.sleep(0)
            order.append("langgraph_closed")

    ctx = RunContext(uuid4(), uuid4(), None, None, ZoneInfo("UTC"), "en", datetime.now(UTC))
    session = LangGraphSession(SimpleNamespace(astream=astream), None, ctx, 25)
    stream = session.run("hello")
    assert await anext(stream) == FinalText("Answer")
    await stream.aclose()
    assert order == ["langgraph_closed"]
