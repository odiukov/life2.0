"""Real-LLM checks for log_sleep extraction. Run with `make evals`."""

from pathlib import Path
from typing import Any

import pytest
import yaml
from shared.ports.llm import LLMTask
from shared.testing.evals import real_llm_or_skip
from sleep.application.log_sleep import SYSTEM
from sleep.application.schemas import SleepExtraction
from sleep.settings import SleepSettings

pytestmark = pytest.mark.evals
CASES: list[dict[str, Any]] = yaml.safe_load(
    (Path(__file__).parent / "cases.yaml").read_text("utf-8")
)


@pytest.fixture(scope="module")
def llm():  # type: ignore[no-untyped-def]
    return real_llm_or_skip(
        SleepSettings.model_validate({"database": {"dsn": "postgresql://unused@localhost/unused"}})
    )


@pytest.mark.parametrize("case", CASES, ids=[c["text"][:40] for c in CASES])
async def test_case(case: dict[str, Any], llm) -> None:  # type: ignore[no-untyped-def]
    got = await llm.structured(
        task=LLMTask.FAST, system=SYSTEM, user=case["text"], schema=SleepExtraction
    )
    expect = case["expect"]
    for key in ("bed_time", "wake_time", "duration_minutes"):
        if key in expect:
            assert getattr(got, key) == expect[key], (key, got)
    if "quality_min" in expect:
        assert got.quality is not None
        assert got.quality >= expect["quality_min"]
    if "quality_max" in expect:
        assert got.quality is not None
        assert got.quality <= expect["quality_max"]
    if expect.get("placeable") is False:
        assert got.duration_minutes is None
        assert not (got.bed_time and got.wake_time)
