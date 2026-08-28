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
    with patch("sync_service.app.sync.list_user_credentials", new=AsyncMock(return_value=[("user-1", {"email": "a@b.com", "password": "p"})])):
        with patch("sync_service.app.sync.fetch_diary", new=AsyncMock(return_value=(MOCK_YAZIO_DATA, {"access_token": "tok", "expires_at": "2099-01-01T00:00:00+00:00"}))):
            with patch("sync_service.app.sync.insert_rows", new=AsyncMock(return_value=(2, 0))):
                with patch("sync_service.app.sync.session.get_yazio_token", new=AsyncMock(return_value=None)):
                    with patch("sync_service.app.sync.session.save_yazio_token", new=AsyncMock()):
                        from sync_service.app.sync import do_nutrition_sync
                        result = await do_nutrition_sync(days=1)

    assert result["synced"] == 2
    assert result["skipped"] == 0
    assert result["errors"] == []


@pytest.mark.asyncio
async def test_do_nutrition_sync_propagates_yazio_errors():
    data_with_error = {"diary": [], "errors": ["diary 2026-04-12: timeout"]}
    with patch("sync_service.app.sync.list_user_credentials", new=AsyncMock(return_value=[("user-1", {"email": "a@b.com", "password": "p"})])):
        with patch("sync_service.app.sync.fetch_diary", new=AsyncMock(return_value=(data_with_error, {"access_token": "tok", "expires_at": "2099-01-01T00:00:00+00:00"}))):
            with patch("sync_service.app.sync.insert_rows", new=AsyncMock(return_value=(0, 0))):
                with patch("sync_service.app.sync.session.get_yazio_token", new=AsyncMock(return_value=None)):
                    with patch("sync_service.app.sync.session.save_yazio_token", new=AsyncMock()):
                        from sync_service.app.sync import do_nutrition_sync
                        result = await do_nutrition_sync(days=1)

    assert len(result["errors"]) == 1
    assert "diary 2026-04-12" in result["errors"][0]


@pytest.mark.asyncio
async def test_nutrition_sync_endpoint_returns_counts():
    with patch("sync_service.app.sync.list_user_credentials", new=AsyncMock(return_value=[("user-1", {"email": "a@b.com", "password": "p"})])):
        with patch("sync_service.app.sync.fetch_diary", new=AsyncMock(return_value=(MOCK_YAZIO_DATA, {"access_token": "tok", "expires_at": "2099-01-01T00:00:00+00:00"}))):
            with patch("sync_service.app.sync.insert_rows", new=AsyncMock(return_value=(2, 0))):
                with patch("sync_service.app.sync.session.get_yazio_token", new=AsyncMock(return_value=None)):
                    with patch("sync_service.app.sync.session.save_yazio_token", new=AsyncMock()):
                        from sync_service.app.main import app
                        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                            resp = await client.post("/sync/nutrition")

    assert resp.status_code == 200
    body = resp.json()
    assert body["synced"] == 2
    assert body["skipped"] == 0


@pytest.mark.asyncio
async def test_nutrition_sync_endpoint_dedup():
    with patch("sync_service.app.sync.list_user_credentials", new=AsyncMock(return_value=[("user-1", {"email": "a@b.com", "password": "p"})])):
        with patch("sync_service.app.sync.fetch_diary", new=AsyncMock(return_value=(MOCK_YAZIO_DATA, {"access_token": "tok", "expires_at": "2099-01-01T00:00:00+00:00"}))):
            with patch("sync_service.app.sync.insert_rows", new=AsyncMock(return_value=(0, 2))):
                with patch("sync_service.app.sync.session.get_yazio_token", new=AsyncMock(return_value=None)):
                    with patch("sync_service.app.sync.session.save_yazio_token", new=AsyncMock()):
                        from sync_service.app.main import app
                        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                            resp = await client.post("/sync/nutrition")

    assert resp.json()["skipped"] == 2


def test_enrich_simple_product_reads_absolute_nutrients():
    """simple_products carry totals at entry['nutrients'][...]. AI-generated meals
    have amount=1 with the kcal living entirely on the nutrients dict."""
    from sync_service.app.yazio import _enrich_simple_product

    out = _enrich_simple_product({
        "daytime": "breakfast",
        "name": "Salmon wrap",
        "amount": 1,
        "is_ai_generated": True,
        "nutrients": {
            "energy.energy": 368,
            "nutrient.protein": 27,
            "nutrient.carb": 17,
            "nutrient.fat": 21,
        },
    })

    assert out["meal_type"] == 0
    assert out["food"]["name"] == "Salmon wrap"
    assert out["food"]["energy_kcal"] == 368
    assert out["food"]["protein"] == 27
    assert out["food"]["carbohydrates"] == 17
    assert out["food"]["fat"] == 21


def test_enrich_simple_product_missing_nutrients_returns_zero():
    from sync_service.app.yazio import _enrich_simple_product

    out = _enrich_simple_product({"daytime": "snack", "name": "no-nutrients"})
    assert out["food"]["energy_kcal"] == 0.0
    assert out["food"]["protein"] == 0.0


def test_enrich_recipe_portion_multiplies_per_portion_by_count():
    """Recipe nutrients are per portion; diary entry portion_count scales them."""
    from sync_service.app.yazio import _enrich_recipe_portion

    out = _enrich_recipe_portion(
        {"daytime": "dinner", "portion_count": 2, "recipe_id": "r1"},
        {
            "name": "Banana-peanut muffins",
            "portion_count": 7,  # recipe yields 7; not used for scaling
            "nutrients": {
                "energy.energy": 296.1,
                "nutrient.protein": 13.07,
                "nutrient.carb": 15.97,
                "nutrient.fat": 20.14,
            },
        },
    )

    assert out["meal_type"] == 2
    assert out["food"]["name"] == "Banana-peanut muffins"
    assert out["food"]["amount"] == 2
    assert round(out["food"]["energy_kcal"], 1) == 592.2
    assert round(out["food"]["protein"], 2) == 26.14
    assert round(out["food"]["carbohydrates"], 2) == 31.94
    assert round(out["food"]["fat"], 2) == 40.28


def test_enrich_recipe_portion_defaults_count_to_one():
    from sync_service.app.yazio import _enrich_recipe_portion

    out = _enrich_recipe_portion(
        {"daytime": "lunch"},
        {"name": "X", "nutrients": {"energy.energy": 100}},
    )
    assert out["food"]["energy_kcal"] == 100
