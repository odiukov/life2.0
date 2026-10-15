from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from shared.skill_ids import Calendar

SKILLS = [
    AgentSkill(id=skill, name=name, description=description, tags=["structured"])
    for skill, name, description in (
        (Calendar.CONNECT, "Connect Calendar", "Exchange a PKCE code and store Google tokens."),
        (Calendar.DISCONNECT, "Disconnect Calendar", "Remove the connection and revoke its token."),
        (Calendar.STATUS, "Connection Status", "Check whether Google Calendar is connected."),
        (Calendar.LIST, "List Events", "List normalized events on a day in the user timezone."),
        (
            Calendar.PROPOSE,
            "Propose Change",
            "Resolve an event and propose a change for confirmation.",
        ),
        (Calendar.APPLY, "Apply Change", "Apply a confirmed change using its event etag."),
    )
]


def build_agent_card(url: str) -> AgentCard:
    return AgentCard(
        protocol_version="0.3.0",
        name="calendar-agent",
        description="Google Calendar of the user: events, the shape of the day, and confirmed changes.",
        url=url,
        version="1.0.0",
        capabilities=AgentCapabilities(streaming=True, push_notifications=False),
        default_input_modes=["data"],
        default_output_modes=["text", "data"],
        skills=SKILLS,
    )
