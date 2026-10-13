from __future__ import annotations

from typing import Protocol


class SpeechToText(Protocol):
    async def transcribe(self, audio: bytes, *, mime: str, language: str | None) -> str: ...
