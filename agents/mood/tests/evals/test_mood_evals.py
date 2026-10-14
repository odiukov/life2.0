"""Real-LLM checks for log_mood extraction. Run with `make evals`."""

from pathlib import Path
from typing import Any

import pytest
import yaml
from mood.application.log_mood import SYSTEM
from mood.application.schemas import MoodExtraction
from mood.domain.entry import has_signal
from mood.settings import MoodSettings
from shared.ports.llm import LLMTask
from shared.testing.evals import real_llm_or_skip

pytestmark = pytest.mark.evals
CASES: list[dict[str, Any]] = yaml.safe_load(
    (Path(__file__).parent / "cases.yaml").read_text("utf-8")
)


@pytest.fixture(scope="module")
def llm():  # type: ignore[no-untyped-def]
    return real_llm_or_skip(
        MoodSettings.model_validate({"database": {"dsn": "postgresql://unused@localhost/unused"}})
    )


@pytest.mark.parametrize("case", CASES, ids=[c["text"][:40] for c in CASES])
async def test_case(case: dict[str, Any], llm) -> None:  # type: ignore[no-untyped-def]
    got = await llm.structured(
        task=LLMTask.FAST, system=SYSTEM, user=case["text"], schema=MoodExtraction
    )
    expect = case["expect"]
    if expect.get("no_signal"):
        assert not has_signal(got), got
        return
    for key in ("mood_score", "valence"):
        if key in expect:
            assert getattr(got, key) == expect[key], (key, got)
    for key, bound in (("energy_min", "energy"), ("stress_min", "stress")):
        if key in expect:
            assert (getattr(got, bound) or 0) >= expect[key], (key, got)
    if "energy_max" in expect:
        assert got.energy is not None
        assert got.energy <= expect["energy_max"]
    if "tags_any" in expect:
        assert any(any(word in tag for word in expect["tags_any"]) for tag in got.tags), got.tags
