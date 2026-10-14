from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from mood.application.schemas import MoodExtraction
from mood.domain.entry import MoodEntry, has_signal, mood_line
from shared.ports.health_logs import HealthLogRow

AT = datetime(2026, 10, 13, 18, 5, tzinfo=UTC)


def test_schema_clamps_tags_and_rejects_out_of_range() -> None:
    e = MoodExtraction(
        mood_score=7, tags=[" Tired ", "WORK", "", "a", "b", "c", "d", "e"], summary="tired"
    )
    assert e.tags == ["tired", "work", "a", "b", "c", "d"]
    try:
        MoodExtraction(mood_score=11, summary="x")
    except ValueError:
        pass
    else:
        raise AssertionError("11 must be rejected")


def test_signal() -> None:
    assert has_signal(MoodExtraction(mood_score=None, tags=["calm"], summary="calm"))
    assert not has_signal(MoodExtraction(summary="no mood signal"))


def test_roundtrip_and_line() -> None:
    row = HealthLogRow(
        "mood",
        AT,
        {
            "mood_score": 6,
            "energy": 4,
            "stress": 7,
            "valence": "neg",
            "tags": ["work"],
            "raw_text": "устал от работы, но держусь",
            "source_skill": "log_mood",
        },
        "manual",
        "mood",
    )
    entry = MoodEntry.from_row(row)
    assert entry.to_data() == dict(row.data)
    assert mood_line(entry, ZoneInfo("Europe/Lisbon")) == (
        '- 2026-10-13 19:05 | mood_score=6 | energy=4 | stress=7 | valence=neg | tags=[work] "устал от работы, но держусь"'
    )
