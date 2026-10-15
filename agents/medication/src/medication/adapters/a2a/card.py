from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from shared.skill_ids import Dashboard, Feed, Medication

SKILLS: list[AgentSkill] = [
    AgentSkill(
        id=Feed.EVENTS,
        name="Day Feed",
        description="Structured events of a local day.",
        tags=["feed", "structured"],
    ),
    AgentSkill(
        id=Dashboard.CARD,
        name="Dashboard Card",
        description="Structured dashboard card.",
        tags=["dashboard", "structured"],
    ),
    AgentSkill(
        id=Dashboard.DETAIL,
        name="Dashboard Detail",
        description="Structured dashboard detail.",
        tags=["dashboard", "structured"],
    ),
    AgentSkill(
        id=Medication.DEFINE,
        name="Define Medication",
        description=(
            "Parse free text into a structured medication definition: name "
            "(kebab-case), dose (e.g. '200mg'), schedule (free-text e.g. "
            "'daily 21:00' or 'mon,wed,fri morning'), optional notes. Inserts "
            "a row in the medications table."
        ),
        tags=["medication", "define"],
        examples=[
            "магний 200мг каждый вечер в 21:00",
            "vitamin D 2000IU every morning",
            "iron 25mg mon/wed/fri",
        ],
    ),
    AgentSkill(
        id=Medication.LOG,
        name="Log Medication Taken",
        description=(
            "Record a single dose taken. Accepts {name} (resolved via registry "
            "with name normalization) and optional {dose_override, note}."
        ),
        tags=["medication", "log"],
        examples=[
            "/med magnesium",
            "выпил магний вечером",
            "took iron with breakfast",
        ],
    ),
    AgentSkill(
        id=Medication.LIST,
        name="List Active Medications",
        description=("Deterministic list of active medications with last-taken recency."),
        tags=["medication", "list"],
        examples=["/med list", "what am I currently taking"],
    ),
    AgentSkill(
        id=Medication.ANALYZE,
        name="Analyze Adherence",
        description=(
            "Compute adherence window (default 14 days): expected doses from "
            "schedule × actual logs from health_logs → percentage + missed days + "
            "streak. Aggregations in SQL, final summary via LLM."
        ),
        tags=["medication", "analysis"],
        examples=[
            "how's my medication adherence",
            "did I miss any doses last week",
        ],
    ),
    AgentSkill(
        id=Medication.ARCHIVE,
        name="Archive Medication",
        description=(
            "Soft-delete a medication (set archived_at). History in health_logs "
            "is preserved via the denormalized `name` field."
        ),
        tags=["medication", "archive"],
        examples=["/med stop magnesium", "stop tracking iron"],
    ),
]


LEGACY_DESCRIPTION = "Owns medication/supplement definitions and intake logs: creates schedules, records doses taken, and computes adherence."


def build_agent_card(url: str) -> AgentCard:
    return AgentCard(
        protocol_version="0.3.0",
        name="medication-agent",
        description=LEGACY_DESCRIPTION,
        url=url,
        version="1.0.0",
        capabilities=AgentCapabilities(streaming=True, push_notifications=False),
        default_input_modes=["text"],
        default_output_modes=["text"],
        skills=SKILLS,
    )


PEER_SKILLS: dict[str, str] = {
    "mood": "analyze_mood",
    "sleep": "analyze_sleep",
    "recovery": "analyze_recovery_trend",
}
