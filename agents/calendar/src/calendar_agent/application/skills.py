"""Structured calendar skills. No model: the orchestrator's model fills typed parameters."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, time
from uuid import UUID
from zoneinfo import ZoneInfo

from shared.a2a.executor import SkillHandler, SkillResult
from shared.a2a.proposals import Proposal, to_data
from shared.a2a.request import SkillRequest
from shared.observability.logging import get_logger
from shared.ports.clock import Clock
from shared.ports.credentials import CredentialStore
from shared.ports.translator import Translator
from shared.ports.uow import UnitOfWorkFactory
from shared.ports.users import UserSettings, UserSettingsRepository
from shared.skill_ids import Calendar

from calendar_agent.application.ports import (
    CalendarAuthError,
    CalendarRejected,
    CalendarUnavailable,
    EventGone,
    GoogleCalendar,
    GoogleOAuth,
    InvalidGrant,
    PreconditionFailed,
)
from calendar_agent.application.tokens import SERVICE, NotConnected, TokenProvider, expires_at
from calendar_agent.domain.changes import InvalidChange, google_body, parse_change
from calendar_agent.domain.events import Event, event_dto, event_line, normalize, title_matches

LIST_TIMEOUT_S = 10.0
MAX_EVENTS = 50
logger = get_logger(__name__)


def _fail(code: str) -> SkillResult:
    return SkillResult(output=code, failed=True)


def _day(value: object) -> date | None:
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


@dataclass
class _Deps:
    uow: UnitOfWorkFactory
    google: GoogleCalendar
    oauth: GoogleOAuth
    tokens: TokenProvider
    clock: Clock
    tr: Translator
    default_locale: str

    async def settings(self, user: UUID) -> UserSettings:
        async with self.uow.for_user(user) as tx:
            return await tx.repo(UserSettingsRepository).get(user)

    async def events_on(
        self,
        user: UUID,
        day: date,
        zone: ZoneInfo,
        limit: int = MAX_EVENTS,
        timeout_s: float = LIST_TIMEOUT_S,
    ) -> list[Event]:
        token = await self.tokens.fresh(user)
        raw = await self.google.list_events(
            token,
            time_min=datetime.combine(day, time.min, tzinfo=zone).isoformat(),
            time_max=datetime.combine(day, time.max, tzinfo=zone).isoformat(),
            max_results=limit,
            timeout_s=timeout_s,
        )
        return [e for r in raw if (e := normalize(r, zone))]


Body = Callable[[SkillRequest], Awaitable[SkillResult]]


def _guard(handler: Body) -> SkillHandler:
    """Map the shared failure modes to codes; keeps every skill body about its own logic."""

    async def run(request: SkillRequest, consult: tuple[str, ...]) -> SkillResult:
        try:
            return await handler(request)
        except NotConnected:
            return _fail("not_connected")
        except CalendarAuthError:
            return _fail("not_connected")
        except CalendarUnavailable:
            return _fail("calendar_unavailable")
        except EventGone:
            return _fail("not_found")
        except PreconditionFailed:
            return _fail("changed_since_proposal")
        except CalendarRejected as exc:
            logger.warning("calendar_rejected", status=exc.status)
            return _fail("rejected_by_google")

    return run


def build_skills(
    *,
    uow: UnitOfWorkFactory,
    google: GoogleCalendar,
    oauth: GoogleOAuth,
    clock: Clock,
    translator: Translator,
    default_locale: str,
) -> dict[str, SkillHandler]:
    d = _Deps(
        uow,
        google,
        oauth,
        TokenProvider(uow=uow, oauth=oauth, clock=clock),
        clock,
        translator,
        default_locale,
    )

    async def connect(request: SkillRequest) -> SkillResult:
        code, verifier = request.params.get("code"), request.params.get("code_verifier")
        if not isinstance(code, str) or not isinstance(verifier, str) or not code or not verifier:
            return _fail("invalid_params")
        try:
            tokens = await oauth.exchange_code(code, verifier)
        except InvalidGrant:
            return _fail("invalid_grant")
        if not tokens.refresh_token:
            return _fail(
                "invalid_grant"
            )  # without offline access the connection would die in an hour
        async with uow.for_user(request.user_id) as tx:
            await tx.repo(CredentialStore).put(
                request.user_id,
                SERVICE,
                {
                    "access_token": tokens.access_token,
                    "refresh_token": tokens.refresh_token,
                    "expires_at": expires_at(clock, tokens),
                },
            )
        return SkillResult(output="connected", data={"status": "connected"})

    async def disconnect(request: SkillRequest) -> SkillResult:
        async with uow.for_user(request.user_id) as tx:
            store = tx.repo(CredentialStore)
            creds = await store.get(request.user_id, SERVICE)
            await store.delete(request.user_id, SERVICE)
        if creds and creds.get("refresh_token"):
            await oauth.revoke(str(creds["refresh_token"]))
        return SkillResult(output="disconnected", data={"status": "disconnected"})

    async def status(request: SkillRequest) -> SkillResult:
        async with uow.for_user(request.user_id) as tx:
            connected = (
                await tx.repo(CredentialStore).revision(request.user_id, SERVICE) is not None
            )
        return SkillResult(output=str(connected).lower(), data={"connected": connected})

    async def list_events(request: SkillRequest) -> SkillResult:
        day = _day(request.params.get("day"))
        limit = request.params.get("max", MAX_EVENTS)
        if day is None or type(limit) is not int or not 1 <= limit <= MAX_EVENTS:
            return _fail("invalid_params")
        settings = await d.settings(request.user_id)
        events = await d.events_on(request.user_id, day, settings.timezone, limit=limit)
        lines = [f"Calendar events for {day.isoformat()}:"] + [
            event_line(e, settings.timezone) for e in events
        ]
        if not events:
            lines = [f"No calendar events found for {day.isoformat()}."]
        return SkillResult(output="\n".join(lines), data={"events": [event_dto(e) for e in events]})

    async def propose(request: SkillRequest) -> SkillResult:
        try:
            change = parse_change(request.params)
        except InvalidChange:
            return _fail("invalid_params")
        settings = await d.settings(request.user_id)
        locale = settings.locale or default_locale
        if change.op == "create":
            summary = _summary(
                d, locale, settings.timezone, "create", change.fields["summary"], change.fields
            )
            return SkillResult(
                output=summary,
                data=to_data(
                    Proposal(
                        "calendar.create",
                        summary,
                        {
                            "op": "create",
                            "event_id": None,
                            "etag": None,
                            "fields": dict(change.fields),
                        },
                    )
                ),
            )
        event = await _resolve(d, request, settings)
        if isinstance(event, SkillResult):
            return event
        summary = _summary(
            d, locale, settings.timezone, change.op, event.summary, change.fields, event
        )
        payload = {
            "op": change.op,
            "event_id": event.id,
            "etag": event.etag,
            "fields": dict(change.fields),
        }
        return SkillResult(
            output=summary, data=to_data(Proposal(f"calendar.{change.op}", summary, payload))
        )

    async def apply(request: SkillRequest) -> SkillResult:
        payload = request.params.get("payload")
        if not isinstance(payload, Mapping):
            return _fail("invalid_params")
        try:
            change = parse_change({"op": payload.get("op"), "fields": payload.get("fields") or {}})
        except InvalidChange:
            return _fail("invalid_params")
        event_id, etag = payload.get("event_id"), payload.get("etag")
        if change.op != "create" and (not isinstance(event_id, str) or not isinstance(etag, str)):
            return _fail("invalid_params")
        token = await d.tokens.fresh(request.user_id)
        if change.op == "create":
            result = await google.create_event(token, google_body(change.fields))
        elif change.op == "update":
            result = await google.patch_event(
                token, str(event_id), google_body(change.fields), str(etag)
            )
        else:
            await google.delete_event(token, str(event_id), str(etag))
            result = {"id": event_id, "summary": None}
        return SkillResult(
            output="applied",
            data={
                "status": "applied",
                "event": {"id": result.get("id"), "summary": result.get("summary")},
            },
        )

    return {
        Calendar.CONNECT: _guard(connect),
        Calendar.DISCONNECT: _guard(disconnect),
        Calendar.STATUS: _guard(status),
        Calendar.LIST: _guard(list_events),
        Calendar.PROPOSE: _guard(propose),
        Calendar.APPLY: _guard(apply),
    }


async def _resolve(d: _Deps, request: SkillRequest, settings: UserSettings) -> Event | SkillResult:
    event_id = request.params.get("event_id")
    zone = settings.timezone
    if isinstance(event_id, str) and event_id:
        token = await d.tokens.fresh(request.user_id)
        found = normalize(await d.google.get_event(token, event_id), zone)
        return found if found is not None else _fail("not_found")
    title, day = request.params.get("title"), _day(request.params.get("day"))
    if not isinstance(title, str) or not title.strip() or day is None:
        return _fail("invalid_params")
    events = await d.events_on(request.user_id, day, zone)
    stopwords = frozenset(d.tr.t("calendar.title_stopwords", "ru").split())
    matches = [e for e in events if e.id and title_matches(title, e.summary, stopwords)]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        return SkillResult(
            output="not_found",
            data={"kind": "not_found", "visible": [event_dto(e) for e in events]},
        )
    return SkillResult(
        output="ambiguous",
        data={"kind": "ambiguous", "candidates": [event_dto(e) for e in matches]},
    )


def _when(
    d: _Deps,
    locale: str,
    zone: ZoneInfo,
    start: datetime | None,
    end: datetime | None,
    day: date | None,
) -> str:
    if start is None or end is None:
        return d.tr.t(
            "calendar.proposal.all_day", locale, day=d.tr.date(day or d.clock.now().date(), locale)
        )
    local_start, local_end = start.astimezone(zone), end.astimezone(zone)
    return f"{d.tr.date(local_start.date(), locale)} {local_start:%H:%M}–{local_end:%H:%M}"


def _summary(
    d: _Deps,
    locale: str,
    zone: ZoneInfo,
    op: str,
    title: str,
    fields: Mapping[str, str],
    event: Event | None = None,
) -> str:
    if op == "create":
        when = _when(
            d,
            locale,
            zone,
            datetime.fromisoformat(fields["start"]),
            datetime.fromisoformat(fields["end"]),
            None,
        )
        return d.tr.t("calendar.proposal.create", locale, title=title, when=when)
    assert event is not None
    when = _when(d, locale, zone, event.start, event.end, event.day)
    if op == "delete":
        return d.tr.t("calendar.proposal.delete", locale, title=title, when=when)
    changes = []
    if "summary" in fields:
        changes.append(d.tr.t("calendar.proposal.rename", locale, title=fields["summary"]))
    if "start" in fields:
        changes.append(
            _when(
                d,
                locale,
                zone,
                datetime.fromisoformat(fields["start"]),
                datetime.fromisoformat(fields["end"]),
                None,
            )
        )
    for key in ("description", "location"):
        if key in fields:
            changes.append(d.tr.t(f"calendar.proposal.{key}", locale))
    return d.tr.t(
        "calendar.proposal.update", locale, title=title, when=when, changes="; ".join(changes)
    )
