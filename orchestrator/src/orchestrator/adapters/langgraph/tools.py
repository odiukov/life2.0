"""LangChain tools generated from the agent catalog, bound to one run's context."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any, Literal

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, Field, create_model
from shared.a2a.proposals import from_data
from shared.ports.skills import SkillCallError, SkillClient, SkillUnavailable
from shared.skill_ids import Calendar

from orchestrator.application.ports import (
    HealthSync,
    PeerAgents,
    PeerUnavailable,
    ProposalRecorder,
    RunContext,
    SyncUnavailable,
)
from orchestrator.domain.catalog import CATALOG, CatalogEntry, tool_name
from orchestrator.domain.focus import autodetect_focus_sources, merge_focus_sources

Result = tuple[str, dict[str, Any]]
PROPOSED = "A confirmation card is now shown to the user. Nothing changes until they confirm; do not say it is done."
CALENDAR_ERRORS = {
    "not_connected": "Google Calendar is not connected. Ask the user to connect it in Integrations.",
    "calendar_unavailable": "Google Calendar is unavailable right now; suggest trying again later.",
    "invalid_params": "The calendar request was invalid: use YYYY-MM-DD dates and ISO times with an offset.",
    "not_found": "That event no longer exists.",
}
SYNC_HINTS = {
    "auth_failed": " — reconnect it in Integrations",
    "rate_limited": " — the provider is limiting requests; try later",
}


def _ask_schema(entry: CatalogEntry) -> type[BaseModel]:
    fields: dict[str, Any] = {
        "message": (str, Field(description="The user's words for this agent, unchanged.")),
        "skill": (
            Literal[entry.skills],
            Field(description="The agent skill that matches the intent."),
        ),
    }
    if entry.accepts_focus_sources:
        fields["focus_sources"] = (
            list[str] | None,
            Field(
                default=None,
                description="Domains the user explicitly cites as the basis for advice.",
            ),
        )
    return create_model(f"Ask{entry.name.title()}", **fields)


def _ask_tool(
    entry: CatalogEntry,
    ctx: RunContext,
    last_user_text: str,
    peers: PeerAgents,
    proposals: ProposalRecorder,
) -> BaseTool:
    async def run(message: str, skill: str, focus_sources: list[str] | None = None) -> Result:
        focus = None
        if entry.accepts_focus_sources:
            focus = merge_focus_sources(
                focus_sources,
                autodetect_focus_sources(last_user_text, entry.name, entry.accepts_focus_sources),
            )
        try:
            reply = await peers.ask(
                entry.name, user_id=ctx.user_id, skill=skill, text=message, focus_sources=focus
            )
        except PeerUnavailable:
            return f"The {entry.name} agent is unavailable right now.", {
                "agent": entry.name,
                "consulted": [],
                "failed": True,
            }
        artifact: dict[str, Any] = {"agent": entry.name, "consulted": list(reply.consulted)}
        content = reply.text or f"The {entry.name} agent returned no answer."
        if reply.failed:
            artifact["failed"] = True
        proposal = from_data(reply.data) if entry.proposes_actions and not reply.failed else None
        if proposal is not None and proposal.action != "home.call_tool":
            return "The agent could not prepare that change.", {**artifact, "failed": True}
        if proposal is not None:
            action = await proposals.record(ctx, entry.name, proposal)
            artifact["proposal_id"] = str(action.id)
            content = f"{content}\n\n{PROPOSED}"
        return content, artifact

    return StructuredTool.from_function(
        coroutine=run,
        name=tool_name(entry.name),
        description=entry.description,
        args_schema=_ask_schema(entry),
        response_format="content_and_artifact",
    )


def _lines(events: Sequence[Mapping[str, Any]]) -> str:
    return "\n".join(
        f"• {e.get('summary')} (event_id: {e.get('id')}, {e.get('start') or e.get('day')})"
        for e in events
    )


def _calendar_tools(
    ctx: RunContext, calendar: SkillClient, proposals: ProposalRecorder
) -> list[BaseTool]:
    async def call(
        skill: str, params: dict[str, object]
    ) -> tuple[str | None, Mapping[str, Any] | None, str]:
        try:
            reply = await calendar.call(skill_id=skill, user_id=ctx.user_id, params=params)
        except SkillUnavailable:
            return CALENDAR_ERRORS["calendar_unavailable"], None, ""
        except SkillCallError as exc:
            return CALENDAR_ERRORS.get(exc.code, "The calendar could not do that."), None, ""
        return None, reply.data, reply.text

    async def calendar_list(day: str) -> Result:
        error, _, text = await call(Calendar.LIST, {"day": day})
        return error or text, {
            "agent": "calendar",
            "consulted": [],
            **({"failed": True} if error else {}),
        }

    async def calendar_propose(
        op: Literal["create", "update", "delete"],
        event_id: str | None = None,
        title: str | None = None,
        day: str | None = None,
        summary: str | None = None,
        start: str | None = None,
        end: str | None = None,
        description: str | None = None,
        location: str | None = None,
    ) -> Result:
        fields = {
            k: v
            for k, v in {
                "summary": summary,
                "start": start,
                "end": end,
                "description": description,
                "location": location,
            }.items()
            if v is not None
        }
        params: dict[str, object] = {"op": op, "fields": fields}
        if event_id:
            params["event_id"] = event_id
        if title:
            params["title"], params["day"] = title, day
        error, data, _ = await call(Calendar.PROPOSE, params)
        artifact: dict[str, Any] = {"agent": "calendar", "consulted": []}
        if error:
            return error, {**artifact, "failed": True}
        if data and data.get("kind") == "ambiguous":
            return "Several events match; ask the user which one:\n" + _lines(
                data.get("candidates") or []
            ), artifact
        if data and data.get("kind") == "not_found":
            return "No matching event. Events that day:\n" + (
                _lines(data.get("visible") or []) or "(none)"
            ), artifact
        proposal = from_data(data)
        if proposal is None or proposal.action not in {
            "calendar.create",
            "calendar.update",
            "calendar.delete",
        }:
            return "The calendar could not prepare that change.", {**artifact, "failed": True}
        action = await proposals.record(ctx, "calendar", proposal)
        return f"{proposal.summary}\n\n{PROPOSED}", {**artifact, "proposal_id": str(action.id)}

    return [
        StructuredTool.from_function(
            coroutine=calendar_list,
            name="calendar_list",
            response_format="content_and_artifact",
            description="List the user's Google Calendar events for one day (day=YYYY-MM-DD). Read-only.",
        ),
        StructuredTool.from_function(
            coroutine=calendar_propose,
            name="calendar_propose",
            response_format="content_and_artifact",
            description=(
                "Propose creating, changing or deleting one Google Calendar event. Identify an existing event by "
                "event_id, or by title plus day (YYYY-MM-DD). Times are ISO 8601 with an offset. The user confirms "
                "in the app; nothing changes before that."
            ),
        ),
    ]


def _sync_tool(ctx: RunContext, sync: HealthSync) -> BaseTool:
    async def sync_health_data() -> Result:
        try:
            results = await sync.sync_user(ctx.user_id)
        except SyncUnavailable:
            return "Sync failed: the sync service is unavailable.", {
                "agent": "sync",
                "consulted": [],
                "failed": True,
            }
        parts = []
        for r in results:
            status = str(r.get("status"))
            if status in ("disabled", "not_connected"):
                continue
            line = f"{r.get('service')} {status}"
            if status in ("ok", "partial"):
                line += f" ({r.get('written')} new or updated)"
            parts.append(line + SYNC_HINTS.get(status, ""))
        text = ("Sync: " + "; ".join(parts) + ".") if parts else "Sync: no integrations connected."
        return text, {"agent": "sync", "consulted": []}

    return StructuredTool.from_function(
        coroutine=sync_health_data,
        name="sync_health_data",
        response_format="content_and_artifact",
        description="Synchronize the user's health data from Garmin and Yazio now.",
    )


def build_tools(
    ctx: RunContext,
    *,
    last_user_text: str,
    peers: PeerAgents,
    skills: Callable[[str], SkillClient],
    proposals: ProposalRecorder,
    sync: HealthSync,
) -> list[BaseTool]:
    tools = [
        _ask_tool(e, ctx, last_user_text, peers, proposals)
        for e in CATALOG.values()
        if e.tool == "ask"
    ]
    tools += _calendar_tools(ctx, skills("calendar"), proposals)
    tools.append(_sync_tool(ctx, sync))
    return tools
