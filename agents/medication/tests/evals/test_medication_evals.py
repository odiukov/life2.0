"""Real-LLM checks for medication definitions and cross-language resolution. Run with `make evals`."""

from pathlib import Path
from typing import Any

import pytest
import yaml
from medication.application.define import SYSTEM
from medication.application.schemas import MedicationDefinition
from medication.settings import MedicationSettings
from shared.analysis.matching import resolve_name
from shared.ports.llm import LLMTask
from shared.testing.evals import real_llm_or_skip

pytestmark = pytest.mark.evals
CASES: dict[str, list[dict[str, Any]]] = yaml.safe_load(
    (Path(__file__).parent / "cases.yaml").read_text("utf-8")
)


@pytest.fixture(scope="module")
def llm():  # type: ignore[no-untyped-def]
    return real_llm_or_skip(
        MedicationSettings.model_validate(
            {"database": {"dsn": "postgresql://unused@localhost/unused"}}
        )
    )


def _contains(value: str | None, needles: list[str]) -> bool:
    return value is not None and any(n.lower() in value.lower() for n in needles)


@pytest.mark.parametrize("case", CASES["define"], ids=[c["text"][:40] for c in CASES["define"]])
async def test_define(case: dict[str, Any], llm) -> None:  # type: ignore[no-untyped-def]
    got = await llm.structured(
        task=LLMTask.FAST, system=SYSTEM, user=case["text"], schema=MedicationDefinition
    )
    expect = case["expect"]
    if "name" in expect:
        assert got.name == expect["name"], got
    if "name_any" in expect:
        assert got.name in expect["name_any"], got
    if "dose_any" in expect:
        assert _contains(got.dose, expect["dose_any"]), got
    if "schedule_any" in expect:
        assert _contains(got.schedule, expect["schedule_any"]), got
    if "notes_or_schedule_any" in expect:
        assert _contains(f"{got.notes or ''} {got.schedule}", expect["notes_or_schedule_any"]), got


@pytest.mark.parametrize("case", CASES["resolve"], ids=[c["text"][:40] for c in CASES["resolve"]])
async def test_resolve(case: dict[str, Any], llm) -> None:  # type: ignore[no-untyped-def]
    assert await resolve_name(case["text"], case["names"], llm=llm) == case["expect"]
