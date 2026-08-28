import logging

from . import session
from .garmin import fetch_all
from .mapper import map_sleep, map_activity, map_daily_stats, map_hrv
from .db import insert_rows, list_user_credentials
from .yazio import fetch_diary
from .yazio_mapper import map_diary_day
from .apple_health import map_body_composition

logger = logging.getLogger(__name__)


async def do_sync(days: int = 7) -> dict:
    """Fetch Garmin data for all users with garmin credentials, insert with dedup.

    Returns {"synced": int, "skipped": int, "errors": list[str]}.
    """
    user_creds = await list_user_credentials("garmin")

    total_synced = 0
    total_skipped = 0
    all_errors: list[str] = []

    for user_id, creds in user_creds:
        token_in = await session.get_garmin_token(user_id)
        raw, token_out = await fetch_all(days, email=creds["email"], password=creds["password"], token_in=token_in)
        if token_out:
            await session.save_garmin_token(user_id, token_out)

        rows: list[dict] = []
        errors: list[str] = list(raw["errors"])

        for date_str, sleep_raw in raw["sleep"]:
            row = map_sleep(date_str, sleep_raw)
            if row:
                rows.append(row)

        for activity_raw in raw["activities"]:
            row = map_activity(activity_raw)
            if row:
                rows.append(row)

        for date_str, stats_raw in raw["daily_stats"]:
            row = map_daily_stats(date_str, stats_raw)
            if row:
                rows.append(row)

        for date_str, hrv_raw in raw.get("hrv", []):
            row = map_hrv(date_str, hrv_raw)
            if row:
                rows.append(row)

        try:
            inserted, skipped = await insert_rows(rows, user_id=user_id)
            total_synced += inserted
            total_skipped += skipped
        except Exception as e:
            errors.append(f"db: {e}")

        if errors:
            all_errors.extend(f"[{user_id}] {e}" for e in errors)

    return {"synced": total_synced, "skipped": total_skipped, "errors": all_errors}


async def do_body_sync(payload: dict) -> dict:
    """Accept Apple Health body composition payload, map and store.

    The caller (orchestrator) passes user_id resolved from the auth header.
    Returns {"synced": int, "skipped": int, "errors": list[str]}.
    """
    rows = map_body_composition(payload)
    errors: list[str] = []

    if not rows:
        return {"synced": 0, "skipped": 0, "errors": ["no recognized metrics in payload"]}

    user_id = payload.get("user_id")
    try:
        inserted, skipped = await insert_rows(rows, user_id=user_id)
    except Exception as e:
        errors.append(f"db: {e}")
        inserted, skipped = 0, 0

    return {"synced": inserted, "skipped": skipped, "errors": errors}


async def do_nutrition_sync(days: int = 2) -> dict:
    """Fetch Yazio diary for all users with yazio credentials, insert with dedup.

    Returns {"synced": int, "skipped": int, "errors": list[str]}.
    """
    user_creds = await list_user_credentials("yazio")

    total_synced = 0
    total_skipped = 0
    all_errors: list[str] = []

    for user_id, creds in user_creds:
        token_in = await session.get_yazio_token(user_id)
        raw, token_out = await fetch_diary(days, email=creds["email"], password=creds["password"], token_in=token_in)
        await session.save_yazio_token(user_id, token_out)

        rows: list[dict] = []
        errors: list[str] = list(raw["errors"])

        for date_str, entries in raw["diary"]:
            rows.extend(map_diary_day(date_str, entries))

        try:
            inserted, skipped = await insert_rows(rows, user_id=user_id)
            total_synced += inserted
            total_skipped += skipped
        except Exception as e:
            errors.append(f"db: {e}")

        if errors:
            all_errors.extend(f"[{user_id}] {e}" for e in errors)

    return {"synced": total_synced, "skipped": total_skipped, "errors": all_errors}
