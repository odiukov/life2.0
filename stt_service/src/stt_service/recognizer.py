"""Recognizer boundary. Only this module imports faster_whisper."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from av.error import FFmpegError

from stt_service.settings import SttSettings


@dataclass(frozen=True, slots=True)
class Recognized:
    text: str
    language: str | None
    duration_s: float


class TooLong(Exception):
    """The decoded audio duration exceeds the configured limit."""


class Undecodable(Exception):
    """The audio cannot be decoded."""


class Recognizer(Protocol):
    def transcribe(self, path: str, language: str | None) -> Recognized: ...


class WhisperRecognizer:
    def __init__(self, settings: SttSettings) -> None:
        from faster_whisper import WhisperModel

        self._model = WhisperModel(
            settings.model,
            device=settings.device,
            compute_type=settings.compute_type,
            download_root=settings.model_dir,
        )
        self._max = settings.max_duration_s

    def transcribe(self, path: str, language: str | None) -> Recognized:
        try:
            segments, info = self._model.transcribe(
                path, language=language, vad_filter=True, beam_size=1
            )
            duration = float(info.duration)
            if duration > self._max:
                raise TooLong(f"{duration:.0f}s")
            text = " ".join(segment.text.strip() for segment in segments).strip()
        except FFmpegError as exc:
            raise Undecodable(type(exc).__name__) from exc
        return Recognized(text=text, language=info.language, duration_s=duration)


class FakeRecognizer:
    def __init__(
        self,
        text: str = "",
        language: str | None = "ru",
        duration_s: float = 1.0,
        error: Exception | None = None,
    ) -> None:
        self.text, self.language, self.duration_s, self.error = text, language, duration_s, error
        self.calls = 0

    def transcribe(self, path: str, language: str | None) -> Recognized:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return Recognized(self.text, language or self.language, self.duration_s)
