"""OpenTelemetry + Langfuse setup shared by all services.

Canonical OTEL: SDK + auto-instrumentors + OTLP export via HTTP.
Canonical GenAI: OpenLLMetry (traceloop-sdk) provides LangChain/LangGraph/LLM-SDK spans
with gen_ai.* semantic conventions.

First line of each service's `main.py`:

    from shared.telemetry import init_telemetry
    init_telemetry("my-service")

Env vars:
    TELEMETRY_ENABLED         true|false (default true; false = no-op)
    TELEMETRY_CAPTURE_BODIES  full|metadata|consented (default full)
    LANGFUSE_DEFAULT_USER_ID  fallback for set_span_user(None)
    LANGFUSE_PUBLIC_KEY       builds OTLP auth header
    LANGFUSE_SECRET_KEY       builds OTLP auth header
    OTEL_EXPORTER_OTLP_ENDPOINT  default http://langfuse-web:3000/api/public/otel
"""
from __future__ import annotations

import base64
import logging
import os
from typing import Awaitable, Callable

log = logging.getLogger(__name__)

_INITIALIZED: bool = False

OTLP_DEFAULT_ENDPOINT = "http://langfuse-web:3000/api/public/otel"


def init_telemetry(
    service_name: str,
    *,
    consent_lookup: Callable[[str], Awaitable[bool]] | None = None,
) -> None:
    """Idempotent OTEL + Traceloop setup. First line of main.py, before FastAPI import.

    `consent_lookup` is only relevant in `consented` mode; the root-span resolver
    (in the service) invokes it to populate W3C baggage. Stored on the module
    so services that don't start root spans directly (agents) can still use it
    if needed.
    """
    global _INITIALIZED
    if _INITIALIZED:
        return
    if os.environ.get("TELEMETRY_ENABLED", "true").lower() in ("false", "0", ""):
        _INITIALIZED = True
        log.info("Telemetry disabled via TELEMETRY_ENABLED")
        return

    os.environ.setdefault("OTEL_SERVICE_NAME", service_name)
    os.environ.setdefault("OTEL_EXPORTER_OTLP_ENDPOINT", OTLP_DEFAULT_ENDPOINT)
    # Traceloop's default api_endpoint is https://api.traceloop.com and it bails
    # out when no TRACELOOP_API_KEY is set. Point it at our OTLP endpoint so it
    # initializes a real TracerProvider and exports to Langfuse instead.
    os.environ.setdefault(
        "TRACELOOP_BASE_URL", os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"]
    )

    pub = os.environ.get("LANGFUSE_PUBLIC_KEY")
    sec = os.environ.get("LANGFUSE_SECRET_KEY")
    if pub and sec and "OTEL_EXPORTER_OTLP_HEADERS" not in os.environ:
        from urllib.parse import quote
        token = base64.b64encode(f"{pub}:{sec}".encode()).decode()
        # OTEL spec: header VALUES in OTEL_EXPORTER_OTLP_HEADERS must be URL-encoded
        # if they contain '=' or ','. Base64 padding '==' triggers the warning and,
        # on stricter SDK versions, drops headers entirely. `quote(safe="")` escapes '='.
        auth_value = quote(f"Basic {token}", safe="")
        os.environ["OTEL_EXPORTER_OTLP_HEADERS"] = f"Authorization={auth_value}"
        # Mirror for Traceloop's header reader as well.
        os.environ.setdefault(
            "TRACELOOP_HEADERS", os.environ["OTEL_EXPORTER_OTLP_HEADERS"]
        )

    capture = os.environ.get("TELEMETRY_CAPTURE_BODIES", "full").lower()
    os.environ.setdefault(
        "TRACELOOP_TRACE_CONTENT",
        "true" if capture == "full" else "false",
    )

    # Traceloop installs global TracerProvider + BatchSpanProcessor + OTLPExporter.
    # Do this before framework instrumentors so they hook into Traceloop's provider.
    try:
        from traceloop.sdk import Traceloop
        Traceloop.init(app_name=service_name, disable_batch=False)
    except Exception as e:
        log.warning("Traceloop.init failed (telemetry will be degraded): %s", e)

    # Fallback: if Traceloop silently did not register a real TracerProvider
    # (missing API key against api.traceloop.com, singleton from a prior init
    # that was reset by test harness, etc.), install the OTEL SDK provider
    # directly so spans are recording.
    _ensure_tracer_provider(service_name)

    _instrument_frameworks()

    if capture == "consented":
        from shared.consent import install_consent_pipeline
        install_consent_pipeline()
    # Stash consent_lookup for later callers that need it.
    global _consent_lookup
    _consent_lookup = consent_lookup

    _INITIALIZED = True
    log.info("Telemetry initialized: service=%s capture=%s", service_name, capture)


