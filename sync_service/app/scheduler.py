import asyncio
import logging
import os

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)


def start_scheduler() -> None:
    scheduler = AsyncIOScheduler()

    # Mac/Docker Desktop pauses containers when the laptop sleeps. Without a
    # generous misfire_grace_time, APScheduler silently drops runs that came due
    # while paused (default grace is 1 second). 6h covers an overnight sleep.
    grace_seconds = 6 * 3600

    utc_hour = int(os.environ.get("SYNC_HOUR", "6"))
    scheduler.add_job(
        _run_daily_sync,
        CronTrigger(hour=utc_hour, minute=0),
        id="daily_sync_utc",
        replace_existing=True,
        misfire_grace_time=grace_seconds,
        coalesce=True,
    )

    local_hour = int(os.environ.get("BRIEFING_LOCAL_HOUR", "9"))
    local_tz = os.environ.get("BRIEFING_TZ", "Europe/Lisbon")
    scheduler.add_job(
        _run_daily_sync,
        CronTrigger(hour=local_hour, minute=0, timezone=local_tz),
        id="daily_sync_local",
        replace_existing=True,
        misfire_grace_time=grace_seconds,
        coalesce=True,
    )

    scheduler.start()
    logger.info(
        f"Scheduler started: daily sync at {utc_hour:02d}:00 UTC and {local_hour:02d}:00 {local_tz}"
    )


async def _run_daily_sync() -> None:
    from .sync import do_sync, do_nutrition_sync  # late import to avoid circular at module load

    try:
        result = await do_sync()
        logger.info(f"Daily Garmin sync complete: {result}")
    except Exception as e:
        logger.error(f"Daily Garmin sync failed: {e}")

    try:
        result = await do_nutrition_sync()
        logger.info(f"Daily Yazio sync complete: {result}")
    except Exception as e:
        logger.error(f"Daily Yazio sync failed: {e}")

    # Fire briefing after sync completes — fire-and-forget via create_task so sync
    # does not block waiting for the briefing (which includes a Claude call).
    # The task runs on the same event loop and survives until _trigger_briefing completes.
    orchestrator_url = os.environ.get("ORCHESTRATOR_URL", "http://orchestrator:8000")
    asyncio.create_task(_trigger_briefing(orchestrator_url))


async def _trigger_briefing(orchestrator_url: str) -> None:
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            resp = await client.post(f"{orchestrator_url}/briefing")
            logger.info(f"Daily briefing triggered: {resp.json()}")
    except Exception as e:
        logger.warning(f"Daily briefing trigger failed: {e}")
