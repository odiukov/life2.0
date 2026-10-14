"""Real-LLM checks for log_workout extraction. Run with `make evals`."""

from pathlib import Path
from typing import Any

import pytest
import yaml
from shared.ports.llm import LLMTask
from shared.testing.evals import real_llm_or_skip
from workout.application.log_workout import SYSTEM
from workout.application.schemas import WorkoutExtraction
from workout.settings import WorkoutSettings

pytestmark = pytest.mark.evals
CASES: list[dict[str, Any]] = yaml.safe_load(
    (Path(__file__).parent / "cases.yaml").read_text("utf-8")
)


@pytest.fixture(scope="module")
def llm():  # type: ignore[no-untyped-def]
    return real_llm_or_skip(
        WorkoutSettings.model_validate(
            {"database": {"dsn": "postgresql://unused@localhost/unused"}}
        )
    )


@pytest.mark.parametrize("case", CASES, ids=[c["text"][:40] for c in CASES])
async def test_case(case: dict[str, Any], llm) -> None:  # type: ignore[no-untyped-def]
    got = await llm.structured(
        task=LLMTask.FAST, system=SYSTEM, user=case["text"], schema=WorkoutExtraction
    )
    expect = case["expect"]
    if expect.get("not_a_workout"):
        assert got.name == "none"
        return
    for key in ("activity_type", "duration_minutes", "effort", "started_at"):
        if key in expect:
            assert getattr(got, key) == expect[key], (key, got)
    if "distance_km" in expect:
        assert got.distance_km is not None
        assert abs(got.distance_km - expect["distance_km"]) < 0.01
