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
from pydantic import BaseModel, Field
from typing import Literal

from .auth import current_user
from .db import clear_activity, fetch_body_logs, get_health_summary, get_stats, get_tasks_today, get_yesterday_metrics
from .integrations_routes import router as integrations_router
from .health_agent import create_health_agent
from .registry import check_agent_health, discover_agents, get_registry


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _graph, _pool, _saver
    from .checkpointer import close_checkpointer, open_checkpointer
    await discover_agents()
    _pool, _saver = await open_checkpointer()
    _graph = await create_health_agent(checkpointer=_saver)
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
app.include_router(integrations_router)
from .agent_passthrough import router as agent_passthrough_router
app.include_router(agent_passthrough_router)


# Temporary verbose logger for pydantic validation errors — helps track down
# the shape of failing /sync/health batches. Remove when the HealthKit sample
# shape is fully locked.
_logging = logging
from fastapi.exceptions import RequestValidationError as _RVE
from fastapi.responses import JSONResponse as _JR
_val_logger = _logging.getLogger("orchestrator.validation")


@app.exception_handler(_RVE)
async def _log_validation_error(request, exc: _RVE):
    body = await request.body()
    _val_logger.warning(
        "422 %s %s errors=%r body=%r",
        request.method, request.url.path, exc.errors()[:5], body[:500],
    )
    return _JR(status_code=422, content={"detail": exc.errors()})


# -------- HealthKit sync endpoint (Plan Task 19) --------

class HealthSample(BaseModel):
    """One HealthKit sample as the mobile app pushes it."""
    type: str
    start: datetime
    end: datetime | None = None
    value: float | None = None
    unit: str | None = None
    stages: list[dict] | None = None
    source: str | None = None
    activityTypeName: str | None = None


class SyncHealthBody(BaseModel):
    samples: list[HealthSample] = Field(..., max_length=500)


_SYNC_SERVICE_BASE = os.environ.get("SYNC_SERVICE_URL", "http://sync-service:8080")


@app.post("/sync/trigger")
async def sync_trigger(user_id: UUID = Depends(current_user)):
    """Fire-and-forget: kick off full sync (Garmin + Yazio + alerts) on the sync-service.

    Returns immediately with {"ok": true}. Failures are logged server-side.
    Authenticated so random clients can't spam the sync service.
    """
    async def _fire():
        async with httpx.AsyncClient(timeout=30.0) as c:
            try:
                await c.post(f"{_SYNC_SERVICE_BASE}/sync/all")
            except Exception as exc:
                _logging.getLogger(__name__).warning("sync/all failed: %s", exc)

    asyncio.create_task(_fire())
    return {"ok": True}


@app.post("/sync/health")
async def sync_health(body: SyncHealthBody, user_id: UUID = Depends(current_user)):
    """Accept a batch of HealthKit samples; idempotent by (user_id, source, type, recorded_at).

    Rejects payloads with more than 500 samples — mobile chunks before POST.
    """
    from shared.db import get_pool
    pool = await get_pool()
    inserted = 0
    async with pool.acquire() as c:
        async with c.transaction():
            for s in body.samples:
                data = s.model_dump(
                    mode="json", exclude={"type", "start", "source"}, exclude_none=True,
                )
                res = await c.execute(
                    """
                    INSERT INTO health_logs (user_id, agent, type, recorded_at, data, source)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    ON CONFLICT (user_id, source, type, recorded_at) DO NOTHING
                    """,
                    user_id, "apple-health", s.type, s.start, data, s.source or "apple-health",
                )
                if res.split()[-1] == "1":
                    inserted += 1
    # Collapse raw HealthKit samples into per-night sleep_session + per-day
    # daily_stats rows so the sleep / recovery agents see their
    # expected schema. Idempotent — safe to run even when nothing inserted.
    from .healthkit_aggregator import aggregate_for_user
    agg = await aggregate_for_user(user_id)
    return {"inserted": inserted, "received": len(body.samples), "aggregated": agg}


class StreamChatRequest(BaseModel):
    threadId: str = ""
    runId: str = ""
    userTimezone: str | None = None
    messages: list[dict] = []
    actions: list = []
    extensions: dict = {}
    forward_props: dict = {}


