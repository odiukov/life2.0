"""Real-LLM checks for habit definitions and cross-language name resolution. Run with `make evals`."""

from pathlib import Path
from typing import Any

import pytest
import yaml
from habits.application.define import SYSTEM
from habits.application.schemas import HabitDefinition
from habits.settings import HabitsSettings
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
        HabitsSettings.model_validate({"database": {"dsn": "postgresql://unused@localhost/unused"}})
    )


@pytest.mark.parametrize("case", CASES["define"], ids=[c["text"][:40] for c in CASES["define"]])
async def test_define(case: dict[str, Any], llm) -> None:  # type: ignore[no-untyped-def]
    got = await llm.structured(
        task=LLMTask.FAST, system=SYSTEM, user=case["text"], schema=HabitDefinition
    )
    expect = case["expect"]
    for key in ("name", "kind", "cadence_type", "cadence_days", "target_value"):
        if key in expect:
            assert getattr(got, key) == expect[key], (key, got)
    if "unit_any" in expect:
        assert got.unit is not None
        assert any(u in got.unit for u in expect["unit_any"])


@pytest.mark.parametrize("case", CASES["resolve"], ids=[c["text"][:40] for c in CASES["resolve"]])
async def test_resolve(case: dict[str, Any], llm) -> None:  # type: ignore[no-untyped-def]
    assert await resolve_name(case["text"], case["names"], llm=llm) == case["expect"]
