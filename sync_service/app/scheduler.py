import logging
import os

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)


from opentelemetry import trace as _otel_trace
from shared.telemetry import set_span_user

_job_tracer = _otel_trace.get_tracer("sync.scheduler")


def traced_job(name: str):
    """Wrap an APScheduler-scheduled async function in a root span."""
    def deco(fn):
        async def wrapped(*a, **kw):
            with _job_tracer.start_as_current_span(f"sync.{name}") as span:
                span.set_attribute("job.name", name)
                set_span_user()
                return await fn(*a, **kw)
        wrapped.__name__ = fn.__name__
        wrapped.__doc__ = fn.__doc__
        return wrapped
    return deco


def start_scheduler() -> None:
    scheduler = AsyncIOScheduler()

    # Mac/Docker Desktop pauses containers when the laptop sleeps. Without a
    # generous misfire_grace_time, APScheduler silently drops runs that came due
    # while paused (default grace is 1 second). 6h covers an overnight sleep.
    grace_seconds = 6 * 3600

    local_hour = int(os.environ.get("DAILY_SYNC_HOUR", "9"))
    local_tz = os.environ.get("DAILY_SYNC_TZ", "Europe/Lisbon")
    scheduler.add_job(
        run_daily_sync,
        CronTrigger(hour=local_hour, minute=0, timezone=local_tz),
        id="daily_sync_local",
        replace_existing=True,
        misfire_grace_time=grace_seconds,
        coalesce=True,
    )

    scheduler.start()
    logger.info(
        f"Scheduler started: daily sync at {local_hour:02d}:00 {local_tz}"
    )


@traced_job("daily_sync")
async def run_daily_sync() -> dict:
    from .sync import do_sync, do_nutrition_sync  # late import to avoid circular at module load

    garmin: dict | None = None
    yazio: dict | None = None
    errors: list[str] = []

    try:
        garmin = await do_sync()
        logger.info(f"Daily Garmin sync complete: {garmin}")
    except Exception as e:
        logger.error(f"Daily Garmin sync failed: {e}")
        errors.append(f"garmin: {e}")

    try:
        yazio = await do_nutrition_sync()
        logger.info(f"Daily Yazio sync complete: {yazio}")
    except Exception as e:
        logger.error(f"Daily Yazio sync failed: {e}")
        errors.append(f"yazio: {e}")

    return {"garmin": garmin, "yazio": yazio, "errors": errors}
