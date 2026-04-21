"""Orchestrator HTTP entrypoint."""
from __future__ import annotations

from shared.telemetry import init_telemetry
init_telemetry("orchestrator")

import json
import os
import uuid
from contextlib import asynccontextmanager

from ag_ui_langgraph import LangGraphAgent, add_langgraph_fastapi_endpoint
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel

from .briefing import build_dashboard, run_briefing
from .db import clear_activity, get_health_summary, get_stats, get_tasks_today, get_yesterday_metrics
from .health_agent import create_health_agent
from .registry import check_agent_health, discover_agents, get_registry


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _graph, _pool, _saver
    from .checkpointer import close_checkpointer, open_checkpointer
    await discover_agents()
    _pool, _saver = await open_checkpointer()
    _graph = await create_health_agent(checkpointer=_saver)
    # Late-register the AG-UI endpoint now that _graph exists.
    add_langgraph_fastapi_endpoint(
        app,
        LangGraphAgent(
            name="default",
            description="Personal health assistant with access to sleep, workout, nutrition, body, mood, habits agents plus live Google Calendar tools",
            graph=_graph,
        ),
        path="/agui",
    )
    try:
        yield
    finally:
        from .mcp_tools import close_mcp_sessions
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


class StreamChatRequest(BaseModel):
    threadId: str = ""
    runId: str = ""
    messages: list[dict] = []
    actions: list = []
    extensions: dict = {}
    forward_props: dict = {}


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


@app.post("/chat/stream")
async def chat_stream(req: StreamChatRequest):
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
            _user_for_consent = _os.environ.get("LANGFUSE_DEFAULT_USER_ID", "owner")
            _bodies_ok = await is_consented(_user_for_consent)
        except Exception as _e:
            _logging.getLogger(__name__).warning(
                "consent lookup failed, defaulting to bodies_ok=False: %s", _e
            )
            _bodies_ok = False  # fail-closed for privacy

    user_messages = [m for m in req.messages if m.get("role") == "user"]
    if not user_messages:
        raise HTTPException(status_code=400, detail="No user message found")
    text = user_messages[-1].get("content", "")

    async def _run_graph():
        async for event in _graph.astream(
            {"messages": [HumanMessage(content=text)]},
            config={"configurable": {"thread_id": thread_id}},
        ):
            for _node, update in event.items():
                messages = update.get("messages") if isinstance(update, dict) else None
                if not messages:
                    continue
                last = messages[-1]
                if not isinstance(last, AIMessage) or getattr(last, "tool_calls", None):
                    continue
                content = getattr(last, "content", "")
                if content:
                    yield content

    async def event_stream():
        _bag_ctx = _otel_baggage.set_baggage(
            "telemetry.bodies_ok", "1" if _bodies_ok else "0"
        )
        _bag_token = _otel_context.attach(_bag_ctx)
        try:
            yield _sse({"type": "RunStarted", "threadId": thread_id, "runId": run_id})
            yield _sse({"type": "TextMessageStart", "messageId": message_id, "role": "assistant"})
            tried_reset = False
            while True:
                try:
                    async for content in _run_graph():
                        yield _sse({
                            "type": "TextMessageContent",
                            "messageId": message_id,
                            "delta": content,
                        })
                    break
                except ValueError as e:
                    # LangGraph raises ValueError with "INVALID_CHAT_HISTORY" when the stored
                    # checkpoint has AIMessage tool_calls without matching ToolMessages — e.g.
                    # after an interrupted run. Wipe the thread and retry once.
                    if "INVALID_CHAT_HISTORY" in str(e) and not tried_reset and _saver is not None:
                        tried_reset = True
                        try:
                            await _saver.adelete_thread(thread_id)
                        except Exception as del_err:
                            yield _sse({
                                "type": "TextMessageContent",
                                "messageId": message_id,
                                "delta": f"Error: {del_err}",
                            })
                            break
                        yield _sse({
                            "type": "TextMessageContent",
                            "messageId": message_id,
                            "delta": "♻️ Предыдущий разговор был прерван, начинаю заново.\n\n",
                        })
                        continue
                    yield _sse({
                        "type": "TextMessageContent",
                        "messageId": message_id,
                        "delta": f"Error: {e}",
                    })
                    break
                except Exception as e:
                    yield _sse({
                        "type": "TextMessageContent",
                        "messageId": message_id,
                        "delta": f"Error: {e}",
                    })
                    break

            yield _sse({"type": "TextMessageEnd", "messageId": message_id})
            yield _sse({"type": "RunFinished", "threadId": thread_id, "runId": run_id})
        finally:
            _otel_context.detach(_bag_token)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/stats")
