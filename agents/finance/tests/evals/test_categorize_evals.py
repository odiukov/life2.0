"""Real-LLM categorization check. Run with `make evals`."""

from pathlib import Path
from uuid import uuid4

import pytest
import yaml
from finance.application.categorize import Categorizer
from finance.domain.categories import desc_key
from finance.settings import FinanceSettings
from finance.testing import InMemoryCategoryCache, InMemoryTransactions, in_memory_uow
from shared.testing.evals import real_llm_or_skip

pytestmark = pytest.mark.evals
CASES = yaml.safe_load((Path(__file__).parent / "categorize_cases.yaml").read_text("utf-8"))


async def test_categories_match_at_least_nine_of_ten() -> None:
    settings = FinanceSettings.model_validate(
        {"database": {"dsn": "postgresql://unused@localhost/unused"}}
    )
    llm = real_llm_or_skip(settings)
    cache = InMemoryCategoryCache()
    user = uuid4()
    await Categorizer(llm=llm, uow=in_memory_uow(InMemoryTransactions(), cache))(
        user, {str(i): c["description"] for i, c in enumerate(CASES)}
    )
    hits = sum(cache.rows[user].get(desc_key(c["description"])) == c["category"] for c in CASES)
    assert hits >= 9, cache.rows[user]
