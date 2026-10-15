"""Which Home Assistant tools only read, and how a pending tool call is described."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

# Explicit allow-list. Every tool not listed here — including tools a future Home Assistant adds —
# is treated as a change and needs the user's confirmation.
READ_ONLY_TOOLS = frozenset({"GetLiveContext", "GetDateTime", "todo_get_items"})
KNOWN_ACTIONS = frozenset(
    {
        "HassTurnOn",
        "HassTurnOff",
        "HassLightSet",
        "HassClimateSetTemperature",
        "HassListAddItem",
        "HassMediaPause",
        "HassMediaUnpause",
    }
)


@dataclass(frozen=True, slots=True)
class ToolCall:
    tool: str
    args: Mapping[str, object]


def is_read_only(name: str) -> bool:
    return name in READ_ONLY_TOOLS


def action_key(tool: str) -> str:
    """i18n key of the confirmation text for this tool."""
    return f"home.proposal.{tool}" if tool in KNOWN_ACTIONS else "home.proposal.generic"


def target(args: Mapping[str, object]) -> str:
    """The human part of the arguments: entity name, area, then anything else, in that order."""
    parts = [str(args[k]) for k in ("name", "area", "floor", "domain") if args.get(k)]
    if parts:
        parts.extend(f"{k} {args[k]}" for k in ("brightness", "color", "temperature") if k in args)
    else:
        parts = [f"{k}={v}" for k, v in sorted(args.items()) if isinstance(v, str | int | float)]
    return ", ".join(parts)
