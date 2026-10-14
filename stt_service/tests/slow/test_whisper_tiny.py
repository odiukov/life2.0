"""Real faster-whisper with a tiny model; enable with STT_TEST_MODEL=tiny."""

import math
import struct
import wave
from pathlib import Path

import pytest
from pydantic_settings import BaseSettings, SettingsConfigDict
from stt_service.recognizer import TooLong, WhisperRecognizer
from stt_service.settings import SttSettings

pytestmark = pytest.mark.slow


class _TestEnv(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="STT_TEST_")
    model: str | None = None


@pytest.fixture(scope="module")
def recognizer(tmp_path_factory: pytest.TempPathFactory) -> WhisperRecognizer:
    model = _TestEnv().model
    if not model:
        pytest.skip("set STT_TEST_MODEL=tiny to run")
    return WhisperRecognizer(
        SttSettings(model=model, model_dir=str(tmp_path_factory.mktemp("models")), max_duration_s=5)
    )


def tone(path: Path, seconds: float) -> None:
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(16000)
        frames = b"".join(
            struct.pack("<h", int(1000 * math.sin(2 * math.pi * 440 * i / 16000)))
            for i in range(int(16000 * seconds))
        )
        out.writeframes(frames)


def test_tone_has_no_speech_and_a_duration(recognizer: WhisperRecognizer, tmp_path: Path) -> None:
    path = tmp_path / "tone.wav"
    tone(path, 1.0)
    result = recognizer.transcribe(str(path), "ru")
    assert result.text == ""
    assert abs(result.duration_s - 1.0) < 0.1


def test_too_long_is_rejected_from_metadata(recognizer: WhisperRecognizer, tmp_path: Path) -> None:
    path = tmp_path / "long.wav"
    tone(path, 6.0)
    with pytest.raises(TooLong):
        recognizer.transcribe(str(path), "ru")
