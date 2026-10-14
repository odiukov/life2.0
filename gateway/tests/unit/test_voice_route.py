from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI, Header, Request
from gateway.voice import build_router
from shared.ports.stt import (
    AudioTooLong,
    SpeechBusy,
    SpeechUnavailable,
    Transcript,
    UnsupportedAudio,
)
from shared.testing.fakes import FakeSpeechToText

USER_HEADERS = {"X-User-Id": str(uuid4())}


async def dev_user(x_user_id: str = Header(alias="X-User-Id")) -> UUID:
    return UUID(x_user_id)


def client(stt: FakeSpeechToText, max_bytes: int = 1000) -> httpx.AsyncClient:
    app = FastAPI()
    app.include_router(build_router(stt, dev_user, max_bytes=max_bytes))
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://gw")


async def test_returns_text_and_passes_mime_and_language() -> None:
    stt = FakeSpeechToText(Transcript("купил хлеб", "ru", 1.2))
    async with client(stt) as http:
        response = await http.post(
            "/voice/transcribe",
            files={"audio": ("rec.m4a", b"x" * 10, "audio/m4a")},
            data={"language": "en"},
            headers=USER_HEADERS,
        )
    assert (response.status_code, response.json()) == (200, {"text": "купил хлеб"})
    assert stt.calls == [(10, "audio/m4a", "en")]


async def test_empty_speech_defaults_to_russian_and_empty_text() -> None:
    stt = FakeSpeechToText()
    async with client(stt) as http:
        response = await http.post(
            "/voice/transcribe",
            files={"audio": ("rec.m4a", b"x", "audio/m4a")},
            headers=USER_HEADERS,
        )
    assert (response.status_code, response.json()) == (200, {"text": ""})
    assert stt.calls == [(1, "audio/m4a", "ru")]


async def test_upload_at_size_limit_is_accepted() -> None:
    stt = FakeSpeechToText()
    async with client(stt, max_bytes=5) as http:
        response = await http.post(
            "/voice/transcribe",
            files={"audio": ("rec.m4a", b"x" * 5, "audio/m4a")},
            headers=USER_HEADERS,
        )
    assert response.status_code == 200
    assert stt.calls == [(5, "audio/m4a", "ru")]


async def test_oversized_upload_never_reaches_the_service() -> None:
    stt = FakeSpeechToText()
    async with client(stt, max_bytes=5) as http:
        response = await http.post(
            "/voice/transcribe",
            files={"audio": ("rec.m4a", b"x" * 6, "audio/m4a")},
            headers=USER_HEADERS,
        )
    assert (response.status_code, response.json()) == (413, {"detail": "audio_too_long"})
    assert stt.calls == []


async def test_authentication_is_required_before_transcription() -> None:
    stt = FakeSpeechToText()
    async with client(stt) as http:
        response = await http.post(
            "/voice/transcribe", files={"audio": ("rec.m4a", b"x", "audio/m4a")}
        )
    assert response.status_code == 422
    assert stt.calls == []


@pytest.mark.parametrize("authenticated", [True, False])
async def test_large_stream_is_rejected_before_consuming_the_whole_body(
    authenticated: bool,
) -> None:
    stt = FakeSpeechToText()
    consumed: list[int] = []
    boundary = "voice-boundary"

    async def chunks():
        parts = [
            (
                f'--{boundary}\r\nContent-Disposition: form-data; name="audio"; '
                'filename="rec.m4a"\r\nContent-Type: audio/m4a\r\n\r\n'
            ).encode(),
            b"x" * 40_000,
            b"y" * 40_000,
            b"z" * 40_000,
            f"\r\n--{boundary}--\r\n".encode(),
        ]
        for index, part in enumerate(parts):
            consumed.append(index)
            yield part

    headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
    if authenticated:
        headers.update(USER_HEADERS)
    async with client(stt, max_bytes=5) as http:
        response = await http.post("/voice/transcribe", content=chunks(), headers=headers)
    assert (response.status_code, response.json()) == (413, {"detail": "audio_too_long"})
    assert consumed == [0, 1, 2]
    assert stt.calls == []


async def test_declared_oversize_is_rejected_without_reading_body() -> None:
    stt = FakeSpeechToText()
    consumed = False

    async def chunks():
        nonlocal consumed
        consumed = True
        yield b"small"

    async with client(stt, max_bytes=5) as http:
        response = await http.post(
            "/voice/transcribe",
            content=chunks(),
            headers={"Content-Type": "multipart/form-data", "Content-Length": "1000000"},
        )
    assert (response.status_code, response.json()) == (413, {"detail": "audio_too_long"})
    assert not consumed
    assert stt.calls == []


async def test_voice_body_cap_does_not_limit_other_routes() -> None:
    app = FastAPI()
    app.include_router(build_router(FakeSpeechToText(), dev_user, max_bytes=5))

    @app.post("/other")
    async def other(request: Request) -> dict[str, int]:
        return {"size": len(await request.body())}

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://gw"
    ) as http:
        response = await http.post("/other", content=b"x" * 80_000)
    assert (response.status_code, response.json()) == (200, {"size": 80_000})


@pytest.mark.parametrize(
    ("error", "status", "detail"),
    [
        (AudioTooLong("x"), 413, "audio_too_long"),
        (UnsupportedAudio("x"), 415, "unsupported_audio"),
        (SpeechBusy("x"), 504, "stt_busy"),
        (SpeechUnavailable("x"), 503, "stt_unavailable"),
    ],
)
async def test_errors(error: Exception, status: int, detail: str) -> None:
    async with client(FakeSpeechToText(error=error)) as http:
        response = await http.post(
            "/voice/transcribe",
            files={"audio": ("rec.m4a", b"x", "audio/m4a")},
            headers=USER_HEADERS,
        )
    assert (response.status_code, response.json()) == (status, {"detail": detail})
