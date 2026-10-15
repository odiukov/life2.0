"""Orchestrator HTTP entrypoint."""

from __future__ import annotations

from shared.telemetry import init_telemetry

init_telemetry("orchestrator")

import asyncio
import json
import logging
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import httpx
from uuid import UUID
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel, ValidationError
from pydantic_settings import SettingsError
from typing import Literal

from . import vault
from .auth import current_user
from gateway.auth.settings import AuthSettings
from .health_agent import create_health_agent
from .registry import discover_agents


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        vault.ensure_ready()
        auth_settings = AuthSettings()
        if auth_settings.auth_mode != "dev" and auth_settings.secret() is None:
            raise RuntimeError("auth_not_configured")
    except (ValidationError, SettingsError):
        # ASGI logs startup exceptions; suppress validation inputs and their chain.
        raise RuntimeError("orchestrator_configuration_invalid") from None
    global _graph, _pool, _saver
    from .checkpointer import close_checkpointer, open_checkpointer

    await discover_agents()
    _pool, _saver = await open_checkpointer()
    _graph = await create_health_agent(checkpointer=_saver)
    try:
        yield
    finally:
        from .mcp_tools import close_mcp_sessions

        if _gateway is not None:
            await _gateway.aclose()
        await close_mcp_sessions()
        if _pool is not None:
            await close_checkpointer(_pool)


# Populated by lifespan; must exist at module level so endpoint functions can close over them.
_graph = None
_pool = None
_saver = None

app = FastAPI(title="Orchestrator", lifespan=lifespan)
from shared.telemetry import instrument_fastapi_app

instrument_fastapi_app(app)
_cors_origins = (
    ["*"]
    if os.getenv("ENV", "dev") == "dev"
    else ["http://localhost:3000"]  # P0 tightens this to the public app host
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["content-type"],
)
from .agent_passthrough import router as agent_passthrough_router

app.include_router(agent_passthrough_router)

from gateway.composition import GatewayNotConfigured
from gateway.composition import mount as mount_gateway

from .auth import gateway

try:
    _gateway = gateway()
except GatewayNotConfigured:
    _gateway = None
    logging.getLogger(__name__).warning("gateway_disabled_without_database_settings")
if _gateway is not None:
    mount_gateway(app, _gateway)


class StreamChatRequest(BaseModel):
    threadId: str = ""
    runId: str = ""
    userTimezone: str | None = None
    messages: list[dict] = []
    actions: list = []
    extensions: dict = {}
    forward_props: dict = {}


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


_AGENT_FROM_TOOL = {
    "ask_sleep_agent": "sleep",
    "ask_workout_agent": "workout",
    "ask_nutrition_agent": "nutrition",
    "ask_body_agent": "body",
    "ask_mood_agent": "mood",
    "ask_habits_agent": "habits",
    "ask_recovery_agent": "recovery",
    "ask_medication_agent": "medication",
}


_routing_logger = logging.getLogger("orchestrator.routing")


async def _run_graph_with_routing(
    text: str,
    user_id: str,
    thread_id: str,
    user_timezone: str | None = None,
):
    """Yields (primary, consulted, content) tuples — primary defaults to 'main' when no peer was called.

    `observed` is hoisted across the full astream traversal: when peers run in
    parallel, each tool node emits an update carrying ONLY its own done-call
    (because `_run_peer_tool` snapshots toolCalls before running). Resetting
    the accumulator per-event would lose every peer except the last one,
    leaving `consulted=[]` and a single agent label on a multi-domain reply.

    `consulted` aggregates two sources: orchestrator-level peers it called
    directly (`observed[:-1]`), AND inner consultations each peer reported
    via the `consulted_peers` artifact (sleep/workout/nutrition fan out to
    other peers internally — those are invisible to the ReAct loop but still
    deserve a "via X" chip in the UI).
    """
    primary: str = "main"
    observed: list[str] = []
    inner_consulted: list[str] = []
    consulted: list[str] = []
    async for event in _graph.astream(
        {
            "messages": [HumanMessage(content=text)],
            "userId": user_id,
            "userTimezone": user_timezone,
        },
        config={"configurable": {"thread_id": thread_id}},
    ):
        for _node, update in event.items():
            if not isinstance(update, dict):
                continue
            if update.get("activeAgent"):
                primary = update["activeAgent"]
            for tc in update.get("toolCalls") or []:
                if tc.get("status") not in ("done", "error"):
                    continue
                agent = _AGENT_FROM_TOOL.get(tc.get("name", ""))
                if agent and agent not in observed:
                    observed.append(agent)
                    _routing_logger.info(
                        "routing thread=%s observed peer=%s order=%s",
                        thread_id,
                        agent,
                        observed,
                    )
                for inner in tc.get("consultedPeers") or []:
                    if inner and inner not in inner_consulted:
                        inner_consulted.append(inner)
            if observed:
                primary = observed[-1]
                # Direct peers (other than primary) + inner-consulted peers,
                # excluding primary and dedup'd while preserving order.
                merged: list[str] = []
                for src in (observed[:-1], inner_consulted):
                    for name in src:
                        if name != primary and name not in merged:
                            merged.append(name)
                consulted = merged
            messages = update.get("messages")
            if not messages:
                continue
            last = messages[-1]
            if not isinstance(last, AIMessage) or getattr(last, "tool_calls", None):
                continue
            content = getattr(last, "content", "")
            if content:
                _routing_logger.info(
                    "routing thread=%s yield primary=%s consulted=%s",
                    thread_id,
                    primary,
                    consulted,
                )
                yield (primary, consulted, content)


