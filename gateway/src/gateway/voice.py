"""Authenticate voice uploads and return a transcript for user review."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.routing import APIRoute
from household.adapters.http import Authenticate
from pydantic import BaseModel
from shared.ports.stt import AudioTooLong, SpeechBusy, SpeechError, SpeechToText, UnsupportedAudio
from starlette.types import Message

_ERRORS: dict[type[SpeechError], tuple[int, str]] = {
    AudioTooLong: (413, "audio_too_long"),
    UnsupportedAudio: (415, "unsupported_audio"),
    SpeechBusy: (504, "stt_busy"),
}


class TranscriptOut(BaseModel):
    text: str


def build_router(stt: SpeechToText, authenticate: Authenticate, *, max_bytes: int) -> APIRouter:
    # Multipart boundaries, headers, and the language field need a small envelope.
    # The exact audio limit is checked separately after parsing.
    body_cap = max_bytes + 65_536

    class LimitedUploadRoute(APIRoute):
        def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
            handle = super().get_route_handler()

            async def limited_upload(request: Request) -> Response:
                length = request.headers.get("content-length")
                if (
                    length is not None
                    and length.isdecimal()
                    and (len(length) > 20 or int(length) > body_cap)
                ):
                    raise HTTPException(status_code=413, detail="audio_too_long")

                received = 0

                async def limited_receive() -> Message:
                    nonlocal received
                    message = await request.receive()
                    if message["type"] == "http.request":
                        received += len(message.get("body", b""))
                        if received > body_cap:
                            raise HTTPException(status_code=413, detail="audio_too_long")
                    return message

                return await handle(Request(request.scope, receive=limited_receive))

            return limited_upload

    router = APIRouter(prefix="/voice", tags=["voice"], route_class=LimitedUploadRoute)
    user_dependency = Depends(authenticate)

    @router.post("/transcribe", response_model=TranscriptOut)
    async def transcribe(
        audio: Annotated[UploadFile, File()],
        language: Annotated[str, Form()] = "ru",
        _user: UUID = user_dependency,
    ) -> TranscriptOut:
        data = await audio.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise HTTPException(status_code=413, detail="audio_too_long")
        try:
            transcript = await stt.transcribe(
                data, mime=audio.content_type or "application/octet-stream", language=language
            )
        except SpeechError as exc:
            status, detail = _ERRORS.get(type(exc), (503, "stt_unavailable"))
            raise HTTPException(status_code=status, detail=detail) from exc
        return TranscriptOut(text=transcript.text)

    return router
