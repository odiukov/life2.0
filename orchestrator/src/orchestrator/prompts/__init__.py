from __future__ import annotations

from datetime import datetime
from importlib.resources import files
from zoneinfo import ZoneInfo

BODY = files(__package__).joinpath("system.md").read_text("utf-8").strip()
LEAD = (
    "This task is led by {lead}. Send messages on {lead}'s topic to its tool — it consults its "
    "colleagues itself; send messages clearly about another domain to that domain's agent."
)


def system_prompt(*, now: datetime, zone: ZoneInfo, lead_agent: str | None) -> str:
    local = now.astimezone(zone)
    head = (
        f"Current date: {local.date().isoformat()} ({zone.key}). "
        "Resolve today/tomorrow/yesterday from this date before choosing tool arguments. "
        "For calendar questions, pass the resolved YYYY-MM-DD date."
    )
    parts = [head, BODY]
    if lead_agent:
        parts.append(LEAD.format(lead=lead_agent))
    return "\n\n".join(parts)
