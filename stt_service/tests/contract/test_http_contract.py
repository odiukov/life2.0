"""The HTTP adapter speaks the local STT service contract."""

import asyncio

import httpx
import pytest
from shared.adapters.stt import HttpSpeechToText
from shared.ports.stt import (
    AudioTooLong,
    SpeechBusy,
    SpeechUnavailable,
    Transcript,
    UnsupportedAudio,
)
from stt_service.app import create_app
from stt_service.recognizer import FakeRecognizer, TooLong, Undecodable
from stt_service.settings import SttSettings


async def run(recognizer: FakeRecognizer) -> Transcript:
    app = create_app(SttSettings(), load=lambda: recognizer)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app)) as http,
    ):
        for _ in range(100):
            if (await http.get("http://stt/health")).status_code == 200:
                break
            await asyncio.sleep(0.01)
        return await HttpSpeechToText("http://stt", http).transcribe(
            b"x" * 10, mime="audio/m4a", language="ru"
        )


async def test_success() -> None:
    assert await run(FakeRecognizer(text="купил хлеб", duration_s=2.0)) == Transcript(
        "купил хлеб", "ru", 2.0
    )


@pytest.mark.parametrize(
    ("recognizer", "error"),
    [
        (FakeRecognizer(error=TooLong("x")), AudioTooLong),
        (FakeRecognizer(error=Undecodable("x")), UnsupportedAudio),
        (FakeRecognizer(error=RuntimeError("x")), SpeechUnavailable),
    ],
)
async def test_errors(recognizer: FakeRecognizer, error: type[Exception]) -> None:
    with pytest.raises(error):
        await run(recognizer)


async def test_busy_and_unreachable() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(504, json={"detail": "stt_busy"}))
    ) as http:
        with pytest.raises(SpeechBusy):
            await HttpSpeechToText("http://stt", http).transcribe(
                b"x", mime="audio/wav", language=None
            )

    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(down)) as http:
        with pytest.raises(SpeechUnavailable):
            await HttpSpeechToText("http://stt", http).transcribe(
                b"x", mime="audio/wav", language=None
            )