class BodyProfileUpdate(BaseModel):
    height_cm: float | None = None
    weight_kg: float | None = None
    age: int | None = None
    sex: str | None = None          # "male" | "female"
    activity_level: str | None = None
    calorie_goal_override: int | None = None


class ViHealthProfileImport(BaseModel):
    height_cm: float | None = None
    weight_kg: float | None = None
    age: int | None = None
    sex: Literal["male", "female"] | None = None


def _compute_tdee(weight_kg: float, height_cm: float, age: int, sex: str, activity_level: str) -> int:
    """Mifflin-St Jeor BMR × activity multiplier.

    BMR (men)   = 10×W + 6.25×H − 5×A + 5
    BMR (women) = 10×W + 6.25×H − 5×A − 161
      W = weight kg, H = height cm, A = age years

    TDEE = BMR × multiplier:
      sedentary=1.2, light=1.375, moderate=1.55, active=1.725, very_active=1.9
    """
    bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age + (5 if sex == "male" else -161)
    multipliers = {
        "sedentary": 1.2,
        "light": 1.375,
        "moderate": 1.55,
        "active": 1.725,
        "very_active": 1.9,
    }
    return round(bmr * multipliers.get(activity_level, 1.55))


def _fmt_duration(seconds: int) -> str:
    """Format seconds as 'Xh Ym' (e.g. '7h 23m')."""
    h = seconds // 3600
    m = (seconds % 3600) // 60
    return f"{h}h {m}m"


def _hrv_pct(hrv: int | None, baseline: float | None) -> int | None:
    if hrv is None or not baseline:  # baseline=0.0 would divide-by-zero
        return None
    return min(100, round(hrv / baseline * 100))


def _mood_pct(avg_score: float | None) -> int | None:
    if avg_score is None:
        return None
    return min(100, round(avg_score / 10.0 * 100))


def _steps_pct(steps: float | None) -> int | None:
    if steps is None:
        return None
    return min(100, round(steps / 10_000 * 100))


def _format_age(days: int) -> str:
    if days <= 0:
        return "today"
    if days == 1:
        return "yesterday"
    return f"{days} days ago"


async def _build_featured_body(user_id: UUID) -> dict | None:
    rows = await fetch_body_logs(user_id, limit=12)
    if len(rows) < 2:
        return None
    latest = rows[0]
    latest_data = latest.get("data") or {}
    if latest_data.get("weight_kg") is None:
        return None
    age_days = (datetime.now(timezone.utc) - latest["recorded_at"]).days
    if age_days > 60:
        return None

    target = latest["recorded_at"] - timedelta(days=30)

    prev_row = next(
        (r for r in rows[1:] if (r.get("data") or {}).get("weight_kg") is not None),
        None,
    )
    weight_delta_prev = (
        round(latest_data["weight_kg"] - prev_row["data"]["weight_kg"], 1)
        if prev_row else None
    )

    def delta_for(field: str) -> float | None:
        cur = latest_data.get(field)
        if cur is None:
            return None
        candidates = [
            r for r in rows[1:]
            if (r.get("data") or {}).get(field) is not None
        ]
        if not candidates:
            return None
        anchor = min(
            candidates,
            key=lambda r: abs((r["recorded_at"] - target).total_seconds()),
        )
        if abs((anchor["recorded_at"] - target).total_seconds()) > 10 * 86400:
            return None
        return round(cur - anchor["data"][field], 1)

    spark_rows = [
        r for r in rows
        if (r.get("data") or {}).get("weight_kg") is not None
    ][:8]
    spark_weights = [r["data"]["weight_kg"] for r in reversed(spark_rows)]

    return {
        "weightKg": latest_data["weight_kg"],
        "weightDelta30d": delta_for("weight_kg"),
        "weightDeltaPrev": weight_delta_prev,
        "ageDaysLabel": _format_age(age_days),
        "source": latest.get("source") or "",
        "sparkWeights": spark_weights,
        "fatPct": latest_data.get("body_fat_pct"),
        "fatPctDelta30d": delta_for("body_fat_pct"),
        "muscleKg": latest_data.get("muscle_kg"),
        "muscleKgDelta30d": delta_for("muscle_kg"),
        "leanKg": latest_data.get("lean_mass_kg"),
        "leanKgDelta30d": delta_for("lean_mass_kg"),
    }


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


