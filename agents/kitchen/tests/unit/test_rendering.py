from decimal import Decimal
from uuid import uuid4

from kitchen.application.rendering import KitchenText
from kitchen.application.service import AppliedChange, ApplyResult, UndoOutcome
from kitchen.domain.model import ExpirySource, Status, Unit
from kitchen.testing import make_batch
from shared.adapters.i18n import JsonTranslator
from shared.config import find_locales_dir

TEXT = KitchenText(JsonTranslator.from_dir(find_locales_dir()))


def test_quantities_are_humanized_and_localized() -> None:
    batch = make_batch(
        id=1,
        quantity=Decimal("1500"),
        unit=Unit.G,
        display_name="курица",
        expiry_source=ExpirySource.EXPLICIT,
    )
    assert TEXT.line("ru", batch).startswith("• курица — 1,5 кг (до ")
    assert TEXT.line("en", batch).startswith("• курица — 1.5 kg (until ")


def test_sections_not_found_and_hint() -> None:
    before = make_batch(id=1)
    after = make_batch(id=1, quantity=Decimal(0), status=Status.CONSUMED)
    result = ApplyResult(group_id=uuid4(), changes=[AppliedChange("consume", before, after)])
    text = TEXT.applied("ru", result, ["кефир"], [])
    assert text.splitlines() == [
        "Списал:",
        "• молоко 3.2% — закончилось",
        "Не нашёл в запасах: кефир",
        "Скажи «отмени», если что-то не так.",
    ]


def test_nothing_changed_has_no_hint() -> None:
    assert TEXT.applied("ru", None, ["кефир"], []) == "Не нашёл в запасах: кефир"


def test_undo_outcomes() -> None:
    assert TEXT.undo("en", UndoOutcome.CONFLICT).startswith("Can't undo")
