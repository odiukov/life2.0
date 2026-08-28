import pytest
from unittest.mock import AsyncMock, patch
from uuid import UUID

_TEST_USER_ID = UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")


@pytest.mark.asyncio
async def test_fetch_body_logs_filters_by_type():
    from shared.db import fetch_body_logs

    fake_pool = AsyncMock()
    fake_pool.fetch.return_value = [
        {"type": "body_composition", "data": {"weight_kg": 79.6},
         "recorded_at": "2026-04-14", "source": "vihealth"},
    ]

    with patch("shared.db.get_pool", new=AsyncMock(return_value=fake_pool)):
        rows = await fetch_body_logs(_TEST_USER_ID, limit=5)

    assert len(rows) == 1
    assert rows[0]["data"]["weight_kg"] == 79.6
    call_sql = fake_pool.fetch.call_args.args[0]
    assert "user_id = $1" in call_sql
    assert "body_composition" in call_sql or fake_pool.fetch.call_args.args[2] == "body_composition"