_routing_logger = _logging.getLogger("orchestrator.routing")


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
                        thread_id, agent, observed,
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
                    thread_id, primary, consulted,
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

    async def event_stream():
        _bag_ctx = _otel_baggage.set_baggage(
            "telemetry.bodies_ok", "1" if _bodies_ok else "0"
        )
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
                        yield _sse({
                            "type": "TextMessageContent",
                            "messageId": message_id,
                            "delta": content,
                        })
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
                except Exception as e:  # noqa: BLE001
                    yield _sse({
                        "type": "TextMessageContent",
                        "messageId": message_id,
                        "delta": f"Error: {e}",
                    })
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


@app.get("/stats")
async def stats(user_id: UUID = Depends(current_user)):
    from shared.telemetry import set_span_user
    set_span_user()
    return await get_stats(user_id)


@app.get("/health-summary")
async def health_summary(user_id: UUID = Depends(current_user)):
    from shared.telemetry import set_span_user
    set_span_user()
    return await get_health_summary(user_id)


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


@app.get("/agents/{agent_id}/detail")
async def agent_detail_endpoint(
    agent_id: str,
    user_id: UUID = Depends(current_user),
) -> dict:
    from .agent_detail import get_agent_detail, VALID_AGENT_IDS
    from shared.telemetry import set_span_user
    set_span_user()
    if agent_id not in VALID_AGENT_IDS:
        raise HTTPException(status_code=404, detail=f"Unknown agent: {agent_id}")
    return await get_agent_detail(agent_id, user_id)


