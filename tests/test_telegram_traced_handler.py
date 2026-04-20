"""Unit test for telegram_bot.main.traced_handler decorator."""
import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture(autouse=True)
def reset_telemetry():
    import shared.telemetry as t
    t._INITIALIZED = False
    from opentelemetry.test.globals_test import reset_trace_globals
    reset_trace_globals()
    yield
    t._INITIALIZED = False
    reset_trace_globals()


@pytest.mark.asyncio
async def test_traced_handler_sets_span_attributes(monkeypatch):
    monkeypatch.setenv("TELEMETRY_ENABLED", "false")
    monkeypatch.setenv("LANGFUSE_DEFAULT_USER_ID", "owner")

    # Use an InMemorySpanExporter attached to a fresh TracerProvider to avoid
    # relying on Traceloop's global setup in the test.
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    from opentelemetry import trace as otel_trace

    # Import & reload telegram_bot.app.main with telemetry disabled so it
    # doesn't install a provider over our test-exporter one.
    import importlib
    import telegram_bot.app.main as tmain
    importlib.reload(tmain)

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    otel_trace.set_tracer_provider(provider)

    # Re-bind the module-level tracer AFTER provider swap so start_as_current_span
    # uses the exporter-backed provider.
    tmain._telemetry_tracer = otel_trace.get_tracer("telegram.bot")

    update = MagicMock()
    update.effective_chat.id = 12345
    context = MagicMock()

    inner = AsyncMock(return_value=None)
    inner.__name__ = "cmd_x"
    wrapped = tmain.traced_handler("x")(inner)

    await wrapped(update, context)

    provider.force_flush()
    spans = exporter.get_finished_spans()
    assert any(s.name == "telegram.x" for s in spans)
    s = next(s for s in spans if s.name == "telegram.x")
    assert s.attributes["telegram.chat_id"] == 12345
    assert s.attributes["telegram.command"] == "x"
    assert s.attributes["langfuse.user.id"] == "owner"
    assert s.attributes["langfuse.session.id"] == "tg-12345"
