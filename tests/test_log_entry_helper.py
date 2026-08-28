"""Test the make_log_entry_artifact helper produces the canonical shape
that orchestrator's _extract_log_entry_from_task expects."""
from datetime import datetime, timezone


def test_make_log_entry_artifact_produces_canonical_shape():
    from shared.log_entry import make_log_entry_artifact
    from a2a.types import DataPart

    art = make_log_entry_artifact("hello world")
    assert art.name == "log_entry"
    assert len(art.parts) == 1
    root = getattr(art.parts[0], "root", art.parts[0])
    assert isinstance(root, DataPart)
    assert root.data["summary"] == "hello world"
    assert "timestamp" in root.data
    # parses as ISO-8601 with timezone
    datetime.fromisoformat(root.data["timestamp"])


def test_make_log_entry_artifact_clips_long_summary():
    from shared.log_entry import make_log_entry_artifact

    long_text = "x" * 200
    art = make_log_entry_artifact(long_text)
    root = getattr(art.parts[0], "root", art.parts[0])
    assert len(root.data["summary"]) <= 120
    assert root.data["summary"].endswith("…")


def test_make_log_entry_artifact_uses_provided_timestamp():
    from shared.log_entry import make_log_entry_artifact

    fixed = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    art = make_log_entry_artifact("ok", recorded_at=fixed)
    root = getattr(art.parts[0], "root", art.parts[0])
    assert root.data["timestamp"] == "2025-01-01T12:00:00+00:00"
