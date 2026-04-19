from a2a.types import AgentCapabilities, AgentCard


def build_agent_card() -> AgentCard:
    return AgentCard(
        protocol_version="0.3.0",
        name="medication-agent",
        description="stub",
        url="http://agent-medication:8008/",
        version="0.0.1",
        capabilities=AgentCapabilities(streaming=True, push_notifications=False),
        default_input_modes=["text"],
        default_output_modes=["text"],
        skills=[],
    )
