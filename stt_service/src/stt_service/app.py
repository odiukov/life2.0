"""Private HTTP speech endpoint with one active recognition at a time."""

from __future__ import annotations

import asyncio
import os
import tempfile
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager, suppress
from typing import Annotated

import structlog
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from stt_service.recognizer import Recognized, Recognizer, TooLong, Undecodable
from stt_service.settings import SttSettings

MIMES = {
    "audio/m4a": ".m4a",
    "audio/mp4": ".m4a",
    "audio/x-m4a": ".m4a",
    "audio/aac": ".aac",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
}
log = structlog.get_logger(__name__)


class TranscriptOut(BaseModel):
    text: str
    language: str | None
    duration_s: float


def create_app(settings: SttSettings, load: Callable[[], Recognizer]) -> FastAPI:
    state: dict[str, Recognizer] = {}
    gate = asyncio.Semaphore(1)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        async def warm() -> None:
            try:
                state["recognizer"] = await asyncio.to_thread(load)
                log.info("stt_model_loaded", model=settings.model)
            except Exception as exc:
                log.error("stt_model_load_failed", error_type=type(exc).__name__)

        task = asyncio.create_task(warm())
        try:
            yield
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    app = FastAPI(title="stt", lifespan=lifespan)

    @app.get("/health")
    async def health() -> JSONResponse:
        ready = "recognizer" in state
        return JSONResponse(
            {"status": "ok" if ready else "loading"}, status_code=200 if ready else 503
        )

    @app.post("/transcribe", response_model=TranscriptOut)
    async def transcribe(
        audio: Annotated[UploadFile, File()], language: Annotated[str | None, Form()] = None
    ) -> TranscriptOut:
        try:
            suffix = MIMES.get((audio.content_type or "").split(";")[0].strip().lower())
            if suffix is None:
                raise HTTPException(status_code=415, detail="unsupported_audio")
            data = await audio.read(settings.max_bytes + 1)
            if len(data) > settings.max_bytes:
                raise HTTPException(status_code=413, detail="audio_too_long")
            recognizer = state.get("recognizer")
            if recognizer is None:
                raise HTTPException(status_code=503, detail="stt_loading")
            try:
                await asyncio.wait_for(gate.acquire(), timeout=settings.queue_timeout_s)
            except TimeoutError as exc:
                raise HTTPException(status_code=504, detail="stt_busy") from exc

            path = ""
            worker: asyncio.Task[Recognized] | None = None

            def cleanup() -> None:
                gate.release()
                if path:
                    with suppress(FileNotFoundError):
                        os.remove(path)

            async def recognize() -> Recognized:
                try:
                    return await asyncio.to_thread(recognizer.transcribe, path, language)
                finally:
                    cleanup()

            try:
                with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as handle:
                    path = handle.name
                    handle.write(data)
                worker = asyncio.create_task(recognize())
                # Shield preserves the worker's semaphore and audio file after request cancellation.
                worker.add_done_callback(
                    lambda done: done.exception() if not done.cancelled() else None
                )
                result = await asyncio.shield(worker)
            except TooLong as exc:
                raise HTTPException(status_code=413, detail="audio_too_long") from exc
            except Undecodable as exc:
                raise HTTPException(status_code=415, detail="unsupported_audio") from exc
            except Exception as exc:
                log.warning("stt_failed", error_type=type(exc).__name__)
                raise HTTPException(status_code=500, detail="stt_failed") from exc
            finally:
                if worker is None:
                    cleanup()
            log.info("stt_done", duration_s=round(result.duration_s, 1), language=result.language)
            return TranscriptOut(
                text=result.text, language=result.language, duration_s=result.duration_s
            )
        finally:
            await audio.close()

    return app
