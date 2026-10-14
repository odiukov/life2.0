"""Production entrypoint: telemetry must start before anything else is imported."""

from shared.observability.telemetry import init_telemetry, instrument_fastapi_app

init_telemetry("sync-service")

from pydantic import ValidationError  # noqa: E402
from pydantic_settings import SettingsError  # noqa: E402

from sync.main import create_app  # noqa: E402

try:
    app = create_app()
except (ValidationError, SettingsError):
    # Settings errors include raw input values. Exit before Uvicorn can print them.
    raise SystemExit("sync_configuration_invalid") from None
instrument_fastapi_app(app)
