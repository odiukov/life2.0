from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class Transcript:
    text: str
    language: str | None
    duration_s: float


class SpeechError(Exception):
    """Base class for speech-to-text failures."""


class AudioTooLong(SpeechError):
    """The recording exceeds the configured size or duration."""


class UnsupportedAudio(SpeechError):
    """The audio container or codec cannot be decoded."""


class SpeechBusy(SpeechError):
    """The recognizer queue did not free up in time."""


class SpeechUnavailable(SpeechError):
    """The recognizer cannot be reached or failed unexpectedly."""


class SpeechToText(Protocol):
    async def transcribe(self, audio: bytes, *, mime: str, language: str | None) -> Transcript:
        """Empty speech returns Transcript(text="")."""
        ...
