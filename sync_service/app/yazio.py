import asyncio
import os
from datetime import date, timedelta

import httpx

BASE_URL = "https://yzapi.yazio.com/v18"
CLIENT_ID = "1_4hiybetvfksgw40o0sog4s884kwc840wwso8go4k8c04goo4c"
CLIENT_SECRET = "6rok2m65xuskgkgogw40wkkk8sw0osg84s8cggsc4woos4s8o"
USER_AGENT = "YAZIO/12.31.0 (com.yazio.android; build:411052340; Android 34) Ktor"

_DAYTIME_TO_INT = {"breakfast": 0, "lunch": 1, "dinner": 2, "snack": 3}


def _get_dates(days: int) -> list[str]:
    yesterday = date.today() - timedelta(days=1)
    return [(yesterday - timedelta(days=i)).isoformat() for i in range(days)]


def _enrich_product(entry: dict, product: dict) -> dict:
    """Build an old-schema entry {meal_type, food{...}} from a consumed-items row + product details.

    Yazio product `nutrients` are expressed per gram; multiply by `amount` (grams)
    to get absolute values for the consumed portion.
    """
    amount = entry.get("amount") or 0
    nutrients = product.get("nutrients") or {}
    return {
        "meal_type": _DAYTIME_TO_INT.get(entry.get("daytime", "snack"), 3),
        "food": {
            "name": product.get("name", ""),
            "amount": amount,
            "energy_kcal": amount * nutrients.get("energy.energy", 0.0),
            "protein": amount * nutrients.get("nutrient.protein", 0.0),
            "carbohydrates": amount * nutrients.get("nutrient.carb", 0.0),
            "fat": amount * nutrients.get("nutrient.fat", 0.0),
        },
    }


def _enrich_simple_product(entry: dict) -> dict:
    """simple_products store absolute nutrients per consumed portion (NOT per gram).

    Used by free-form calorie logs and AI-described meals (`is_ai_generated`).
    Real shape: `nutrients: {"energy.energy": 368, "nutrient.protein": 27, ...}`.
    """
    nutrients = entry.get("nutrients") or {}
    return {
        "meal_type": _DAYTIME_TO_INT.get(entry.get("daytime", "snack"), 3),
        "food": {
            "name": entry.get("name", "simple"),
            "amount": entry.get("amount") or entry.get("serving_quantity") or 1,
            "energy_kcal": nutrients.get("energy.energy", 0.0),
            "protein": nutrients.get("nutrient.protein", 0.0),
            "carbohydrates": nutrients.get("nutrient.carb", 0.0),
            "fat": nutrients.get("nutrient.fat", 0.0),
        },
    }


def _enrich_recipe_portion(entry: dict, recipe: dict) -> dict:
    """Recipe `nutrients` are per portion; multiply by diary `portion_count`."""
    nutrients = recipe.get("nutrients") or {}
    portions = entry.get("portion_count") or 1
    return {
        "meal_type": _DAYTIME_TO_INT.get(entry.get("daytime", "snack"), 3),
        "food": {
            "name": recipe.get("name", "recipe"),
            "amount": portions,
            "energy_kcal": portions * nutrients.get("energy.energy", 0.0),
            "protein": portions * nutrients.get("nutrient.protein", 0.0),
            "carbohydrates": portions * nutrients.get("nutrient.carb", 0.0),
            "fat": portions * nutrients.get("nutrient.fat", 0.0),
        },
    }


async def _fetch_day(
    client: httpx.AsyncClient,
    headers: dict,
    day: str,
    product_cache: dict[str, dict],
    recipe_cache: dict[str, dict],
    errors: list[str],
) -> list[dict]:
    """Fetch one day's diary, enrich products + simple_products + recipes, return old-schema entries."""
    resp = await client.get("/user/consumed-items", params={"date": day}, headers=headers)
    resp.raise_for_status()
    diary = resp.json()

    enriched: list[dict] = []
    for entry in diary.get("products", []) or []:
        pid = entry.get("product_id")
        if not pid:
            continue
        product = product_cache.get(pid)
        if product is None:
            try:
                pr = await client.get(f"/products/{pid}", headers=headers)
                pr.raise_for_status()
                product = pr.json()
                product_cache[pid] = product
            except Exception as e:
                errors.append(f"product {pid}: {e}")
                continue
        enriched.append(_enrich_product(entry, product))

    for entry in diary.get("simple_products", []) or []:
        enriched.append(_enrich_simple_product(entry))

    for entry in diary.get("recipe_portions", []) or []:
        rid = entry.get("recipe_id")
        if not rid:
            continue
        recipe = recipe_cache.get(rid)
        if recipe is None:
            try:
                rr = await client.get(f"/recipes/{rid}", headers=headers)
                rr.raise_for_status()
                recipe = rr.json()
                recipe_cache[rid] = recipe
            except Exception as e:
                errors.append(f"recipe {rid}: {e}")
                continue
        enriched.append(_enrich_recipe_portion(entry, recipe))

    return enriched


async def fetch_diary(days: int = 1) -> dict:
    """Fetch the last N days' Yazio diary, enriched with product nutrients.

    Returns {"diary": [(date_str, entries)], "errors": [str]} where each entry
    matches the old /v7 shape: {meal_type:int, food:{name, amount, energy_kcal, protein, carbohydrates, fat}}.
    """
    email = os.environ["YAZIO_EMAIL"]
    password = os.environ["YAZIO_PASSWORD"]

    headers_base = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    errors: list[str] = []
    diary_out: list[tuple[str, list]] = []

    async with httpx.AsyncClient(base_url=BASE_URL, headers=headers_base, timeout=20.0) as client:
        auth = await client.post("/oauth/token", json={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "grant_type": "password",
            "username": email,
            "password": password,
        })
        auth.raise_for_status()
        token = auth.json().get("access_token")
        if not token:
            raise ValueError(f"Yazio auth response missing access_token: {auth.json()}")
        auth_h = {"Authorization": f"Bearer {token}"}

        product_cache: dict[str, dict] = {}
        recipe_cache: dict[str, dict] = {}
        for d in _get_dates(days):
            try:
                entries = await _fetch_day(client, auth_h, d, product_cache, recipe_cache, errors)
                diary_out.append((d, entries))
            except Exception as e:
                errors.append(f"diary {d}: {e}")

    return {"diary": diary_out, "errors": errors}
