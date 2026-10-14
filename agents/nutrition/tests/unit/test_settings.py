import re
from pathlib import Path

import pytest
from nutrition.settings import NutritionSettings
from shared.config import env_names

REPO = Path(__file__).resolve().parents[4]


def test_reads_the_legacy_variable_names(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE__DSN", "postgresql://app_rw:x@postgres:5432/db")
    monkeypatch.setenv("NUTRITION_AGENT_URL", "http://n:8003/")
    monkeypatch.setenv("SYNC_SERVICE_URL", "http://sync-service:8080")
    settings = NutritionSettings()
    assert settings.nutrition_agent_url == "http://n:8003/"
    assert settings.sync_service_url == "http://sync-service:8080"
    assert settings.service_name == "agent-nutrition"


def test_env_example_documents_every_setting() -> None:
    text = (REPO / ".env.example").read_text(encoding="utf-8")
    missing = [
        n
        for n in sorted(env_names(NutritionSettings, exclude={"service_name"}))
        if not re.search(rf"^#?\s*{re.escape(n)}=", text, re.MULTILINE)
    ]
    assert missing == []
