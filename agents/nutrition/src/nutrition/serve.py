"""Production entrypoint: telemetry must start before anything else is imported."""

from shared.observability.telemetry import init_telemetry, instrument_fastapi_app

init_telemetry("agent-nutrition")

from nutrition.main import create_app  # noqa: E402

app = create_app()
instrument_fastapi_app(app)
