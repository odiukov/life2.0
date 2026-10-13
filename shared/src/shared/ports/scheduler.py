from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol

Job = Callable[[], Awaitable[None]]


class Scheduler(Protocol):
    def add_cron(self, job_id: str, func: Job, *, hour: int, minute: int, tz: str) -> None: ...

    async def start(self) -> None: ...

    async def shutdown(self) -> None: ...
