import asyncio
import os
from datetime import date, timedelta

from garminconnect import Garmin


def _get_dates(days: int = 7) -> list[str]:
    """Return ISO date strings for the last N days, newest first."""
    today = date.today()
    return [(today - timedelta(days=i)).isoformat() for i in range(days)]


def _fetch_sync(days: int) -> dict:
    """Synchronous Garmin fetch — called via asyncio.to_thread."""
    client = Garmin(os.environ["GARMIN_EMAIL"], os.environ["GARMIN_PASSWORD"])
    client.login()

    dates = _get_dates(days)
    sleep_data: list[tuple[str, dict]] = []
    activities: list[dict] = []
    daily_stats: list[tuple[str, dict]] = []
    errors: list[str] = []

    for d in dates:
        try:
            sleep_data.append((d, client.get_sleep_data(d)))
        except Exception as e:
            errors.append(f"sleep {d}: {e}")

    try:
        # Activities: single range call, newest-first dates so [-1] is oldest
        activities = client.get_activities_by_date(dates[-1], dates[0])
    except Exception as e:
        errors.append(f"activities: {e}")

    for d in dates:
        try:
            daily_stats.append((d, client.get_stats(d)))
        except Exception as e:
            errors.append(f"daily_stats {d}: {e}")

    return {
        "sleep": sleep_data,
        "activities": activities,
        "daily_stats": daily_stats,
        "errors": errors,
    }


async def fetch_all(days: int = 7) -> dict:
    """Async wrapper: runs the blocking Garmin client in a thread pool."""
    return await asyncio.to_thread(_fetch_sync, days)
