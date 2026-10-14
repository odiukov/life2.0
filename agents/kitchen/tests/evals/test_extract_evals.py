"""Real-LLM extraction checks. Run with `make evals`; needs provider credentials."""

from datetime import date
from pathlib import Path
from typing import Any

import pytest
import yaml
from evals.matching import check, inventory_text
from kitchen.application.extract import ExtractionContext, extract_operations
from kitchen.settings import KitchenSettings
from shared.adapters.llm.build import build_llm_provider
from shared.ports.llm import LLMTask

pytestmark = pytest.mark.evals
CASES: list[dict[str, Any]] = yaml.safe_load(
    (Path(__file__).parent / "cases.yaml").read_text(encoding="utf-8")
)
TODAY = date(2026, 10, 13)
KEYS = {
    "anthropic": "anthropic_api_key",
    "openrouter": "openrouter_api_key",
    "gemini": "gemini_api_key",
    "groq": "groq_api_key",
}


@pytest.fixture(scope="module")
def settings() -> KitchenSettings:
    settings = KitchenSettings.model_validate(
        {"database": {"dsn": "postgresql://unused@localhost/unused"}}
    )
    provider = settings.llm.route(LLMTask.KITCHEN_EXTRACT).provider
    if provider == "fake":
        pytest.skip("Real-provider evals do not run against the fake provider")
    if provider in KEYS:
        secret = getattr(settings, KEYS[provider])
        value = secret.get_secret_value().strip() if secret is not None else ""
        if not value or value == "test-placeholder":
            pytest.skip(f"{KEYS[provider].upper()} needs a real key; absent or test-placeholder")
    return settings


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
async def test_extraction_case(case: dict[str, Any], settings: KitchenSettings) -> None:
    ops = await extract_operations(
        build_llm_provider(settings),
        ExtractionContext(
            text=case["text"],
            today=TODAY,
            timezone="Europe/London",
            inventory=inventory_text(case.get("inventory", [])),
            clarification=case.get("clarification"),
        ),
    )
    problems = check(case, ops)
    assert not problems, "\n".join(problems)
