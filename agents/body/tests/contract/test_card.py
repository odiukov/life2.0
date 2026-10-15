from body.adapters.a2a.card import PEER_SKILLS, SKILLS, build_agent_card
from shared.skill_ids import Body, Dashboard, Feed


def test_card_preserves_analysis_and_advertises_structured_import() -> None:
    card = build_agent_card("http://agent-body:8004/")
    legacy = [s for s in SKILLS if s.id not in {Dashboard.CARD, Dashboard.DETAIL, Feed.EVENTS}]
    assert card.name == "body-agent"
    assert card.url == "http://agent-body:8004/"
    assert [s.id for s in legacy] == [Body.GET_LATEST, Body.ANALYZE_TREND, Body.IMPORT_VIHEALTH]
    assert legacy[0].examples == ["сколько я вешу", "what's my weight", "current body fat"]
    assert PEER_SKILLS == {
        "nutrition": "analyze_nutrition",
        "workout": "analyze_workout",
        "recovery": "analyze_recovery_trend",
    }

    assert card.protocol_version == "0.3.0"
    assert len(card.skills) == 5
    assert card.version == "1.0.0"
    assert card.capabilities.streaming is True
    assert card.capabilities.push_notifications is False
    assert card.default_input_modes == card.default_output_modes == ["text"]

    assert card.description == (
        "Owns body-composition data (weight, fat %, muscle, BMR, visceral fat, body age) "
        "ingested from ViHealth/LePulse scales. Answers current-state queries and trend analyses."
    )
    assert [s.name for s in legacy[:2]] == ["Get Latest Body Composition", "Analyze Body Trend"]
    assert [s.tags for s in legacy[:2]] == [["body", "weight", "query"], ["body", "analysis"]]
    assert legacy[1].examples == [
        "проанализируй историю веса",
        "how has my body composition changed",
    ]
    assert [s.description for s in legacy[:2]] == [
        "Return the most recent weight, body fat %, muscle and related metrics.",
        "Analyze weight / fat / muscle dynamics and correlate with nutrition and training.",
    ]

    assert legacy[2].input_modes == ["application/pdf"]
    assert legacy[2].tags == ["body", "import", "structured"]


def test_card_declares_dashboard_skills() -> None:
    assert {s.id for s in SKILLS if "dashboard" in s.tags} == {Dashboard.CARD}


def test_card_declares_structured_feed() -> None:
    assert next(s for s in SKILLS if s.id == Feed.EVENTS).tags == ["structured"]
