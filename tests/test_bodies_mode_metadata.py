"""Metadata mode: TRACELOOP_TRACE_CONTENT must be false → no prompt/completion
bodies captured by OpenLLMetry instrumentors."""
import os
import pytest


@pytest.fixture(autouse=True)
def reset_telemetry():
    import shared.telemetry as t
    t._INITIALIZED = False
    from opentelemetry.test.globals_test import reset_trace_globals
    reset_trace_globals()
    yield
    t._INITIALIZED = False
    reset_trace_globals()


def test_metadata_mode_disables_content_capture(monkeypatch):
    monkeypatch.setenv("TELEMETRY_ENABLED", "true")
    monkeypatch.setenv("TELEMETRY_CAPTURE_BODIES", "metadata")
    monkeypatch.delenv("TRACELOOP_TRACE_CONTENT", raising=False)
    from shared import telemetry
    telemetry.init_telemetry("svc")
    assert os.environ["TRACELOOP_TRACE_CONTENT"] == "false"


def test_full_mode_enables_content_capture(monkeypatch):
    monkeypatch.setenv("TELEMETRY_ENABLED", "true")
    monkeypatch.setenv("TELEMETRY_CAPTURE_BODIES", "full")
    monkeypatch.delenv("TRACELOOP_TRACE_CONTENT", raising=False)
    from shared import telemetry
    telemetry.init_telemetry("svc")
    assert os.environ["TRACELOOP_TRACE_CONTENT"] == "true"


def test_consented_mode_enables_content_capture(monkeypatch):
    # Consented mode MUST capture content — ConsentSpanExporter redacts it at
    # export time per user consent. Without capture there'd be nothing to redact.
    monkeypatch.setenv("TELEMETRY_ENABLED", "true")
    monkeypatch.setenv("TELEMETRY_CAPTURE_BODIES", "consented")
    monkeypatch.delenv("TRACELOOP_TRACE_CONTENT", raising=False)
    from shared import telemetry
    telemetry.init_telemetry("svc")
    assert os.environ["TRACELOOP_TRACE_CONTENT"] == "true"
