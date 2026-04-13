import logging
import os

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
    from .sync import do_sync  # late import to avoid circular at module load

    try:
        result = await do_sync()
        logger.info(f"Daily sync complete: {result}")
    except Exception as e:
        logger.error(f"Daily sync failed: {e}")