@app.get("/dashboard/summary")
async def dashboard_summary(user_id: UUID = Depends(current_user)) -> dict:
    from shared.telemetry import set_span_user
    from .db import get_body_profile, fetch_body_logs
    set_span_user()
    metrics = await get_yesterday_metrics(user_id)
    # For nutrition and workout, prefer today's data if available.
    today_metrics = await get_yesterday_metrics(user_id, use_today=True)
    nutrition_is_today = False
    if today_metrics.get("nutrition") and today_metrics["nutrition"].get("kcal"):
        metrics["nutrition"] = today_metrics["nutrition"]
        nutrition_is_today = True
    workout_is_today = False
    if today_metrics.get("workout") and today_metrics["workout"].get("activity_count"):
        metrics["workout"] = today_metrics["workout"]
        workout_is_today = True

    # Fetch body profile once; used for nutrition card, agent card, and alerts.
    profile = await get_body_profile(user_id)

    # Inject protein goal so nutrition_protein_low_rule can fire.
    if metrics.get("nutrition"):
        weight_kg = profile.get("weight_kg") or 75.0
        metrics["nutrition"]["protein_goal_g"] = round(weight_kg * 1.8)

    agents = []

    # ── Sleep ──────────────────────────────────────────────────────────────
    sleep = metrics.get("sleep")
    if sleep and sleep.get("duration_seconds") is not None:
        secs = sleep["duration_seconds"]
        hrs = secs / 3600
        pills = []
        if sleep.get("deep_sleep_seconds") is not None:
            pills.append(f"Deep {_fmt_duration(sleep['deep_sleep_seconds'])}")
        if sleep.get("hrv") is not None:
            pills.append(f"HRV {sleep['hrv']}")
        if sleep.get("score") is not None:
            pills.append(f"Score {sleep['score']}")
        agents.append({
            "agent": "sleep",
            "label": "Sleep",
            "metric": _fmt_duration(secs),
            "tint": "success" if hrs >= 7 else "warn",
            "detail": " · ".join(pills) if pills else None,
            "progress": min(hrs / 8.0, 1.0),
        })

    # ── Recovery ───────────────────────────────────────────────────────────
    recovery = metrics.get("recovery")
    if recovery and recovery.get("bucket"):
        bucket = recovery["bucket"]
        tint_map = {"recovered": "success", "neutral": "warn", "depleted": "danger"}
        progress_map = {"recovered": 0.85, "neutral": 0.55, "depleted": 0.20}
        top3 = recovery.get("top3") or []
        pills = [
            f"{s['label']} {s['dir']}{s['delta']}" if s.get("delta") else f"{s['label']} {s['dir']}"
            for s in top3[:3]
            if s.get("label") and s.get("dir")
        ]
        agents.append({
            "agent": "recovery",
            "label": "Recovery",
            "metric": bucket.capitalize(),
            "tint": tint_map.get(bucket, "neutral"),
            "detail": " · ".join(pills) if pills else None,
            "progress": progress_map.get(bucket),
        })

    # ── Workout ────────────────────────────────────────────────────────────
    workout = metrics.get("workout")
    if workout:
        dist_km = (workout.get("total_distance_meters") or 0) / 1000
        name = workout.get("first_name") or workout.get("first_type") or "Workout"
        metric_str = f"{name} · {dist_km:.1f}km" if dist_km > 0.1 else name
        pills = []
        if workout.get("total_calories"):
            pills.append(f"{workout['total_calories']} kcal")
        agents.append({
            "agent": "workout",
            "label": "Workout",
            "metric": metric_str,
            "tint": "neutral",
            "detail": " · ".join(pills) if pills else None,
            "progress": None,
            "workout_type": workout.get("first_type") or "",
        })

    # ── Nutrition ──────────────────────────────────────────────────────────
    nutrition = metrics.get("nutrition")
    if nutrition and nutrition.get("kcal") is not None:
        kcal = int(nutrition["kcal"])
        pills = []
        if nutrition.get("protein_g") is not None:
            pills.append(f"P {int(nutrition['protein_g'])}g")
        if nutrition.get("carbs_g") is not None:
            pills.append(f"C {int(nutrition['carbs_g'])}g")
        if nutrition.get("fat_g") is not None:
            pills.append(f"F {int(nutrition['fat_g'])}g")
        progress = None
        goal = None
        try:
            weight_kg = profile.get("weight_kg")
            if weight_kg is None:
                rows = await fetch_body_logs(user_id, limit=1)
                if rows:
                    weight_kg = rows[0].get("data", {}).get("weight_kg")
            override = profile.get("calorie_goal_override")
            if override:
                goal = int(override)
            elif all([weight_kg, profile.get("height_cm"), profile.get("age"), profile.get("sex"), profile.get("activity_level")]):
                goal = _compute_tdee(weight_kg, profile["height_cm"], profile["age"], profile["sex"], profile["activity_level"])
            if goal:
                progress = min(kcal / goal, 1.0)
        except Exception:
            pass
        if goal:
            pills.append(f"Goal {goal} kcal")
        agents.append({
            "agent": "nutrition",
            "label": "Nutrition",
            "metric": f"{kcal} kcal",
            "tint": "neutral",
            "detail": " · ".join(pills) if pills else None,
            "progress": progress,
        })

    # ── Mood ───────────────────────────────────────────────────────────────
    mood = metrics.get("mood")
    if mood:
        avg = mood.get("avg_score")
        if avg is not None:
            pills = []
            if mood.get("avg_stress") is not None:
                pills.append(f"Stress {mood['avg_stress']:.1f}")
            if mood.get("avg_energy") is not None:
                pills.append(f"Energy {mood['avg_energy']:.1f}")
            if mood.get("count"):
                pills.append(f"{mood['count']} entries")
            agents.append({
                "agent": "mood",
                "label": "Mood",
                "metric": f"{avg:.1f}/10",
                "tint": "success" if avg >= 7 else "warn",
                "detail": " · ".join(pills) if pills else None,
                "progress": avg / 10.0,
            })

    # ── Habits ─────────────────────────────────────────────────────────────
    habits = metrics.get("habits")
    if habits:
        completed = habits.get("completed_yesterday")
        expected = habits.get("expected_yesterday")
        if completed is not None and expected is not None and expected > 0:
            pills = []
            missed = habits.get("missed_names") or []
            if missed:
                pills.append(f"Missed: {missed[0]}")
            streaks = habits.get("top_streaks") or []
            if streaks:
                s = streaks[0]
                pills.append(f"Streak: {s['name']} {s['streak']}d")
            agents.append({
                "agent": "habits",
                "label": "Habits",
                "metric": f"{completed}/{expected}",
                "tint": "success" if completed >= expected else "warn",
                "detail": " · ".join(pills) if pills else None,
                "progress": completed / expected,
            })

    # ── Medication ─────────────────────────────────────────────────────────
    medication = metrics.get("medication")
    if medication and medication.get("active"):
        from datetime import timedelta, datetime as _dt, timezone as _tz
        now_utc = _dt.now(_tz.utc)
        last_by_name: dict = {}
        for r in medication.get("logs") or []:
            n, ts = r.get("name"), r.get("recorded_at")
            if n and ts and (n not in last_by_name or ts > last_by_name[n]):
                last_by_name[n] = ts
        active_names = [m.get("name") for m in medication["active"] if m.get("name")]
        overdue = [
            n for n in active_names
            if last_by_name.get(n) is None
            or (now_utc - last_by_name[n]) >= timedelta(days=2)
        ]
        missed = len(overdue)
        pills = [f"−{(now_utc - last_by_name[n]).days}d {n}" for n in overdue[:2] if n in last_by_name]
        taken = len(active_names) - missed
        agents.append({
            "agent": "medication",
            "label": "Medication",
            "metric": " · ".join(active_names[:2]) if active_names else "On track",
            "tint": "danger" if missed > 1 else "warn" if missed == 1 else "success",
            "detail": " · ".join(pills) if pills else None,
            "progress": taken / len(active_names) if active_names else 1.0,
        })

    # ── Calendar ───────────────────────────────────────────────────────────
    calendar = metrics.get("calendar")
    if calendar:
        count = int(calendar.get("events_count") or 0)
        free_start = calendar.get("first_free_slot_start")
        free_len = calendar.get("first_free_slot_len_min")
        all_day = calendar.get("all_day_events") or []
        detail_bits = []
        if free_start and free_len:
            detail_bits.append(f"Free {free_start} · {free_len}m")
        if all_day:
            detail_bits.append(f"All-day: {all_day[0]}")
        agents.append({
            "agent": "calendar",
            "label": "Calendar",
            "metric": f"{count} event{'s' if count != 1 else ''}",
            "tint": "neutral" if count < 5 else "warn",
            "detail": " · ".join(detail_bits) if detail_bits else None,
            "progress": min(count / 8, 1.0),
        })

    # ── Featured sleep ─────────────────────────────────────────────────────
    sleep_m = metrics.get("sleep")
    featured_sleep = None
    if sleep_m:
        secs = sleep_m.get("duration_seconds") or 0
        deep_secs = sleep_m.get("deep_sleep_seconds") or 0
        hrv_val = sleep_m.get("hrv") or 0
        avg_hr_val = sleep_m.get("avg_hr") or 0
        dur_pct = min(100, round((secs / (8 * 3600)) * 100)) if secs else 0
        deep_pct = min(100, round((deep_secs / secs) * 100)) if secs > 0 else 0
        featured_sleep = {
            "durationLabel": _fmt_duration(secs) if secs else "—",
            "durationPct": dur_pct,
            "deepLabel": _fmt_duration(deep_secs) if deep_secs else "—",
            "deepPct": deep_pct,
            "hrv": hrv_val,
            "avgHr": avg_hr_val,
            "hrvDelta": "—",
            "source": sleep_m.get("source", "Garmin"),
            "insight": None,
        }

    # ── Featured workout ───────────────────────────────────────────────────
    workout_m = metrics.get("workout")
    featured_workout = None
    from shared.db import get_pool as _get_pool
    from datetime import timedelta
    _pool = await _get_pool()
    _now = datetime.now(timezone.utc)
    _7d_start = _now - timedelta(days=7)
    try:
        load_rows = await _pool.fetch(
            """SELECT date_trunc('day', recorded_at AT TIME ZONE 'UTC')::date AS day,
               ROUND(SUM(COALESCE((data->>'duration_seconds')::float, 0)) / 60.0)::int AS minutes
               FROM health_logs
               WHERE user_id = $1 AND agent='workout' AND type='activity'
                 AND recorded_at >= $2
               GROUP BY day ORDER BY day""",
            user_id, _7d_start,
        )
        load_map = {str(r["day"]): (r["minutes"] or 0) for r in load_rows}
        load_history = [
            load_map.get(str((_now - timedelta(days=6 - i)).date()), 0)
            for i in range(7)
        ]
    except Exception:
        load_history = [0, 0, 0, 0, 0, 0, 0]

    if workout_m:
        dist_km = round((workout_m.get("total_distance_meters") or 0) / 1000, 1)
        name = workout_m.get("first_name") or workout_m.get("first_type") or "Workout"
        extra = max(0, (workout_m.get("activity_count") or 1) - 1)
        last_at = workout_m.get("last_at")
        featured_workout = {
            "sessionName": name,
            "distanceKm": dist_km,
            "kcal": workout_m.get("total_calories") or 0,
            "avgHr": workout_m.get("avg_hr") or 0,
            "source": workout_m.get("source", "Garmin"),
            "extraCount": extra,
            "loadHistory": load_history,
            "workoutDate": "today" if workout_is_today else "yesterday",
            "workoutAt": last_at.isoformat() if last_at else None,
        }
    elif any(v > 0 for v in load_history):
        # No workout today/yesterday but recent training in last 7d — fall back
        # to the most recent session so the spark + card still show real data.
        last_row = await _pool.fetchrow(
            """SELECT data->>'name' AS name,
                      data->>'activity_type' AS activity_type,
                      COALESCE((data->>'distance_meters')::float, 0) AS distance_m,
                      COALESCE((data->>'calories')::float, 0) AS kcal,
                      source,
                      recorded_at
               FROM health_logs
               WHERE user_id = $1 AND agent='workout' AND type='activity'
                 AND recorded_at >= $2
               ORDER BY recorded_at DESC LIMIT 1""",
            user_id, _7d_start,
        )
        if last_row:
            featured_workout = {
                "sessionName": last_row["name"] or last_row["activity_type"] or "Workout",
                "distanceKm": round(last_row["distance_m"] / 1000, 1),
                "kcal": int(last_row["kcal"] or 0),
                "avgHr": 0,
                "source": last_row["source"] or "Garmin",
                "extraCount": 0,
                "loadHistory": load_history,
                "workoutDate": "yesterday",
                "workoutAt": last_row["recorded_at"].isoformat(),
            }

    # ── Featured nutrition ─────────────────────────────────────────────────
    nutrition_m = metrics.get("nutrition")
    featured_nutrition = None
    kcal_goal = 0
    weight_kg_for_macros = 75.0
    if nutrition_m and nutrition_m.get("kcal") is not None:
        try:
            weight_kg_for_macros = profile.get("weight_kg") or 75.0
            override = profile.get("calorie_goal_override")
            if override:
                kcal_goal = int(override)
            elif all([weight_kg_for_macros, profile.get("height_cm"), profile.get("age"),
                      profile.get("sex"), profile.get("activity_level")]):
                kcal_goal = _compute_tdee(
                    weight_kg_for_macros, profile["height_cm"], profile["age"],
                    profile["sex"], profile["activity_level"],
                )
        except Exception:
            pass
        featured_nutrition = {
            "kcalConsumed": int(nutrition_m["kcal"]),
            "kcalGoal": kcal_goal or 2000,
            "proteinG": int(nutrition_m.get("protein_g") or 0),
            "proteinGoalG": max(1, round(weight_kg_for_macros * 1.8)),
            "carbsG": int(nutrition_m.get("carbs_g") or 0),
            "carbsGoalG": max(1, round(weight_kg_for_macros * 4.0)),
            "fatG": int(nutrition_m.get("fat_g") or 0),
            "fatGoalG": max(1, round(weight_kg_for_macros * 1.0)),
            "source": nutrition_m.get("source", "Yazio"),
            "nutritionDate": "today" if nutrition_is_today else "yesterday",
        }

    # ── Featured body ──────────────────────────────────────────────────────
    featured_body = await _build_featured_body(user_id)

    # ── Body agent tile ────────────────────────────────────────────────────
    # Mirrors featured_body so the home grid and detail card stay aligned.
    if featured_body:
        body_pills = []
        delta_w = featured_body.get("weightDelta30d")
        if delta_w is not None:
            sign = "+" if delta_w > 0 else ""
            body_pills.append(f"{sign}{delta_w}kg 30d")
        fat = featured_body.get("fatPct")
        if fat is not None:
            body_pills.append(f"Fat {fat}%")
        agents.append({
            "agent": "body",
            "label": "Body",
            "metric": f"{featured_body['weightKg']} kg",
            "tint": "neutral",
            "detail": " · ".join(body_pills) if body_pills else None,
            "progress": None,
        })

    # ── Rings ──────────────────────────────────────────────────────────────
    recovery_m = metrics.get("recovery")

    from shared.db import get_pool as _get_pool
    _rings_pool = await _get_pool()

    # 7-day average HRV — matches the Garmin watch HRV Status widget
    # (the watch shows the rolling baseline, not last night's single reading).
    # Prefer hrv_status rows (HRV Status API); fall back to sleep_session
    # hrv_weekly_avg when HRV Status isn't synced yet.
    try:
        _hrv_row = await _rings_pool.fetchrow(
            """
            SELECT AVG((data->>'hrv_rmssd')::float) AS hrv_avg,
                   (array_agg((data->>'baseline_low')::float
                              ORDER BY recorded_at DESC))[1] AS bl_low,
                   (array_agg((data->>'baseline_high')::float
                              ORDER BY recorded_at DESC))[1] AS bl_high
            FROM health_logs
            WHERE user_id = $1 AND agent = 'sleep' AND type = 'hrv_status'
              AND recorded_at >= NOW() - INTERVAL '7 days'
              AND data->>'hrv_rmssd' IS NOT NULL
            """,
            user_id,
        )
        _hrv_ms = int(round(_hrv_row["hrv_avg"])) if _hrv_row and _hrv_row["hrv_avg"] else None
        _hrv_bl_low = _hrv_row["bl_low"] if _hrv_row else None
        _hrv_bl_high = _hrv_row["bl_high"] if _hrv_row else None
        if _hrv_ms is None:
            _fb = await _rings_pool.fetchrow(
                """
                SELECT AVG((data->>'hrv_weekly_avg')::float) AS hrv_avg
                FROM health_logs
                WHERE user_id = $1 AND agent = 'sleep' AND type = 'sleep_session'
                  AND recorded_at >= NOW() - INTERVAL '7 days'
                  AND data->>'hrv_weekly_avg' IS NOT NULL
                """,
                user_id,
            )
            if _fb and _fb["hrv_avg"]:
                _hrv_ms = int(round(_fb["hrv_avg"]))
    except Exception:
        _hrv_ms = None
        _hrv_bl_low = None
        _hrv_bl_high = None

    # Compute ring pct: position within personal baseline band, fallback to fixed 80ms scale
    def _hrv_ring_pct(ms: int | None, bl_low: float | None, bl_high: float | None) -> int | None:
        if ms is None:
            return None
        if bl_low and bl_high and bl_high > bl_low:
            return min(100, max(0, round((ms - bl_low) / (bl_high - bl_low) * 100)))
        return min(100, round(ms / 80 * 100))

    # Most recent Garmin steps (last 36 h covers early-morning when today's sync hasn't run yet)
    try:
        _steps_row = await _rings_pool.fetchrow(
            """
            SELECT (data->>'steps')::float AS step_count
            FROM health_logs
            WHERE user_id = $1 AND type = 'daily_stats' AND source = 'garmin'
              AND recorded_at >= NOW() - INTERVAL '36 hours'
              AND (data->>'steps')::float > 0
            ORDER BY recorded_at DESC
            LIMIT 1
            """,
            user_id,
        )
        _steps_today = _steps_row["step_count"] if _steps_row else None
    except Exception:
        _steps_today = None

    # ready: null when insufficient data so ring shows — instead of 0%
    ready_pct_val: int | None = {"recovered": 85, "neutral": 55, "depleted": 20}.get(
        (recovery_m or {}).get("bucket", ""), None
    )

    rings = {
        "readyPct": ready_pct_val,
        "hrvPct": _hrv_ring_pct(_hrv_ms, _hrv_bl_low, _hrv_bl_high),
        "hrvMs": _hrv_ms,
        "moodPct": _mood_pct((metrics.get("mood") or {}).get("avg_score")),
        "stepsPct": _steps_pct(_steps_today),
    }

    return {
        "agents": agents,
        "rings": rings,
        "featured_sleep": featured_sleep,
        "featured_workout": featured_workout,
        "featured_nutrition": featured_nutrition,
        "featured_body": featured_body,
    }


