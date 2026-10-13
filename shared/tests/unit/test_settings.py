import re
from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError
from shared.config import (
    BaseServiceSettings,
    DatabaseSettings,
    LLMRoute,
    LLMSettings,
    env_names,
    find_locales_dir,
)
from shared.ports.llm import LLMTask

REPO = Path(__file__).resolve().parents[3]
DSN = "postgresql+asyncpg://app_rw:x@db:5432/life"


@pytest.fixture(autouse=True)
def clean_settings_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    # Isolate settings from developer credentials and service-specific overrides.
    for name in env_names(BaseServiceSettings):
        monkeypatch.delenv(name, raising=False)
    for name in ("DATABASE", "LLM", "LLM__TASKS", "TELEMETRY"):
        monkeypatch.delenv(name, raising=False)


def test_route_parses_provider_and_model_with_colons() -> None:
    route = LLMRoute.model_validate("openrouter:qwen/qwen3-coder-480b-a35b-instruct:free")
    assert route.provider == "openrouter"
    assert route.model == "qwen/qwen3-coder-480b-a35b-instruct:free"
    assert str(route) == "openrouter:qwen/qwen3-coder-480b-a35b-instruct:free"


@pytest.mark.parametrize("raw", ["anthropic", "anthropic:", "unknown:model"])
def test_route_rejects_malformed_values(raw: str) -> None:
    with pytest.raises(ValidationError):
        LLMRoute.model_validate(raw)


@pytest.mark.parametrize(
    "raw", ["postgresql://u:p@h:5432/d", SecretStr("postgresql://u:p@h:5432/d")]
)
def test_dsn_is_normalized_to_asyncpg(raw: str | SecretStr) -> None:
    db = DatabaseSettings.model_validate({"dsn": raw})
    assert db.dsn.get_secret_value() == "postgresql+asyncpg://u:p@h:5432/d"
    assert "u:p" not in repr(db)


def test_nested_env_and_task_routes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE__DSN", DSN)
    monkeypatch.setenv("DATABASE__ROLE", "app_owner")
    monkeypatch.setenv("LLM__DEFAULT", "anthropic:claude-sonnet-5-5")
    monkeypatch.setenv("LLM__TASKS__SMART", "anthropic:claude-opus-5-5")
    monkeypatch.setenv("TELEMETRY__LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("QDRANT_URL", "https://vectors.example.com:6333")
    settings = BaseServiceSettings()
    assert settings.llm.route(LLMTask.FAST).model == "claude-sonnet-5-5"
    assert settings.llm.route(LLMTask.SMART).model == "claude-opus-5-5"
    assert settings.telemetry.log_level == "DEBUG"
    assert settings.default_locale == "ru"
    assert settings.database.role == "app_owner"
    assert str(settings.qdrant_url) == "https://vectors.example.com:6333/"


def test_missing_dsn_fails_fast() -> None:
    with pytest.raises(ValidationError):
        BaseServiceSettings()


def test_default_llm_route_is_provider_neutral_and_oauth_is_opt_in() -> None:
    llm = LLMSettings()
    assert llm.route(LLMTask.SMART).provider == "openrouter"
    assert llm.route(LLMTask.SMART).model == "qwen/qwen3-coder-480b-a35b-instruct:free"
    assert llm.anthropic_auth == "api_key"
    assert LLMSettings(anthropic_auth="oauth_token").anthropic_auth == "oauth_token"


@pytest.mark.parametrize(("field", "value"), [("timeout_s", 0), ("retry_attempts", 0)])
def test_llm_rejects_non_positive_limits(field: str, value: int) -> None:
    with pytest.raises(ValidationError):
        LLMSettings.model_validate({field: value})


def test_database_defaults_to_application_role() -> None:
    db = DatabaseSettings.model_validate({"dsn": DSN})
    assert db.role == "app_rw"
    assert db.pool_size == 5


@pytest.mark.parametrize("role", ["app_owner", "app_rw", "app_legacy"])
def test_database_accepts_supported_roles(role: str) -> None:
    db = DatabaseSettings.model_validate({"dsn": DSN, "role": role})
    assert db.role == role


def test_database_rejects_unknown_role() -> None:
    with pytest.raises(ValidationError):
        DatabaseSettings.model_validate({"dsn": DSN, "role": "postgres"})


def test_database_rejects_empty_pool() -> None:
    with pytest.raises(ValidationError):
        DatabaseSettings.model_validate({"dsn": DSN, "pool_size": 0})


def test_qdrant_defaults_to_local_http_endpoint() -> None:
    settings = BaseServiceSettings(database=DatabaseSettings.model_validate({"dsn": DSN}))
    assert str(settings.qdrant_url) == "http://localhost:6333/"


@pytest.mark.parametrize("url", ["", "qdrant:6333", "ftp://vectors.example.com", "http://"])
def test_qdrant_rejects_invalid_http_urls(url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE__DSN", DSN)
    monkeypatch.setenv("QDRANT_URL", url)
    with pytest.raises(ValidationError):
        BaseServiceSettings()


def test_find_locales_dir_walks_up_to_the_repo() -> None:
    found = find_locales_dir()
    assert found == REPO / "packages" / "i18n" / "locales"
    assert (found / "ru.json").is_file()


def test_find_locales_dir_accepts_a_nested_file(tmp_path: Path) -> None:
    locales = tmp_path / "packages" / "i18n" / "locales"
    locales.mkdir(parents=True)
    assert find_locales_dir(tmp_path / "src" / "service.py") == locales


def test_find_locales_dir_raises_when_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        find_locales_dir(tmp_path)


def test_env_names_flatten_nested_models_and_enum_keyed_dicts() -> None:
    names = env_names(BaseServiceSettings, exclude={"service_name"})
    assert {
        "DATABASE__DSN",
        "DATABASE__ROLE",
        "QDRANT_URL",
        "LLM__TASKS__MOOD_COACH",
        "ANTHROPIC_API_KEY",
    } <= names
    assert "SERVICE_NAME" not in names
    assert "SERVICE_NAME" in env_names(BaseServiceSettings)


def test_env_example_documents_every_setting() -> None:
    text = (REPO / ".env.example").read_text(encoding="utf-8")
    missing = [
        name
        for name in sorted(env_names(BaseServiceSettings))
        if not re.search(rf"^#?\s*{re.escape(name)}=", text, re.MULTILINE)
    ]
    assert missing == []