async def stats():
    from shared.telemetry import set_span_user
    set_span_user()
    return await get_stats()


@app.get("/health-summary")
async def health_summary():
    from shared.telemetry import set_span_user
    set_span_user()
    return await get_health_summary()


@app.delete("/activity")
async def delete_activity():
    from shared.telemetry import set_span_user
    set_span_user()
    deleted = await clear_activity()
    return {"deleted": deleted}


@app.get("/agents")
async def agents():
    from shared.telemetry import set_span_user
    set_span_user()
    registry = get_registry()
    result = []
    for name, entry in registry.items():
        online = await check_agent_health(name)
        tasks_today = await get_tasks_today(name)
        card = entry.get("card", {})
        skills_raw = card.get("skills") or []
        skills = [
            {"id": s.get("id", ""), "name": s.get("name", s.get("id", ""))}
            for s in skills_raw
        ]
        result.append({
            "name": name,
            "url": entry["url"],
            "online": online,
            "skills": skills,
            "description": card.get("description", ""),
            "tasks_today": tasks_today,
        })
    return {"agents": result}


@app.post("/briefing")
async def briefing(debug: bool = False):
    from shared.telemetry import set_span_user
    set_span_user()
    return await run_briefing(get_registry(), use_today=debug)


@app.get("/dashboard", response_class=PlainTextResponse)
async def dashboard_endpoint():
    from shared.telemetry import set_span_user
    set_span_user()
    metrics = await get_yesterday_metrics()
    return build_dashboard(metrics, insight=None)


@app.post("/finance/upload")
async def finance_upload(file: UploadFile = File(..., alias="csv")):
    """Parse a Payoneer PDF monthly statement, UPSERT rows, categorize new
    ones, return a summary string.

    Historically this endpoint accepted CSV; Payoneer no longer exports CSV,
    so the field name `csv` is kept only as a form-field alias for
    backwards-compatibility with earlier telegram-bot builds. The actual
    expected payload is a Payoneer monthly statement PDF.

    Errors:
      415 if the upload is not a PDF (by content-type or filename).
      422 if the PDF doesn't look like a Payoneer Account Statement.
    """
    from shared.telemetry import set_span_user
    set_span_user()
    from .payoneer_pdf import parse_payoneer_pdf, PayoneerPdfFormatError
    from .finance_ingest import (
        ingest_rows, categorize_new, build_upload_summary,
    )
    from .finance_queries import income_for_month, spending_by_category
    from decimal import Decimal

    ct = (file.content_type or "").lower()
    name = (file.filename or "").lower()
    if "pdf" not in ct and not name.endswith(".pdf"):
        raise HTTPException(status_code=415, detail="expected application/pdf upload")

    blob = await file.read()
    if len(blob) > 50 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="pdf > 50 MB")

    try:
        rows, parse_skipped = parse_payoneer_pdf(blob)
    except PayoneerPdfFormatError as e:
        raise HTTPException(status_code=422, detail=f"bad payoneer pdf: {e}")

    ingest_result = await ingest_rows(rows)
    await categorize_new(ingest_result["uncategorized_ids"])

    # Build income/spending summary for the months represented in this upload.
    months = sorted({r["ts"].strftime("%Y-%m") for r in rows}) or [""]
    income_total: dict[str, Decimal] = {}
    spending_total: dict[str, Decimal] = {}
    top_categories: list[tuple[str, Decimal, str]] = []
    for m in months:
        inc = await income_for_month(m)
        for cur, amt in inc.items():
            income_total[cur] = income_total.get(cur, Decimal("0")) + amt
        spend = await spending_by_category(m)
        for cat, cur, amt in spend:
            spending_total[cur] = spending_total.get(cur, Decimal("0")) + amt
            # build_upload_summary expects (name, amount, currency)
            top_categories.append((cat, amt, cur))
    top_categories.sort(key=lambda t: t[1], reverse=True)

    summary = build_upload_summary(
        inserted=ingest_result["inserted"],
        skipped=ingest_result["skipped"] + parse_skipped,
        income_by_currency=income_total,
        spending_by_currency=spending_total,
        top_categories=top_categories[:3],
    )
    return {
        "summary": summary,
        "inserted": ingest_result["inserted"],
        "skipped": ingest_result["skipped"] + parse_skipped,
    }


