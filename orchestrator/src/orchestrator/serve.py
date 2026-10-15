"""Production entrypoint: initialize telemetry before importing the application."""

from shared.observability.telemetry import init_telemetry, instrument_fastapi_app

init_telemetry("orchestrator")

from orchestrator.main import create_app  # noqa: E402

app = create_app()
instrument_fastapi_app(app)
