from .garmin import fetch_all
from .mapper import map_sleep, map_activity, map_daily_stats
from .db import insert_rows
from .yazio import fetch_diary
from .yazio_mapper import map_diary_day


async def do_sync(days: int = 7) -> dict:
    """Fetch all Garmin data, map to health_logs rows, insert with dedup.
    Returns {"synced": int, "skipped": int, "errors": list[str]}.
    """
    raw = await fetch_all(days)
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

    try:
        inserted, skipped = await insert_rows(rows)
    except Exception as e:
        errors.append(f"db: {e}")
        inserted, skipped = 0, 0

    return {"synced": inserted, "skipped": skipped, "errors": errors}


async def do_nutrition_sync(days: int = 1) -> dict:
    """Fetch Yazio diary data, map to health_logs rows, insert with dedup.
    Returns {"synced": int, "skipped": int, "errors": list[str]}.
    """
    raw = await fetch_diary(days)
    rows: list[dict] = []
    errors: list[str] = list(raw["errors"])

    for date_str, entries in raw["diary"]:
        rows.extend(map_diary_day(date_str, entries))

    try:
        inserted, skipped = await insert_rows(rows)
    except Exception as e:
        errors.append(f"db: {e}")
        inserted, skipped = 0, 0

    return {"synced": inserted, "skipped": skipped, "errors": errors}
