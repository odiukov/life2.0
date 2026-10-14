"""Real-LLM checks for log_meal. Run with `make evals`; needs the provider key in the env."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
import yaml
from nutrition.application.log_meal import LogMeal
from nutrition.settings import NutritionSettings
from nutrition.testing import InMemoryBodyMetrics, InMemoryMeals, InMemoryProfiles, in_memory_uow
from shared.a2a.request import SkillRequest
from shared.adapters.i18n import JsonTranslator
from shared.adapters.llm.build import build_llm_provider
from shared.ports.llm import LLMTask
from shared.testing.fakes import FixedClock, InMemoryVectorMemory

pytestmark = pytest.mark.evals

CASES: list[dict[str, Any]] = yaml.safe_load(
    (Path(__file__).parent / "log_meal_cases.yaml").read_text("utf-8")
)
NOW = datetime(2026, 10, 13, 20, 30, tzinfo=UTC)  # 21:30 in Lisbon
KEYS = {
    "anthropic": "anthropic_api_key",
    "openrouter": "openrouter_api_key",
    "gemini": "gemini_api_key",
    "groq": "groq_api_key",
}


@pytest.fixture(scope="module")
def settings() -> NutritionSettings:
    settings = NutritionSettings.model_validate(
        {"database": {"dsn": "postgresql://unused@localhost/unused"}}
    )
    provider = settings.llm.route(LLMTask.FAST).provider
    if provider == "fake":
        pytest.skip("Real-provider evals do not run against the fake provider")
    if provider in KEYS:
        secret = getattr(settings, KEYS[provider])
        value = secret.get_secret_value().strip() if secret is not None else ""
        if not value or value == "test-placeholder":
            pytest.skip(f"{KEYS[provider].upper()} needs a real key; absent or test-placeholder")
    return settings


@pytest.mark.parametrize("case", CASES, ids=[c["text"][:40] for c in CASES])
async def test_log_meal_case(case: dict[str, Any], settings: NutritionSettings) -> None:
    meals, profiles = InMemoryMeals(), InMemoryProfiles()
    user = uuid4()
    profiles.seed(user, timezone="Europe/Lisbon")
    handler = LogMeal(
        llm=build_llm_provider(settings),
        uow=in_memory_uow(meals, profiles, InMemoryBodyMetrics()),
        clock=FixedClock(NOW),
        translator=JsonTranslator.from_dir(settings.i18n_locales_dir),
        memory=InMemoryVectorMemory(),
        default_locale="ru",
    )
    request = SkillRequest(
        task_id=str(uuid4()),
        context_id="eval",
        text=case["text"],
        user_id=user,
        skill_id="log_meal",
        for_date=None,
        is_peer_call=False,
        params={},
    )
    result = await handler(request, ())
    assert not result.failed, "Provider failed; this case did not produce a valid extraction"
    stored = meals.rows.get(user, [])
    items = [i for m in stored for i in m.items]
    kcal = sum(m.totals.kcal for m in stored)
    assert len(items) >= case["min_items"]
    if "max_items" in case:
        assert len(items) <= case["max_items"]
    low, high = case["kcal"]
    assert low <= kcal <= high, f"{kcal=} outside [{low}, {high}]"
    if "local_time" in case:
        local = stored[0].recorded_at.astimezone(ZoneInfo("Europe/Lisbon"))
        assert f"{local:%H:%M}" == case["local_time"]
