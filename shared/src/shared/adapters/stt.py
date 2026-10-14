"""SpeechToText over the local STT service's HTTP contract."""

from __future__ import annotations

import httpx

from shared.ports.stt import (
    AudioTooLong,
    SpeechBusy,
    SpeechUnavailable,
    Transcript,
    UnsupportedAudio,
)

_ERRORS: dict[int, type[Exception]] = {413: AudioTooLong, 415: UnsupportedAudio, 504: SpeechBusy}


class HttpSpeechToText:
    def __init__(self, base_url: str, http: httpx.AsyncClient, *, timeout_s: float = 40.0) -> None:
        self._url = base_url.rstrip("/") + "/transcribe"
        self._http = http
        self._timeout = timeout_s

    async def transcribe(self, audio: bytes, *, mime: str, language: str | None) -> Transcript:
        data = {"language": language} if language else {}
        try:
            response = await self._http.post(
                self._url, files={"audio": ("audio", audio, mime)}, data=data, timeout=self._timeout
            )
        except httpx.HTTPError as exc:
            raise SpeechUnavailable(type(exc).__name__) from exc
        error = _ERRORS.get(response.status_code)
        if error is not None:
            raise error(response.status_code)
        if response.status_code != 200:
            raise SpeechUnavailable(str(response.status_code))
        try:
            body = response.json()
            return Transcript(
                text=str(body["text"]),
                language=body["language"],
                duration_s=float(body["duration_s"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise SpeechUnavailable("invalid_response") from exc
