from __future__ import annotations

from datetime import datetime
from typing import Protocol


class UnreadablePdf(Exception):
    pass


class VisionUnavailable(Exception):
    pass


class ReportReader(Protocol):
    def text(self, data: bytes) -> str: ...
    def tables(self, data: bytes) -> list[list[list[str | None]]]: ...
    def first_page_png(self, data: bytes) -> bytes: ...


class ReportVision(Protocol):
    async def metrics(self, png: bytes) -> tuple[datetime | None, dict[str, float]]: ...
    async def profile(self, png: bytes) -> dict[str, object]: ...
