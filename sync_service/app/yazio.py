import asyncio
import logging
import os
from datetime import date, datetime, timedelta, timezone

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://yzapi.yazio.com/v18"
# Yazio's mobile OAuth client. Yazio has no public API programme, so these are
# the app's own client credentials — supply your own via the environment.
CLIENT_ID = os.environ.get("YAZIO_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("YAZIO_CLIENT_SECRET", "")
USER_AGENT = "YAZIO/12.31.0 (com.yazio.android; build:411052340; Android 34) Ktor"

_DAYTIME_TO_INT = {"breakfast": 0, "lunch": 1, "dinner": 2, "snack": 3}


def _get_dates(days: int) -> list[str]:
    today = date.today()
    return [(today - timedelta(days=i)).isoformat() for i in range(days)]


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


async def validate_credentials(email: str, password: str) -> None:
    """Verify Yazio credentials by performing an OAuth password grant.

    Raises httpx.HTTPStatusError when Yazio rejects the credentials (4xx),
    httpx.HTTPError on transport problems, or ValueError on a malformed
    response. Returns None on success. No tokens are persisted.
    """
    headers_base = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    async with httpx.AsyncClient(base_url=BASE_URL, headers=headers_base, timeout=15.0) as client:
        auth = await client.post(
            "/oauth/token",
            json={
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "grant_type": "password",
                "username": email,
                "password": password,
            },
        )
        auth.raise_for_status()
        if not auth.json().get("access_token"):
            raise ValueError("Yazio auth response missing access_token")


def is_yazio_token_valid(token: dict) -> bool:
    """True if token has more than 5 minutes of lifetime remaining."""
    expires_at = token.get("expires_at")
    if not expires_at:
        return False
    try:
        exp = datetime.fromisoformat(expires_at)
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return (exp - datetime.now(timezone.utc)).total_seconds() > 300
    except Exception:
        return False


def _build_token_out(auth_json: dict) -> dict:
    expires_in = auth_json.get("expires_in", 3600)
    return {
        "access_token": auth_json.get("access_token", ""),
        "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat(),
        "refresh_token": auth_json.get("refresh_token"),
    }


async def fetch_diary(
    days: int,
    email: str,
    password: str,
    token_in: dict | None = None,
) -> tuple[dict, dict]:
    """Fetch the last N days' Yazio diary, enriched with product nutrients.

    Returns ({"diary": [...], "errors": [...]}, token_out).
    """
    headers_base = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    errors: list[str] = []
    diary_out: list[tuple[str, list]] = []
    token_out: dict = {}

    async with httpx.AsyncClient(base_url=BASE_URL, headers=headers_base, timeout=20.0) as client:
        if token_in and is_yazio_token_valid(token_in):
            auth_h = {"Authorization": f"Bearer {token_in['access_token']}"}
            token_out = token_in
        else:
            authenticated = False
            if token_in and token_in.get("refresh_token"):
                try:
                    auth = await client.post("/oauth/token", json={
                        "client_id": CLIENT_ID,
                        "client_secret": CLIENT_SECRET,
                        "grant_type": "refresh_token",
                        "refresh_token": token_in["refresh_token"],
                    })
                    auth.raise_for_status()
                    token_out = _build_token_out(auth.json())
                    auth_h = {"Authorization": f"Bearer {token_out['access_token']}"}
                    authenticated = True
                except Exception as e:
                    logger.warning("Yazio refresh_token failed, falling back to password grant: %s", e)

            if not authenticated:
                auth = await client.post("/oauth/token", json={
                    "client_id": CLIENT_ID,
                    "client_secret": CLIENT_SECRET,
                    "grant_type": "password",
                    "username": email,
                    "password": password,
                })
                auth.raise_for_status()
                token_out = _build_token_out(auth.json())
                if not token_out.get("access_token"):
                    raise ValueError(f"Yazio auth response missing access_token: {auth.json()}")
                auth_h = {"Authorization": f"Bearer {token_out['access_token']}"}

        product_cache: dict[str, dict] = {}
        recipe_cache: dict[str, dict] = {}
        for d in _get_dates(days):
            try:
                entries = await _fetch_day(client, auth_h, d, product_cache, recipe_cache, errors)
                diary_out.append((d, entries))
            except Exception as e:
                errors.append(f"diary {d}: {e}")

    return {"diary": diary_out, "errors": errors}, token_out
