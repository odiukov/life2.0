# sync_service/app/yazio.py
import asyncio
import os
from datetime import date, timedelta

import httpx

BASE_URL = "https://api2.yazio.com"


def _get_dates(days: int) -> list[str]:
    """Return ISO date strings for the last N days, ending yesterday."""
    # Anchor at yesterday: daily cron fires at 06:00 UTC to pull the previous day's diary.
    yesterday = date.today() - timedelta(days=1)
    return [(yesterday - timedelta(days=i)).isoformat() for i in range(days)]


def _fetch_sync(days: int) -> dict:
    """Synchronous Yazio fetch — called via asyncio.to_thread."""
    email = os.environ["YAZIO_EMAIL"]
    password = os.environ["YAZIO_PASSWORD"]

    with httpx.Client(base_url=BASE_URL, timeout=15.0) as client:
        # Authenticate
        auth_resp = client.post(
            "/auth/token",
            json={"email": email, "password": password, "grant_type": "password"},
        )
        auth_resp.raise_for_status()
        data = auth_resp.json()
        token = data.get("access_token")
        if not token:
            raise ValueError(f"Yazio auth response missing access_token: {data}")
        headers = {"Authorization": f"Bearer {token}"}

        dates = _get_dates(days)
        diary: list[tuple[str, list]] = []
        errors: list[str] = []

        for d in dates:
            try:
                resp = client.get(
                    "/v7/user/consumed-food",
                    params={"date": d},
                    headers=headers,
                )
                resp.raise_for_status()
                entries = resp.json().get("entries", [])
                diary.append((d, entries))
            except Exception as e:
                errors.append(f"diary {d}: {e}")

    return {"diary": diary, "errors": errors}


async def fetch_diary(days: int = 1) -> dict:
    """Async wrapper: runs the blocking Yazio client in a thread pool."""
    return await asyncio.to_thread(_fetch_sync, days)
