"""dashboard.card / dashboard.detail for calendar. Google is called outside any database transaction."""

from __future__ import annotations

import asyncio
from datetime import datetime, time

from shared.a2a.executor import SkillResult
from shared.a2a.request import SkillRequest
from shared.dashboard import DashboardContext, empty_card
from shared.ports.clock import Clock
from shared.ports.uow import UnitOfWorkFactory
from shared.ports.users import UserSettingsRepository

from calendar_agent.application.ports import (
    CalendarAuthError,
    CalendarUnavailable,
    GoogleCalendar,
    GoogleOAuth,
)
from calendar_agent.application.tokens import NotConnected, TokenProvider
from calendar_agent.domain.events import Event, day_shape, normalize

CARD_TIMEOUT_S = 2.0  # the legacy budget: a slow calendar must never stall the home screen
DETAIL_TIMEOUT_S = 10.0
MAX_EVENTS = 20


def _detail_event(e: Event, ctx: DashboardContext) -> dict[str, object]:
    if e.all_day or e.start is None or e.end is None:
        return {"time": "All day", "name": e.summary or "All-day event", "dur": "", "all_day": True}
    start, end = e.start.astimezone(ctx.zone), e.end.astimezone(ctx.zone)
    minutes = max(0, int((end - start).total_seconds() // 60))
    return {
        "time": start.strftime("%H:%M"),
        "name": e.summary or "Untitled",
        "dur": f"{minutes // 60}h" if minutes and minutes % 60 == 0 else f"{minutes}m",
        "start": start.isoformat(),
        "end": end.isoformat(),
        "all_day": False,
    }


class _Base:
    def __init__(
        self, *, uow: UnitOfWorkFactory, google: GoogleCalendar, oauth: GoogleOAuth, clock: Clock
    ) -> None:
        self._uow = uow
        self._google = google
        self._clock = clock
        self._tokens = TokenProvider(uow=uow, oauth=oauth, clock=clock)

    async def _context(self, request: SkillRequest) -> DashboardContext:
        async with self._uow.for_user(request.user_id) as tx:
            settings = await tx.repo(UserSettingsRepository).get(request.user_id)
        return DashboardContext(request.user_id, settings, self._clock.now())

    async def _events(self, ctx: DashboardContext, timeout_s: float) -> list[Event] | None:
        """Today's events, or None when the calendar is not connected, slow or down."""
        try:
            async with asyncio.timeout(timeout_s):
                token = await self._tokens.fresh(ctx.user_id)
                raw = await self._google.list_events(
                    token,
                    time_min=datetime.combine(ctx.today, time.min, tzinfo=ctx.zone).isoformat(),
                    time_max=datetime.combine(ctx.today, time.max, tzinfo=ctx.zone).isoformat(),
                    max_results=MAX_EVENTS,
                    timeout_s=timeout_s,
                )
        except (NotConnected, CalendarAuthError, CalendarUnavailable, TimeoutError):
            return None
        return [e for r in raw if (e := normalize(r, ctx.zone))]


class CalendarCard(_Base):
    async def __call__(self, request: SkillRequest, consult: tuple[str, ...]) -> SkillResult:
        ctx = await self._context(request)
        events = await self._events(ctx, CARD_TIMEOUT_S)
        out = empty_card()
        shape = day_shape(events or [], ctx.today, ctx.now, ctx.zone)
        if shape:
            count = int(shape.get("events_count") or 0)  # type: ignore[call-overload]
            bits = []
            if shape.get("first_free_slot_start") and shape.get("first_free_slot_len_min"):
                bits.append(
                    f"Free {shape['first_free_slot_start']} · {shape['first_free_slot_len_min']}m"
                )
            all_day = shape.get("all_day_events") or []
            if all_day:
                bits.append(f"All-day: {all_day[0]}")  # type: ignore[index]
            out["tile"] = {
                "agent": "calendar",
                "label": "Calendar",
                "metric": f"{count} event{'s' if count != 1 else ''}",
                "tint": "neutral" if count < 5 else "warn",
                "detail": " · ".join(bits) if bits else None,
                "progress": min(count / 8, 1.0),
            }
        return SkillResult(output="card", data=out)


class CalendarDetail(_Base):
    async def __call__(self, request: SkillRequest, consult: tuple[str, ...]) -> SkillResult:
        ctx = await self._context(request)
        events = await self._events(ctx, DETAIL_TIMEOUT_S) or []
        rows = [_detail_event(e, ctx) for e in events]
        busy = sum(
            max(0, int((e.end - e.start).total_seconds() // 60))
            for e in events
            if not e.all_day and e.start and e.end
        )
        shape = day_shape(events, ctx.today, ctx.now, ctx.zone) or {}
        metrics: dict[str, object] = {
            "events_count": len(rows),
            "busy_minutes": busy,
            "events": rows[:10],
            "first_free_slot_start": shape.get("first_free_slot_start"),
            "first_free_slot_len_min": shape.get("first_free_slot_len_min"),
        }
        if not rows:
            text = "No calendar events found today."
        elif metrics["first_free_slot_start"] and metrics["first_free_slot_len_min"]:
            text = f"First free block starts at {metrics['first_free_slot_start']} for {metrics['first_free_slot_len_min']} minutes."
        else:
            text = f"{len(rows)} event(s) on the calendar today."
        return SkillResult(
            output="detail",
            data={"agent": "calendar", "insight": text, "metrics": metrics, "history": []},
        )