@app.post("/finance/upload")
async def finance_upload(
    file: UploadFile = File(..., alias="csv"),
    user_id: UUID = Depends(current_user),
):
    """Parse a Payoneer PDF monthly statement, UPSERT rows, categorize new
    ones, return a summary string.

    Historically this endpoint accepted CSV; Payoneer no longer exports CSV,
    so the field name `csv` is kept only as a form-field alias for
    backwards-compatibility with earlier client builds. The actual
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

    ingest_result = await ingest_rows(user_id, rows)
    await categorize_new(user_id, ingest_result["uncategorized_ids"])

    # Build income/spending summary for the months represented in this upload.
    months = sorted({r["ts"].strftime("%Y-%m") for r in rows}) or [""]
    income_total: dict[str, Decimal] = {}
    spending_total: dict[str, Decimal] = {}
    top_categories: list[tuple[str, Decimal, str]] = []
    for m in months:
        inc = await income_for_month(user_id, m)
        for cur, amt in inc.items():
            income_total[cur] = income_total.get(cur, Decimal("0")) + amt
        spend = await spending_by_category(user_id, m)
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


def _thread_title(thread_id: str) -> str:
    if thread_id.startswith("tg-"):
        return "Legacy chat"
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


@app.get("/me")
async def get_me(user_id: UUID = Depends(current_user)) -> dict:
    return {"id": str(user_id), "voice_preset": "calm_coach"}


@app.get("/me/profile")
async def get_profile(user_id: UUID = Depends(current_user)) -> dict:
    from .db import get_body_profile, fetch_body_logs
    profile = await get_body_profile(user_id)
    # Auto-fill weight from latest body_composition log if not in profile
    weight_kg = profile.get("weight_kg")
    if weight_kg is None:
        try:
            rows = await fetch_body_logs(user_id, limit=1)
            if rows:
                weight_kg = rows[0].get("data", {}).get("weight_kg")
        except Exception:
            pass
    tdee_kcal = None
    if all([
        profile.get("height_cm"),
        weight_kg,
        profile.get("age"),
        profile.get("sex"),
        profile.get("activity_level"),
    ]):
        tdee_kcal = _compute_tdee(
            weight_kg,
            profile["height_cm"],
            profile["age"],
            profile["sex"],
            profile["activity_level"],
        )
    return {
        "height_cm": profile.get("height_cm"),
        "weight_kg": weight_kg,
        "age": profile.get("age"),
        "sex": profile.get("sex"),
        "activity_level": profile.get("activity_level"),
        "calorie_goal_override": profile.get("calorie_goal_override"),
        "tdee_kcal": tdee_kcal,
    }


@app.patch("/me/profile")
async def update_profile(body: BodyProfileUpdate, user_id: UUID = Depends(current_user)) -> dict:
    from .db import save_body_profile
    updates = body.model_dump(exclude_unset=True)
    await save_body_profile(user_id, updates)
    return {"ok": True}


@app.post("/me/profile/import-pdf")
async def import_vihealth_pdf(
    file: UploadFile = File(...),
    user_id: UUID = Depends(current_user),
) -> ViHealthProfileImport:
    from .file_router import detect_file_type, _ingest_vihealth
    from .vihealth_pdf import extract_profile_fields

    ct = (file.content_type or "").lower()
    name = (file.filename or "").lower()
    if "pdf" not in ct and not name.endswith(".pdf"):
        raise HTTPException(status_code=415, detail="expected application/pdf")

    blob = await file.read()
    if len(blob) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="pdf > 10 MB")

    file_type = detect_file_type(blob)
    if file_type == "payoneer":
        raise HTTPException(status_code=422, detail="not a ViHealth PDF")

    fields = extract_profile_fields(blob)
    if not fields:
        raise HTTPException(status_code=422, detail="could not extract profile fields")

    # Ingest body composition data if PDF has a text layer (pdfplumber path)
    # For image-only PDFs, file_type is "unknown" and _ingest_vihealth would return empty
    if file_type == "vihealth":
        await _ingest_vihealth(blob, user_id)

    return ViHealthProfileImport(**fields)


@app.get("/chat/threads")
async def list_threads(user_id: UUID = Depends(current_user)) -> list:
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
