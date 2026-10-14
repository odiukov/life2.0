"""Scheduler over APScheduler 3 (AsyncIO)."""

from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from shared.ports.scheduler import Job

# Resume missed jobs once after laptop sleep instead of dropping them.
MISFIRE_GRACE_S = 6 * 3600


class ApschedulerScheduler:
    def __init__(self) -> None:
        self._scheduler = AsyncIOScheduler()

    def add_cron(self, job_id: str, func: Job, *, hour: int, minute: int, tz: str) -> None:
        self._scheduler.add_job(
            func,
            CronTrigger(hour=hour, minute=minute, timezone=tz),
            id=job_id,
            replace_existing=True,
            misfire_grace_time=MISFIRE_GRACE_S,
            coalesce=True,
        )

    def job_ids(self) -> list[str]:
        return [job.id for job in self._scheduler.get_jobs()]

    async def start(self) -> None:
        self._scheduler.start()

    async def shutdown(self) -> None:
        self._scheduler.shutdown(wait=False)
