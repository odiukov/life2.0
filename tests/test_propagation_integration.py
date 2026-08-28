"""Cross-service traceparent propagation via httpx + FastAPI auto-instrumentors."""
import pytest
import httpx


@pytest.fixture(autouse=True)
def reset_telemetry():
    import shared.telemetry as t
    t._INITIALIZED = False
    from opentelemetry.test.globals_test import reset_trace_globals
    reset_trace_globals()
    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        HTTPXClientInstrumentor().uninstrument()
    except Exception:
        pass
    yield
    t._INITIALIZED = False
    reset_trace_globals()


@pytest.mark.asyncio
async def test_trace_id_propagates_from_caller_to_callee(monkeypatch):
    from fastapi import FastAPI
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    from opentelemetry import trace

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    HTTPXClientInstrumentor().instrument()

    app_b = FastAPI()

    @app_b.get("/callee")
    def callee():
        return {"ok": True}

    FastAPIInstrumentor.instrument_app(app_b)

    app_a = FastAPI()

    @app_a.get("/caller")
    async def caller():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app_b), base_url="http://b") as c:
            r = await c.get("/callee")
            return r.json()

    FastAPIInstrumentor.instrument_app(app_a)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app_a), base_url="http://a") as client_outer:
        r = await client_outer.get("/caller")
        assert r.status_code == 200

    provider.force_flush()
    spans = exporter.get_finished_spans()
    trace_ids = {s.context.trace_id for s in spans}
    assert len(trace_ids) == 1, f"Expected 1 trace, got {len(trace_ids)}: spans = {[(s.name, s.context.trace_id) for s in spans]}"
