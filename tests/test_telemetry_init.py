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


def test_is_disabled_reads_env(monkeypatch):
    monkeypatch.setenv("OTEL_PYTHON_DISABLED_INSTRUMENTATIONS", "asyncpg, sqlalchemy ,psycopg")
    from shared import telemetry
    assert telemetry._is_disabled("asyncpg") is True
    assert telemetry._is_disabled("sqlalchemy") is True
    assert telemetry._is_disabled("psycopg") is True
    assert telemetry._is_disabled("httpx") is False


def test_is_disabled_empty_env(monkeypatch):
    monkeypatch.delenv("OTEL_PYTHON_DISABLED_INSTRUMENTATIONS", raising=False)
    from shared import telemetry
    assert telemetry._is_disabled("asyncpg") is False


def test_disabled_instrumentor_not_called(monkeypatch):
    """The OTEL CLI env flag must actually skip our manual .instrument() calls."""
    monkeypatch.setenv("TELEMETRY_ENABLED", "true")
    monkeypatch.setenv("OTEL_PYTHON_DISABLED_INSTRUMENTATIONS", "asyncpg,httpx,logging")
    calls: list[str] = []
    import opentelemetry.instrumentation.asyncpg as asyncpg_mod
    import opentelemetry.instrumentation.httpx as httpx_mod
    import opentelemetry.instrumentation.logging as logging_mod
    monkeypatch.setattr(
        asyncpg_mod.AsyncPGInstrumentor, "instrument",
        lambda self, **_: calls.append("asyncpg"),
    )
    monkeypatch.setattr(
        httpx_mod.HTTPXClientInstrumentor, "instrument",
        lambda self, **_: calls.append("httpx"),
    )
    monkeypatch.setattr(
        logging_mod.LoggingInstrumentor, "instrument",
        lambda self, **_: calls.append("logging"),
    )
    from shared import telemetry
    telemetry.init_telemetry("svc")
    assert calls == []


def test_enabled_instrumentor_is_called(monkeypatch):
    monkeypatch.setenv("TELEMETRY_ENABLED", "true")
    monkeypatch.setenv("OTEL_PYTHON_DISABLED_INSTRUMENTATIONS", "")
    calls: list[str] = []
    import opentelemetry.instrumentation.asyncpg as asyncpg_mod
    monkeypatch.setattr(
        asyncpg_mod.AsyncPGInstrumentor, "instrument",
        lambda self, **_: calls.append("asyncpg"),
    )
    from shared import telemetry
    telemetry.init_telemetry("svc")
    assert "asyncpg" in calls


def test_instrument_fastapi_app_respects_disabled(monkeypatch):
    monkeypatch.setenv("OTEL_PYTHON_DISABLED_INSTRUMENTATIONS", "fastapi")
    calls: list[str] = []
    import opentelemetry.instrumentation.fastapi as fastapi_mod
    monkeypatch.setattr(
        fastapi_mod.FastAPIInstrumentor, "instrument_app",
        staticmethod(lambda app, **_: calls.append("fastapi")),
    )
    from shared import telemetry
    telemetry.instrument_fastapi_app(object())
    assert calls == []
