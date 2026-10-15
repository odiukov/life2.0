"""The ReAct chat, compiled per run on that run's checkpoint connection."""

from __future__ import annotations

import warnings
from collections.abc import AsyncGenerator, AsyncIterator, Callable
from contextlib import aclosing, asynccontextmanager
from typing import Any
from uuid import UUID

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from shared.ports.chat_model import ChatModelFactory
from shared.ports.llm import LLMTask

from orchestrator.adapters.langgraph.checkpoints import CheckpointPool
from orchestrator.application.ports import (
    FinalText,
    GraphEvent,
    InvalidHistory,
    RunContext,
    ToolDone,
)
from orchestrator.prompts import system_prompt

ToolsFactory = Callable[[RunContext, str], list[BaseTool]]


def _text(content: object) -> str:
    if isinstance(content, list):
        return "".join(
            b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"
        )
    return str(content or "")


class LangGraphSession:
    def __init__(
        self, graph: Any, saver: AsyncPostgresSaver, ctx: RunContext, recursion_limit: int
    ) -> None:
        self._graph, self._saver, self._ctx = graph, saver, ctx
        self._config = {"configurable": {"thread_id": ctx.key}, "recursion_limit": recursion_limit}

    async def run(self, text: str) -> AsyncGenerator[GraphEvent, None]:
        try:
            async with aclosing(
                self._graph.astream(
                    {"messages": [HumanMessage(text)]}, self._config, stream_mode="updates"
                )
            ) as updates:
                async for update in updates:
                    for payload in update.values():
                        for message in (
                            (payload or {}).get("messages", []) if isinstance(payload, dict) else []
                        ):
                            if (
                                isinstance(message, ToolMessage)
                                and isinstance(message.artifact, dict)
                                and message.artifact.get("agent")
                            ):
                                a = message.artifact
                                yield ToolDone(
                                    str(a["agent"]),
                                    tuple(a.get("consulted") or ()),
                                    UUID(a["proposal_id"]) if a.get("proposal_id") else None,
                                    bool(a.get("failed")),
                                )
                            elif (
                                isinstance(message, AIMessage)
                                and not message.tool_calls
                                and (content := _text(message.content).strip())
                            ):
                                yield FinalText(content)
        except ValueError as exc:
            if "INVALID_CHAT_HISTORY" in str(exc):
                raise InvalidHistory from None
            raise

    async def append(self, user_text: str, assistant_text: str) -> None:
        await self._graph.aupdate_state(
            self._config,
            {"messages": [HumanMessage(user_text), AIMessage(assistant_text)]},
            as_node="agent",
        )

    async def reset(self) -> None:
        await self._saver.adelete_thread(self._ctx.key)


class LangGraphChat:
    def __init__(
        self,
        chat_models: ChatModelFactory,
        checkpoints: CheckpointPool,
        tools: ToolsFactory,
        *,
        recursion_limit: int,
    ) -> None:
        self._chat_models, self._checkpoints, self._tools, self._limit = (
            chat_models,
            checkpoints,
            tools,
            recursion_limit,
        )

    @asynccontextmanager
    async def session(
        self, ctx: RunContext, last_user_text: str
    ) -> AsyncIterator[LangGraphSession]:
        async with self._checkpoints.session(ctx) as saver:
            with warnings.catch_warnings():
                warnings.simplefilter(
                    "ignore"
                )  # create_react_agent's deprecation notice in langgraph 1.x
                from langgraph.prebuilt import create_react_agent

                graph = create_react_agent(
                    self._chat_models.chat_model(LLMTask.SMART),
                    self._tools(ctx, last_user_text),
                    prompt=system_prompt(now=ctx.now, zone=ctx.zone, lead_agent=ctx.lead_agent),
                    checkpointer=saver,
                )
            yield LangGraphSession(graph, saver, ctx, self._limit)