@app.get("/health")
async def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Mobile endpoints
# ---------------------------------------------------------------------------

from datetime import datetime, timezone as _tz  # noqa: E402


def _thread_title(thread_id: str) -> str:
    if thread_id.startswith("tg-"):
        return "Telegram chat"
    return f"Thread {thread_id[:8]}"


async def _fetch_checkpoint_threads(limit: int = 50) -> list[dict]:
    from shared.db import get_pool
    pool = await get_pool()
    rows = await pool.fetch(
        "SELECT thread_id, MAX(created_at) AS updated_at "
        "FROM checkpoints "
        "GROUP BY thread_id "
        "ORDER BY updated_at DESC "
        "LIMIT $1",
        limit,
    )
    return [dict(r) for r in rows]


def _build_today_shape(metrics: dict, alerts: list) -> dict:
    now = datetime.now()
    hour = now.hour
    if hour < 12:
        greeting = "Good morning"
    elif hour < 18:
        greeting = "Good afternoon"
    else:
        greeting = "Good evening"

    # Status pills
    pills: list[dict] = []
    recovery = metrics.get("recovery") or {}
    if recovery.get("bucket") == "recovered":
        pills.append({"tone": "success", "label": "Recovered"})
    elif recovery.get("bucket") == "depleted":
        pills.append({"tone": "warn", "label": "Depleted"})

    med = metrics.get("medication") or {}
    active_meds = med.get("active") or []
    if active_meds:
        med_logs = med.get("logs") or []
        now_utc = datetime.now(_tz.utc)
        last_by_name: dict[str, datetime] = {}
        for r in med_logs:
            n, ts = r.get("name"), r.get("recorded_at")
            if n and ts and (n not in last_by_name or ts > last_by_name[n]):
                last_by_name[n] = ts
        from datetime import timedelta
        any_missed = any(
            last_by_name.get(m.get("name")) is None
            or (now_utc - last_by_name[m["name"]]) >= timedelta(days=2)
            for m in active_meds
        )
        if any_missed:
            pills.append({"tone": "warn", "label": "Missed med"})

    sleep = metrics.get("sleep") or {}
    if sleep:
        secs = sleep.get("duration_seconds", 0)
        hrs = secs / 3600
        if hrs >= 7:
            pills.append({"tone": "success", "label": f"Slept {hrs:.1f}h"})
        else:
            pills.append({"tone": "warn", "label": f"Slept {hrs:.1f}h"})

    # Must-see lines
    from .briefing import _must_see_lines
    must_see = _must_see_lines(metrics)

    # Alerts → response shape
    now_iso = datetime.now(_tz.utc).isoformat().replace("+00:00", "Z")
    alert_items = [
        {
            "id": a.rule_id,
            "title": a.message[:50],
            "body": a.message,
            "category": a.category,
            "severity": a.severity,
            "created_at": now_iso,
        }
        for a in alerts
    ]

    return {
        "greeting": greeting,
        "date": now.date().isoformat(),
        "status_pills": pills[:4],
        "must_see": must_see,
        "alerts": alert_items,
    }


@app.get("/me")
async def get_me() -> dict:
    return {"id": "me", "voice_preset": "calm_coach"}


@app.get("/chat/threads")
async def list_threads() -> list:
    try:
        rows = await _fetch_checkpoint_threads(limit=50)
    except Exception:
        return []
    return [
        {
            "id": r["thread_id"],
            "title": _thread_title(r["thread_id"]),
            "updated_at": (
                r["updated_at"].astimezone(_tz.utc).isoformat().replace("+00:00", "Z")
                if r["updated_at"] is not None else None
            ),
        }
        for r in rows
    ]


@app.get("/today")
async def get_today() -> dict:
    from .briefing_rules import collect_alerts
    metrics = await get_yesterday_metrics()
    alerts = collect_alerts(metrics)
    return _build_today_shape(metrics, alerts)
