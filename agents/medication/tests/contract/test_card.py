import json
from pathlib import Path

from medication.adapters.a2a.card import PEER_SKILLS, SKILLS, build_agent_card
from shared.skill_ids import Medication


def test_card_is_unchanged() -> None:
    card = build_agent_card("http://agent-medication:8008/")
    assert card.name == "medication-agent"
    assert {s.id for s in SKILLS} == {
        Medication.DEFINE,
        Medication.LOG,
        Medication.LIST,
        Medication.ANALYZE,
        Medication.ARCHIVE,
    }
    assert PEER_SKILLS == {
        "mood": "analyze_mood",
        "sleep": "analyze_sleep",
        "recovery": "analyze_recovery_trend",
    }


def test_complete_legacy_card_metadata() -> None:
    expected = json.loads(Path(__file__).with_name("legacy_card.json").read_text())
    assert build_agent_card("http://agent-medication:8008/").model_dump(mode="json") == expected
