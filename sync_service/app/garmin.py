import asyncio
import logging
from datetime import date, timedelta

from garminconnect import Garmin

logger = logging.getLogger(__name__)


def _get_dates(days: int = 7) -> list[str]:
    """Return ISO date strings for the last N days, newest first."""
    today = date.today()
    return [(today - timedelta(days=i)).isoformat() for i in range(days)]


def _fetch_sync(days: int, email: str, password: str, token_in: str | None = None) -> tuple[dict, str]:
    """Synchronous Garmin fetch — called via asyncio.to_thread."""
    client = Garmin(email, password)
    client.login(tokenstore=token_in)

    dates = _get_dates(days)
    sleep_data: list[tuple[str, dict]] = []
    activities: list[dict] = []
    daily_stats: list[tuple[str, dict]] = []
    hrv_data: list[tuple[str, dict]] = []
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

    for d in dates:
        try:
            hrv_data.append((d, client.get_hrv_data(d)))
        except Exception as e:
            errors.append(f"hrv {d}: {e}")

    try:
        token_out = client.client.dumps()
    except Exception as e:
        logger.warning("Failed to serialize garmin token: %s", e)
        token_out = ""
    return {
        "sleep": sleep_data,
        "activities": activities,
        "daily_stats": daily_stats,
        "hrv": hrv_data,
        "errors": errors,
    }, token_out


async def fetch_all(days: int, email: str, password: str, token_in: str | None = None) -> tuple[dict, str]:
    """Async wrapper: runs the blocking Garmin client in a thread pool."""
    return await asyncio.to_thread(_fetch_sync, days, email, password, token_in)


def _validate_sync(email: str, password: str) -> None:
    Garmin(email, password).login()


async def validate_credentials(email: str, password: str) -> None:
    """Verify Garmin credentials by performing a fresh login.

    Raises GarminConnectAuthenticationError on bad credentials,
    GarminConnectConnectionError on transport problems. Returns None on
    success. No tokens are persisted.
    """
    await asyncio.to_thread(_validate_sync, email, password)
