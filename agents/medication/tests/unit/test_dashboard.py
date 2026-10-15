from medication.application.dashboard import card, detail
from medication.application.ports import MedicationRepository
from medication.domain.medication import Medication
from medication.testing import InMemoryMedications
from shared.skill_ids import Dashboard
from shared.testing import dashboard_golden as g


def medications_repo() -> InMemoryMedications:
    repo = InMemoryMedications()
    for row in g.medication_rows():
        repo.rows[row["id"]] = Medication(  # type: ignore[index]
            id=row["id"],
            name=str(row["name"]),
            dose=row["dose"],
            schedule=str(row["schedule"]),
            notes=None,
            created_at=row["created_at"],  # type: ignore[arg-type]
        )
    return repo


async def test_card_matches_the_golden() -> None:
    assert await g.golden_call(
        card, Dashboard.CARD, {MedicationRepository: medications_repo()}
    ) == g.expected_card("medication")


async def test_detail_matches_the_golden() -> None:
    assert await g.golden_call(
        detail, Dashboard.DETAIL, {MedicationRepository: medications_repo()}
    ) == g.expected_detail("medication")