_consent_lookup: Callable[[str], Awaitable[bool]] | None = None


def get_consent_lookup() -> Callable[[str], Awaitable[bool]] | None:
    return _consent_lookup


def _ensure_tracer_provider(service_name: str) -> None:
    """Ensure opentelemetry.trace has a real SDK TracerProvider registered.

    Traceloop normally does this, but can be a no-op when an API key is missing
    or when its internal singleton predates an OTEL globals reset (common in
    tests). This installs a plain SDK provider with a BatchSpanProcessor and
    OTLP exporter so spans record and export.
    """
    try:
        from opentelemetry import trace
        provider = trace.get_tracer_provider()
        if type(provider).__name__ not in {"ProxyTracerProvider", "NoOpTracerProvider"}:
            return
        from opentelemetry.sdk.resources import Resource, SERVICE_NAME
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                OTLPSpanExporter,
            )
        except ImportError:
            OTLPSpanExporter = None  # type: ignore[assignment]

        resource = Resource.create({SERVICE_NAME: service_name})
        tp = TracerProvider(resource=resource)
        if OTLPSpanExporter is not None:
            tp.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
        trace.set_tracer_provider(tp)
    except Exception as e:
        log.warning("Fallback TracerProvider setup failed: %s", e)


def _instrument_frameworks() -> None:
    """Lazy-import each instrumentor so missing deps don't break services that
    lack them (e.g. telegram_bot has no asyncpg)."""
    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        HTTPXClientInstrumentor().instrument()
    except ImportError:
        pass
    except Exception as e:
        log.warning("HTTPXClientInstrumentor failed: %s", e)

    try:
        from opentelemetry.instrumentation.asyncpg import AsyncPGInstrumentor
        AsyncPGInstrumentor().instrument()
    except ImportError:
        pass
    except Exception as e:
        log.warning("AsyncPGInstrumentor failed: %s", e)

    try:
        from opentelemetry.instrumentation.logging import LoggingInstrumentor
        LoggingInstrumentor().instrument(set_logging_format=True)
    except ImportError:
        pass
    except Exception as e:
        log.warning("LoggingInstrumentor failed: %s", e)


def instrument_fastapi_app(app) -> None:
    """Call after `app = FastAPI(...)`. Patches the instance."""
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        FastAPIInstrumentor.instrument_app(app)
    except ImportError:
        log.warning("opentelemetry-instrumentation-fastapi not installed")
    except Exception as e:
        log.warning("FastAPIInstrumentor failed: %s", e)


def set_span_user(user_id: str | None = None) -> None:
    """Attach langfuse.user.id to current span. None → LANGFUSE_DEFAULT_USER_ID."""
    from opentelemetry import trace
    span = trace.get_current_span()
    if span is None or not span.is_recording():
        return
    resolved = user_id or os.environ.get("LANGFUSE_DEFAULT_USER_ID", "owner")
    span.set_attribute("langfuse.user.id", resolved)


def set_span_session(session_id: str) -> None:
    """Attach langfuse.session.id to current span."""
    from opentelemetry import trace
    span = trace.get_current_span()
    if span is None or not span.is_recording():
        return
    span.set_attribute("langfuse.session.id", session_id)
