import asyncio
import threading
from pathlib import Path

import httpx
import pytest
from av.error import InvalidDataError
from stt_service.app import create_app
from stt_service.recognizer import (
    FakeRecognizer,
    Recognized,
    TooLong,
    Undecodable,
    WhisperRecognizer,
)
from stt_service.settings import SttSettings

WAV = b"RIFF" + b"\x00" * 64


async def _post(
    http: httpx.AsyncClient, audio: bytes = WAV, mime: str = "audio/wav"
) -> httpx.Response:
    return await http.post("/transcribe", files={"audio": ("audio.wav", audio, mime)})


async def _ready(http: httpx.AsyncClient) -> None:
    for _ in range(100):
        if (await http.get("/health")).status_code == 200:
            return
        await asyncio.sleep(0.01)
    pytest.fail("STT did not become ready")


async def _temp_files(path: Path) -> list[Path]:
    return await asyncio.to_thread(lambda: list(path.iterdir()))


async def test_transcribes_and_reports_language_and_duration() -> None:
    app = create_app(SttSettings(), load=lambda: FakeRecognizer(text="купил хлеб", duration_s=1.5))
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://stt") as http,
    ):
        await _ready(http)
        assert (await http.get("/health")).status_code == 200
        response = await http.post(
            "/transcribe",
            files={"audio": ("a.m4a", b"x" * 100, "audio/m4a")},
            data={"language": "ru"},
        )
    assert response.status_code == 200
    assert response.json() == {"text": "купил хлеб", "language": "ru", "duration_s": 1.5}


async def test_health_is_503_until_the_model_is_loaded() -> None:
    release = threading.Event()

    def slow_load() -> FakeRecognizer:
        release.wait(5)
        return FakeRecognizer()

    app = create_app(SttSettings(), load=slow_load)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://stt") as http,
    ):
        assert (await http.get("/health")).status_code == 503
        release.set()
        for _ in range(50):
            if (await http.get("/health")).status_code == 200:
                break
            await asyncio.sleep(0.05)
        assert (await http.get("/health")).status_code == 200


@pytest.mark.parametrize(
    ("recognizer", "status", "detail"),
    [
        (FakeRecognizer(error=TooLong("61s")), 413, "audio_too_long"),
        (FakeRecognizer(error=Undecodable("bad")), 415, "unsupported_audio"),
        (FakeRecognizer(error=RuntimeError("boom")), 500, "stt_failed"),
    ],
)
async def test_recognizer_errors_map_to_statuses(
    recognizer: FakeRecognizer, status: int, detail: str
) -> None:
    app = create_app(SttSettings(), load=lambda: recognizer)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://stt") as http,
    ):
        await _ready(http)
        response = await _post(http)
    assert (response.status_code, response.json()) == (status, {"detail": detail})


@pytest.mark.parametrize(
    ("failure", "status", "detail"),
    [
        (InvalidDataError(1094995529, "invalid audio"), 415, "unsupported_audio"),
        (RuntimeError("model failed"), 500, "stt_failed"),
    ],
)
async def test_real_wrapper_distinguishes_decode_and_model_errors(
    failure: Exception, status: int, detail: str
) -> None:
    class FailingModel:
        def transcribe(
            self, path: str, *, language: str | None, vad_filter: bool, beam_size: int
        ) -> None:
            raise failure

    recognizer = object.__new__(WhisperRecognizer)
    recognizer._model = FailingModel()
    recognizer._max = 60.0
    app = create_app(SttSettings(), load=lambda: recognizer)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://stt") as http,
    ):
        await _ready(http)
        response = await _post(http)
    assert (response.status_code, response.json()) == (status, {"detail": detail})


async def test_body_limit_and_mime_are_checked_before_decoding() -> None:
    recognizer = FakeRecognizer()
    app = create_app(SttSettings(max_bytes=10), load=lambda: recognizer)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://stt") as http,
    ):
        await _ready(http)
        big = await _post(http, b"x" * 11)
        odd = await _post(http, b"x", "text/plain")
    assert (big.status_code, odd.status_code) == (413, 415)
    assert recognizer.calls == 0


async def test_busy_queue_times_out() -> None:
    entered = threading.Event()
    gate = threading.Event()

    class Blocking(FakeRecognizer):
        def transcribe(self, path: str, language: str | None) -> Recognized:
            entered.set()
            gate.wait(5)
            return Recognized("", language, 1.0)

    app = create_app(SttSettings(queue_timeout_s=0.1), load=lambda: Blocking())
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://stt") as http,
    ):
        await _ready(http)
        first = asyncio.create_task(_post(http))
        assert await asyncio.to_thread(entered.wait, 2)
        second = await _post(http)
        gate.set()
        await first
    assert (second.status_code, second.json()) == (504, {"detail": "stt_busy"})


async def test_temp_files_are_removed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import tempfile

    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    app = create_app(SttSettings(), load=lambda: FakeRecognizer(error=Undecodable("x")))
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://stt") as http,
    ):
        await _ready(http)
        await _post(http)
    assert await _temp_files(tmp_path) == []


async def test_cancelled_request_keeps_file_and_gate_until_worker_finishes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tempfile

    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    entered = threading.Event()
    release = threading.Event()

    class Blocking(FakeRecognizer):
        def transcribe(self, path: str, language: str | None) -> Recognized:
            assert Path(path).exists()
            entered.set()
            release.wait(5)
            assert Path(path).exists()
            return Recognized("", language, 1.0)

    app = create_app(SttSettings(queue_timeout_s=0.1), load=lambda: Blocking())
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://stt") as http,
    ):
        await _ready(http)
        first = asyncio.create_task(_post(http))
        assert await asyncio.to_thread(entered.wait, 2)
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        assert len(await _temp_files(tmp_path)) == 1
        second = await _post(http)
        assert second.status_code == 504
        release.set()
        for _ in range(50):
            if not await _temp_files(tmp_path):
                break
            await asyncio.sleep(0.02)
    assert await _temp_files(tmp_path) == []
