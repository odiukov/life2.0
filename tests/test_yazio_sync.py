import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport
import sync_service.app.sync  # pre-import so patch() resolves the module

MOCK_YAZIO_DATA = {
    "diary": [
        ("2026-04-12", [
            {"meal_type": 0, "food": {"name": "Oatmeal", "amount": 80,
             "energy_kcal": 296, "protein": 10.4, "carbohydrates": 48.0, "fat": 5.6}},
            {"meal_type": 1, "food": {"name": "Chicken breast", "amount": 200,
             "energy_kcal": 220, "protein": 41.0, "carbohydrates": 0.0, "fat": 4.8}},
        ]),
    ],
    "errors": [],
}


@pytest.mark.asyncio
async def test_do_nutrition_sync_returns_counts():
    with patch("sync_service.app.sync.fetch_diary", new=AsyncMock(return_value=MOCK_YAZIO_DATA)):
        with patch("sync_service.app.sync.insert_rows", new=AsyncMock(return_value=(2, 0))):
            from sync_service.app.sync import do_nutrition_sync
            result = await do_nutrition_sync(days=1)

    assert result["synced"] == 2
    assert result["skipped"] == 0
    assert result["errors"] == []


@pytest.mark.asyncio
async def test_do_nutrition_sync_propagates_yazio_errors():
    data_with_error = {"diary": [], "errors": ["diary 2026-04-12: timeout"]}
    with patch("sync_service.app.sync.fetch_diary", new=AsyncMock(return_value=data_with_error)):
        with patch("sync_service.app.sync.insert_rows", new=AsyncMock(return_value=(0, 0))):
            from sync_service.app.sync import do_nutrition_sync
            result = await do_nutrition_sync(days=1)

    assert len(result["errors"]) == 1
    assert "diary 2026-04-12" in result["errors"][0]


@pytest.mark.asyncio
async def test_nutrition_sync_endpoint_returns_counts():
    with patch("sync_service.app.sync.fetch_diary", new=AsyncMock(return_value=MOCK_YAZIO_DATA)):
        with patch("sync_service.app.sync.insert_rows", new=AsyncMock(return_value=(2, 0))):
            from sync_service.app.main import app
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post("/sync/nutrition")

    assert resp.status_code == 200
    body = resp.json()
    assert body["synced"] == 2
    assert body["skipped"] == 0


@pytest.mark.asyncio
async def test_nutrition_sync_endpoint_dedup():
    with patch("sync_service.app.sync.fetch_diary", new=AsyncMock(return_value=MOCK_YAZIO_DATA)):
        with patch("sync_service.app.sync.insert_rows", new=AsyncMock(return_value=(0, 2))):
            from sync_service.app.main import app
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post("/sync/nutrition")

    assert resp.json()["skipped"] == 2