@app.post("/chat/stream")
async def chat_stream(req: StreamChatRequest, user_id: UUID = Depends(current_user)):
    thread_id = req.threadId or str(uuid.uuid4())
    run_id = req.runId or str(uuid.uuid4())
    message_id = str(uuid.uuid4())

    from shared.telemetry import set_span_user, set_span_session
    from opentelemetry import baggage as _otel_baggage, context as _otel_context
    import os as _os
    import logging as _logging

    set_span_session(thread_id)
    set_span_user()

    # Consent resolution: only needed in `consented` mode, and must NEVER
    # break the chat handler (telemetry-never-breaks-the-app invariant).
    # In non-consented modes the baggage is written but nothing downstream
    # reads it (ConsentSpanExporter isn't installed), so skip the DB hit.
    _bodies_ok = True
    if _os.environ.get("TELEMETRY_CAPTURE_BODIES", "full").lower() == "consented":
        try:
            from .consent_resolver import is_consented

            _bodies_ok = await is_consented(user_id)
        except Exception as _e:
            _logging.getLogger(__name__).warning(
                "consent_lookup_failed error_type=%s", type(_e).__name__
            )
            _bodies_ok = False  # fail-closed for privacy

    user_messages = [m for m in req.messages if m.get("role") == "user"]
    if not user_messages:
        raise HTTPException(status_code=400, detail="No user message found")
    text = user_messages[-1].get("content", "")

    async def event_stream():
        _bag_ctx = _otel_baggage.set_baggage("telemetry.bodies_ok", "1" if _bodies_ok else "0")
        _bag_token = _otel_context.attach(_bag_ctx)
        try:
            yield _sse({"type": "RunStarted", "threadId": thread_id, "runId": run_id})
            yield _sse({"type": "TextMessageStart", "messageId": message_id, "role": "assistant"})
            primary_emitted = False
            consulted_emitted = False
            tried_reset = False
            while True:
                try:
                    async for primary, consulted, content in _run_graph_with_routing(
                        text,
                        str(user_id),
                        thread_id,
                        req.userTimezone,
                    ):
                        if not primary_emitted:
                            yield _sse({"type": "AgentRouted", "primary": primary})
                            primary_emitted = True
                        yield _sse(
                            {
                                "type": "TextMessageContent",
                                "messageId": message_id,
                                "delta": content,
                            }
                        )
                        if consulted and not consulted_emitted:
                            yield _sse({"type": "AgentConsulted", "peers": consulted})
                            consulted_emitted = True
                    break
                except ValueError as e:
                    # LangGraph raises ValueError with "INVALID_CHAT_HISTORY" when the stored
                    # checkpoint has AIMessage tool_calls without matching ToolMessages — e.g.
                    # after an interrupted run. Wipe the thread and retry once.
                    if "INVALID_CHAT_HISTORY" in str(e) and not tried_reset and _saver is not None:
                        tried_reset = True
                        try:
                            await _saver.adelete_thread(thread_id)
                        except Exception as del_err:  # noqa: BLE001
                            yield _sse(
                                {
                                    "type": "TextMessageContent",
                                    "messageId": message_id,
                                    "delta": f"Error: {del_err}",
                                }
                            )
                            break
                        yield _sse(
                            {
                                "type": "TextMessageContent",
                                "messageId": message_id,
                                "delta": "♻️ Предыдущий разговор был прерван, начинаю заново.\n\n",
                            }
                        )
                        continue
                    yield _sse(
                        {
                            "type": "TextMessageContent",
                            "messageId": message_id,
                            "delta": f"Error: {e}",
                        }
                    )
                    break
                except Exception as e:  # noqa: BLE001
                    yield _sse(
                        {
                            "type": "TextMessageContent",
                            "messageId": message_id,
                            "delta": f"Error: {e}",
                        }
                    )
                    break

            if not primary_emitted:
                yield _sse({"type": "AgentRouted", "primary": "main"})
            yield _sse({"type": "TextMessageEnd", "messageId": message_id})
            yield _sse({"type": "RunFinished", "threadId": thread_id, "runId": run_id})
        finally:
            _otel_context.detach(_bag_token)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/chat/file")
async def chat_file(
    file: UploadFile = File(...),
    thread_id: str = Form(...),
    agent_hint: str | None = Form(None),
    user_id: UUID = Depends(current_user),
):
    """Accept a PDF file, auto-detect ViHealth or Payoneer, parse and import.
    Returns an SSE stream (same format as /chat/stream) with an import summary.

    Errors:
      415 if not a PDF.
      413 if > 50 MB.
    """
    from shared.telemetry import set_span_user

    set_span_user()
    from .file_router import route_file

    ct = (file.content_type or "").lower()
    name = (file.filename or "").lower()
    if "pdf" not in ct and not name.endswith(".pdf"):
        raise HTTPException(status_code=415, detail="expected application/pdf")

    blob = await file.read()
    if len(blob) > 50 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="pdf > 50 MB")

    run_id = str(uuid.uuid4())
    message_id = str(uuid.uuid4())

    async def event_stream():
        yield _sse({"type": "RunStarted", "threadId": thread_id, "runId": run_id})
        yield _sse({"type": "TextMessageStart", "messageId": message_id, "role": "assistant"})
        try:
            summary = await route_file(blob, user_id, agent_hint, file.filename)
        except Exception as e:
            summary = f"Ошибка при обработке файла: {e}"
        yield _sse({"type": "TextMessageContent", "messageId": message_id, "delta": summary})
        yield _sse({"type": "TextMessageEnd", "messageId": message_id})
        yield _sse({"type": "RunFinished", "threadId": thread_id, "runId": run_id})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/health")
async def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Mobile endpoints
# ---------------------------------------------------------------------------

from datetime import timezone as _tz  # noqa: E402
