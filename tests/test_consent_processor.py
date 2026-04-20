"""ConsentSpanExporter redacts sensitive attributes for non-consenting users."""
import pytest
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.trace import SpanContext, SpanKind, Status, StatusCode, TraceFlags
from opentelemetry.sdk.trace.export import SpanExportResult


def _make_readable_span(attrs: dict, name="test") -> ReadableSpan:
    ctx = SpanContext(
        trace_id=0x1,
        span_id=0x2,
        is_remote=False,
        trace_flags=TraceFlags(TraceFlags.SAMPLED),
    )
    return ReadableSpan(
        name=name,
        context=ctx,
        parent=None,
        resource=None,
        attributes=attrs,
        events=(),
        links=(),
        kind=SpanKind.INTERNAL,
        status=Status(StatusCode.UNSET),
        start_time=1000,
        end_time=2000,
    )


class _CapturingInner:
    """Inner exporter that captures spans instead of shipping to OTLP."""
    def __init__(self):
        self.captured = []

    def export(self, spans):
        self.captured = list(spans)
        return SpanExportResult.SUCCESS

    def shutdown(self): pass
    def force_flush(self, timeout_millis=30_000): return True


def test_consent_ok_preserves_sensitive_attrs():
    from shared.consent import ConsentSpanExporter
    inner = _CapturingInner()
    exp = ConsentSpanExporter(inner)

    span = _make_readable_span({
        "telemetry.bodies_ok": "1",
        "gen_ai.prompt.0.content": "my blood pressure is 120/80",
        "gen_ai.usage.input_tokens": 42,
        "http.method": "POST",
    })
    exp.export([span])

    out = inner.captured[0]
    assert out.attributes["gen_ai.prompt.0.content"] == "my blood pressure is 120/80"
    assert out.attributes["gen_ai.usage.input_tokens"] == 42
    assert out.attributes["http.method"] == "POST"


def test_consent_denied_redacts_sensitive_attrs():
    from shared.consent import ConsentSpanExporter
    inner = _CapturingInner()
    exp = ConsentSpanExporter(inner)

    span = _make_readable_span({
        "telemetry.bodies_ok": "0",
        "gen_ai.prompt.0.content": "my blood pressure is 120/80",
        "gen_ai.completion.content": "that's normal",
        "traceloop.entity.input": "{\"q\": \"bp\"}",
        "gen_ai.usage.input_tokens": 42,
        "http.method": "POST",
    })
    exp.export([span])

    out = inner.captured[0]
    assert out.attributes["gen_ai.prompt.0.content"] == "[REDACTED]"
    assert out.attributes["gen_ai.completion.content"] == "[REDACTED]"
    assert out.attributes["traceloop.entity.input"] == "[REDACTED]"
    # Non-sensitive: preserved.
    assert out.attributes["gen_ai.usage.input_tokens"] == 42
    assert out.attributes["http.method"] == "POST"


def test_consent_absent_defaults_to_redact():
    from shared.consent import ConsentSpanExporter
    inner = _CapturingInner()
    exp = ConsentSpanExporter(inner)

    span = _make_readable_span({
        # telemetry.bodies_ok not set
        "gen_ai.prompt.0.content": "sensitive",
        "http.method": "GET",
    })
    exp.export([span])

    out = inner.captured[0]
    assert out.attributes["gen_ai.prompt.0.content"] == "[REDACTED]"
    assert out.attributes["http.method"] == "GET"


def test_exporter_handles_none_and_non_string_attrs():
    from shared.consent import ConsentSpanExporter
    inner = _CapturingInner()
    exp = ConsentSpanExporter(inner)

    span = _make_readable_span({
        "telemetry.bodies_ok": "0",
        "gen_ai.usage.input_tokens": 42,  # int
        "gen_ai.usage.cost": 0.01,         # float
    })
    # Should not raise.
    result = exp.export([span])
    assert result == SpanExportResult.SUCCESS


def test_baggage_snapshot_processor_copies_baggage_to_span_attr():
    from shared.consent import BaggageSnapshotProcessor
    from opentelemetry import baggage, context as otel_context, trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    provider = TracerProvider()
    provider.add_span_processor(BaggageSnapshotProcessor())
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    ctx = baggage.set_baggage("telemetry.bodies_ok", "1")
    token = otel_context.attach(ctx)
    try:
        tracer = provider.get_tracer("t")
        with tracer.start_as_current_span("s") as s:
            pass
    finally:
        otel_context.detach(token)

    spans = exporter.get_finished_spans()
    assert spans[0].attributes["telemetry.bodies_ok"] == "1"
