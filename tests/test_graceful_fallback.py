"""Regression: telemetry must not crash the app if Langfuse is unreachable."""
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


def test_init_with_unreachable_endpoint_does_not_raise(monkeypatch):
    monkeypatch.setenv("TELEMETRY_ENABLED", "true")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://unreachable.invalid:9999")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-x")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-x")
    from shared import telemetry
    # Must not raise even though endpoint is unreachable.
    telemetry.init_telemetry("svc-unreachable")
    assert telemetry._INITIALIZED is True


def test_span_creation_with_unreachable_endpoint(monkeypatch):
    monkeypatch.setenv("TELEMETRY_ENABLED", "true")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://unreachable.invalid:9999")
    from shared import telemetry
    telemetry.init_telemetry("svc")
    from opentelemetry import trace
    tracer = trace.get_tracer("t")
    # Creating and ending a span must not raise even though export will fail.
    with tracer.start_as_current_span("root") as span:
        telemetry.set_span_user("x")
        span.set_attribute("test", "ok")
