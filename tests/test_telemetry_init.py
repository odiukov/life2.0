"""Tests for shared.telemetry.init_telemetry."""
import base64
import importlib
import os
import pytest


@pytest.fixture(autouse=True)
def reset_telemetry():
    """Reset the module-level _INITIALIZED guard and OTEL globals between tests."""
    import shared.telemetry as t
    t._INITIALIZED = False
    # Clear OTEL globals so TracerProvider registration doesn't leak.
    from opentelemetry.test.globals_test import reset_trace_globals
    reset_trace_globals()
    yield
    t._INITIALIZED = False
    reset_trace_globals()


def test_disabled_flag_is_noop(monkeypatch):
    monkeypatch.setenv("TELEMETRY_ENABLED", "false")
    from shared import telemetry
    telemetry.init_telemetry("test-svc")
    from opentelemetry import trace
    # Default provider is ProxyTracerProvider when nothing registered.
    provider = trace.get_tracer_provider()
    assert type(provider).__name__ in {"ProxyTracerProvider", "NoOpTracerProvider"}


def test_init_is_idempotent(monkeypatch):
    monkeypatch.setenv("TELEMETRY_ENABLED", "true")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-x")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-x")
    from shared import telemetry
    telemetry.init_telemetry("svc-a")
    # Second call must not raise and must not re-register providers.
    telemetry.init_telemetry("svc-b")
    assert telemetry._INITIALIZED is True


def test_capture_full_sets_traceloop_content_true(monkeypatch):
    monkeypatch.setenv("TELEMETRY_ENABLED", "true")
    monkeypatch.setenv("TELEMETRY_CAPTURE_BODIES", "full")
    monkeypatch.delenv("TRACELOOP_TRACE_CONTENT", raising=False)
    from shared import telemetry
    telemetry.init_telemetry("svc")
    assert os.environ["TRACELOOP_TRACE_CONTENT"] == "true"


def test_capture_metadata_sets_traceloop_content_false(monkeypatch):
    monkeypatch.setenv("TELEMETRY_ENABLED", "true")
    monkeypatch.setenv("TELEMETRY_CAPTURE_BODIES", "metadata")
    monkeypatch.delenv("TRACELOOP_TRACE_CONTENT", raising=False)
    from shared import telemetry
    telemetry.init_telemetry("svc")
    assert os.environ["TRACELOOP_TRACE_CONTENT"] == "false"


def test_otlp_headers_built_from_pub_sec(monkeypatch):
    from urllib.parse import unquote
    monkeypatch.setenv("TELEMETRY_ENABLED", "true")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-x")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-y")
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_HEADERS", raising=False)
    from shared import telemetry
    telemetry.init_telemetry("svc")
    hdr = os.environ["OTEL_EXPORTER_OTLP_HEADERS"]
    # Value is URL-encoded per OTEL spec (so base64 "==" padding doesn't break parsing).
    assert hdr.startswith("Authorization=")
    raw_value = unquote(hdr.split("Authorization=", 1)[1])
    assert raw_value.startswith("Basic ")
    token = raw_value.split("Basic ", 1)[1]
    decoded = base64.b64decode(token).decode()
    assert decoded == "pk-x:sk-y"


def test_set_span_user_fallback_env(monkeypatch):
    monkeypatch.setenv("TELEMETRY_ENABLED", "true")
    monkeypatch.setenv("LANGFUSE_DEFAULT_USER_ID", "ownerX")
    from shared import telemetry
    telemetry.init_telemetry("svc")
    from opentelemetry import trace
    tracer = trace.get_tracer("t")
    with tracer.start_as_current_span("root") as span:
        telemetry.set_span_user()
        assert span.attributes["langfuse.user.id"] == "ownerX"


def test_set_span_user_override(monkeypatch):
    monkeypatch.setenv("TELEMETRY_ENABLED", "true")
    monkeypatch.setenv("LANGFUSE_DEFAULT_USER_ID", "ownerX")
    from shared import telemetry
    telemetry.init_telemetry("svc")
    from opentelemetry import trace
    tracer = trace.get_tracer("t")
    with tracer.start_as_current_span("root") as span:
        telemetry.set_span_user("alice")
        assert span.attributes["langfuse.user.id"] == "alice"


def test_set_span_session(monkeypatch):
    monkeypatch.setenv("TELEMETRY_ENABLED", "true")
    from shared import telemetry
    telemetry.init_telemetry("svc")
    from opentelemetry import trace
    tracer = trace.get_tracer("t")
    with tracer.start_as_current_span("root") as span:
        telemetry.set_span_session("thread-42")
        assert span.attributes["langfuse.session.id"] == "thread-42"
