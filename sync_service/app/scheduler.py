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

    local_hour = int(os.environ.get("BRIEFING_LOCAL_HOUR", "9"))
    local_tz = os.environ.get("BRIEFING_TZ", "Europe/Lisbon")
    scheduler.add_job(
        run_daily_sync,
        CronTrigger(hour=local_hour, minute=0, timezone=local_tz),
        id="daily_sync_local",
        replace_existing=True,
        misfire_grace_time=grace_seconds,
        coalesce=True,
    )

    if os.environ.get("MOOD_EVENING_CHECKIN", "false").lower() == "true":
        checkin_time = os.environ.get("MOOD_EVENING_CHECKIN_TIME", "21:00")
        checkin_tz = os.environ.get("MOOD_EVENING_CHECKIN_TZ", "Europe/Kyiv")
        try:
            hh, mm = (int(x) for x in checkin_time.split(":", 1))
        except ValueError:
            hh, mm = 21, 0
        scheduler.add_job(
            _send_mood_checkin,
            CronTrigger(hour=hh, minute=mm, timezone=checkin_tz),
            id="mood_evening_checkin",
            replace_existing=True,
            misfire_grace_time=grace_seconds,
            coalesce=True,
        )
        logger.info(f"Mood check-in job scheduled at {checkin_time} {checkin_tz}")

    scheduler.start()
    logger.info(
        f"Scheduler started: daily sync at {local_hour:02d}:00 {local_tz}"
    )


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

    # Fire briefing fire-and-forget so the HTTP caller / scheduler is not blocked
    # by the Claude call inside the briefing.
    orchestrator_url = os.environ.get("ORCHESTRATOR_URL", "http://orchestrator:8000")
    asyncio.create_task(trigger_briefing(orchestrator_url))

    return {"garmin": garmin, "yazio": yazio, "errors": errors}


async def trigger_briefing(orchestrator_url: str) -> None:
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            resp = await client.post(f"{orchestrator_url}/briefing")
            logger.info(f"Daily briefing triggered: {resp.json()}")
    except Exception as e:
        logger.warning(f"Daily briefing trigger failed: {e}")


async def _send_mood_checkin() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        logger.warning("Mood check-in skipped: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set")
        return
    text = "🌙 Вечерний чек-ин: как прошёл день? Ответь одним сообщением."
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json={"chat_id": chat_id, "text": text})
            resp.raise_for_status()
    except Exception as e:
        logger.warning("Mood check-in send failed: %s", e)
