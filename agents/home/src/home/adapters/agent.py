"""home.ask: a small ReAct loop over the household's tools. Changes are captured, never run."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import BaseTool, StructuredTool
from langgraph.prebuilt import create_react_agent
from shared.ports.chat_model import ChatModelFactory
from shared.ports.household_credentials import HouseholdConnection
from shared.ports.llm import LLMTask

from home.adapters.mcp_pool import McpPool
from home.application.ports import AgentOutcome, HomeUnavailable
from home.domain.actions import ToolCall, is_read_only

PENDING = "Not executed: this change is waiting for the user's confirmation in the app."
SYSTEM = (
    "You are the home assistant of one household and control its Home Assistant through tools. "
    "Before answering a question about the home, read the current state with GetLiveContext. "
    "When the user asks to change something, call the one matching tool once. The app then asks "
    "the user to confirm, so never say the change is done; say what will happen after they "
    "confirm. Only entities exposed in Home Assistant are visible; if one is missing, say so. "
    "Answer briefly in plain text, in the user's language ({locale})."
)


def _proposing(tool: BaseTool, sink: list[ToolCall]) -> BaseTool:
    async def capture(**kwargs: Any) -> str:
        if not sink:  # one change per turn: the first call wins, later ones are ignored
            sink.append(ToolCall(tool.name, kwargs))
        return PENDING

    return StructuredTool(
        name=tool.name,
        description=tool.description,
        args_schema=tool.args_schema,
        coroutine=capture,
    )


class LangGraphHomeAgent:
    def __init__(
        self, chat_models: ChatModelFactory, pool: McpPool, *, recursion_limit: int = 12
    ) -> None:
        self._chat_models = chat_models
        self._pool = pool
        self._limit = recursion_limit

    async def run(self, question: str, conn: HouseholdConnection, locale: str) -> AgentOutcome:
        try:
            return await self._run(question, conn, locale)
        except HomeUnavailable:
            raise
        except Exception:
            raise HomeUnavailable from None

    async def _run(self, question: str, conn: HouseholdConnection, locale: str) -> AgentOutcome:
        captured: list[ToolCall] = []
        tools = [
            t if is_read_only(t.name) else _proposing(t, captured)
            for t in await self._pool.tools(conn)
        ]
        graph = create_react_agent(self._chat_models.chat_model(LLMTask.SMART), tools)
        result = await graph.ainvoke(
            {"messages": [SystemMessage(SYSTEM.format(locale=locale)), HumanMessage(question)]},
            {"recursion_limit": self._limit},
        )
        final = next(
            (
                m
                for m in reversed(result["messages"])
                if isinstance(m, AIMessage) and not m.tool_calls
            ),
            None,
        )
        text = final.content if final is not None and isinstance(final.content, str) else ""
        return AgentOutcome(text.strip(), captured[0] if captured else None)
