from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from shared.skill_ids import Home

SKILLS = [
    AgentSkill(id=skill, name=name, description=description, tags=["structured"])
    for skill, name, description in (
        (Home.CONNECT, "Connect Home", "Validate and save the household connection."),
        (Home.DISCONNECT, "Disconnect Home", "Remove the household connection."),
        (Home.STATUS, "Connection Status", "Show who connected Home Assistant and when."),
        (Home.TEST, "Test Connection", "Check the Home Assistant connection."),
        (
            Home.APPLY,
            "Apply Action",
            "Run a confirmed change after checking household and connection.",
        ),
    )
]
SKILLS.append(
    AgentSkill(
        id=Home.ASK,
        name="Ask Home",
        description="Answer home questions and propose changes for confirmation.",
        tags=["home"],
        examples=["выключи свет в гостиной", "what's the temperature in the bedroom"],
    )
)


def build_agent_card(url: str) -> AgentCard:
    return AgentCard(
        protocol_version="0.3.0",
        name="home-agent",
        description="The household's Home Assistant: questions about the home and confirmed changes.",
        url=url,
        version="1.0.0",
        capabilities=AgentCapabilities(streaming=True, push_notifications=False),
        default_input_modes=["text", "data"],
        default_output_modes=["text", "data"],
        skills=SKILLS,
    )
