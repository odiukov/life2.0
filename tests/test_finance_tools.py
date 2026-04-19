"""Unit tests for the finance ReAct tools.

Tools are thin wrappers around finance_queries; tests patch the queries
module to avoid hitting the DB.
"""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.asyncio


async def test_query_finance_summary_formats_per_currency():
    from orchestrator.app.health_agent import query_finance_summary
    with patch(
        "orchestrator.app.finance_queries.income_for_month",
        new=AsyncMock(return_value={"USD": Decimal("2500.00")}),
    ), patch(
        "orchestrator.app.finance_queries.spending_by_category",
        new=AsyncMock(return_value=[("food", "USD", Decimal("340.00"))]),
    ):
        result = await query_finance_summary.ainvoke({"month": "2026-04"})
    assert "2026-04" in result or "апрель" in result.lower()
    assert "2500" in result
    assert "food" in result or "340" in result


async def test_query_finance_categories_lists_top():
    from orchestrator.app.health_agent import query_finance_categories
    with patch(
        "orchestrator.app.finance_queries.spending_by_category",
        new=AsyncMock(return_value=[
            ("software", "USD", Decimal("420")),
            ("food", "USD", Decimal("340")),
            ("transport", "USD", Decimal("120")),
        ]),
    ):
        result = await query_finance_categories.ainvoke({"month": "2026-04"})
    assert "software" in result and "food" in result and "transport" in result


async def test_query_finance_runway_mentions_days():
    from orchestrator.app.health_agent import query_finance_runway
    with patch(
        "orchestrator.app.finance_queries.runway",
        new=AsyncMock(return_value={
            "USD": {"balance": Decimal("680.00"),
                    "avg_daily_burn": Decimal("92.00"),
                    "days": 7},
        }),
    ):
        result = await query_finance_runway.ainvoke({})
    assert "7" in result
    assert "680" in result or "92" in result
