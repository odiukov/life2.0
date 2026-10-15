from __future__ import annotations

from datetime import datetime

from body.application.ports import UnreadablePdf, VisionUnavailable


class FakeReportReader:
    def __init__(self, text: str, tables: list[list[list[str | None]]] | None = None) -> None:
        self._text, self._tables = text, tables or []

    def text(self, data: bytes) -> str:
        if not data.startswith(b"%PDF-"):
            raise UnreadablePdf
        return self._text

    def tables(self, data: bytes) -> list[list[list[str | None]]]:
        return self._tables

    def first_page_png(self, data: bytes) -> bytes:
        return b"\x89PNG fake"


class FakeReportVision:
    def __init__(
        self,
        when: datetime | None = None,
        metrics: dict[str, float] | None = None,
        profile: dict[str, object] | None = None,
        down: bool = False,
    ) -> None:
        self.when, self._metrics, self._profile, self.down = (
            when,
            metrics or {},
            profile or {},
            down,
        )
        self.calls = 0

    async def metrics(self, png: bytes) -> tuple[datetime | None, dict[str, float]]:
        self.calls += 1
        if self.down:
            raise VisionUnavailable
        return self.when, dict(self._metrics)

    async def profile(self, png: bytes) -> dict[str, object]:
        self.calls += 1
        if self.down:
            raise VisionUnavailable
        return dict(self._profile)
