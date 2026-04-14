import asyncio
import logging
import os

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)


def start_scheduler() -> None:
    hour = int(os.environ.get("SYNC_HOUR", "6"))
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        _run_daily_sync,
        CronTrigger(hour=hour, minute=0),
        id="daily_sync",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(f"Scheduler started: daily sync at {hour:02d}:00 UTC")


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
