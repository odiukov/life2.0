from datetime import UTC, datetime
from uuid import UUID

import pytest
from medication.application.schemas import MedicationDefinition
from medication.domain.medication import Intake, Medication, intake_data
from shared.ports.health_logs import HealthLogRow

MED = Medication(
    id=UUID(int=1),
    name="vitamin-d",
    dose="2000 IU",
    schedule="daily morning",
    notes=None,
    created_at=None,
)


def test_schema_slugifies_and_requires_name_and_schedule() -> None:
    d = MedicationDefinition(name="Vitamin D3", dose="2000 IU", schedule="daily 09:00")
    assert d.name == "vitamin-d3"
    for bad in ({"name": "витамин", "schedule": "daily"}, {"name": "b12", "schedule": " "}):
        with pytest.raises(ValueError, match=r"name must contain|schedule is required"):
            MedicationDefinition(**bad)


def test_intake_data_has_the_legacy_keys_and_round_trips() -> None:
    data = intake_data(MED, "принял витамин д", None, None)
    assert data == {
        "name": "vitamin-d",
        "medication_id": str(MED.id),
        "dose_at_time": "2000 IU",
        "note": None,
        "raw_text": "принял витамин д",
        "source_skill": "log_medication",
    }
    intake = Intake.from_row(
        HealthLogRow(
            "medication_taken", datetime(2026, 10, 13, 8, tzinfo=UTC), data, "manual", "medication"
        )
    )
    assert (intake.name, intake.medication_id, intake.dose_at_time) == (
        "vitamin-d",
        str(MED.id),
        "2000 IU",
    )
