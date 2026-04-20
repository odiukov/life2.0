"""Consent-mode pipeline: ConsentSpanExporter + BaggageSnapshotProcessor.

Redact gen_ai.prompt.*, gen_ai.completion.*, traceloop.entity.{input,output},
llm.prompts.*, llm.response.* when the per-user consent baggage flag is not "1".

The baggage value is copied into a span attribute by BaggageSnapshotProcessor.on_start
because baggage is context-local — it doesn't survive the BatchSpanProcessor queue
between span-start and span-export.
"""
from __future__ import annotations

import logging
from typing import Sequence

from opentelemetry import baggage
from opentelemetry.sdk.trace import ReadableSpan, Span, SpanProcessor
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

log = logging.getLogger(__name__)


class BaggageSnapshotProcessor(SpanProcessor):
    """Copies `telemetry.bodies_ok` baggage value to span.attributes at span-start.

    Must be installed BEFORE the BatchSpanProcessor so every span carries the
    snapshot value by the time it's queued for export.
    """
    def on_start(self, span: Span, parent_context=None) -> None:
        val = baggage.get_baggage("telemetry.bodies_ok", parent_context)
        if val is not None:
            span.set_attribute("telemetry.bodies_ok", str(val))

    def on_end(self, span: ReadableSpan) -> None:
        pass

    def shutdown(self) -> None:
        pass

    def force_flush(self, timeout_millis: int = 30_000) -> bool:
        return True


class ConsentSpanExporter(SpanExporter):
    """Wraps an inner SpanExporter (e.g. OTLPSpanExporter). For spans whose
    `telemetry.bodies_ok` attribute != "1", redacts sensitive attributes before
    forwarding to the inner exporter."""

    SENSITIVE_PREFIXES = (
        "gen_ai.prompt.",
        "gen_ai.completion.",
        "traceloop.entity.input",
        "traceloop.entity.output",
        "llm.prompts.",
        "llm.response.",
    )

    # OTEL GenAI semconv (2024+) emits content via span EVENTS, not attributes:
    # gen_ai.user.message, gen_ai.system.message, gen_ai.assistant.message,
    # gen_ai.tool.message, gen_ai.choice. Their bodies are sensitive too.
    SENSITIVE_EVENT_PREFIXES = (
        "gen_ai.user.message",
        "gen_ai.system.message",
        "gen_ai.assistant.message",
        "gen_ai.tool.message",
        "gen_ai.choice",
    )

    def __init__(self, inner: SpanExporter):
        self._inner = inner

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        processed = [self._maybe_redact(s) for s in spans]
        return self._inner.export(processed)

    def _maybe_redact(self, span: ReadableSpan) -> ReadableSpan:
        attrs = span.attributes or {}
        if attrs.get("telemetry.bodies_ok") == "1":
            return span
        redacted_attrs = {
            k: ("[REDACTED]" if any(k.startswith(p) for p in self.SENSITIVE_PREFIXES) else v)
            for k, v in attrs.items()
        }
        redacted_events = tuple(
            self._redact_event(e) for e in (span.events or ())
        )
        return ReadableSpan(
            name=span.name,
            context=span.context,
            parent=span.parent,
            resource=span.resource,
            attributes=redacted_attrs,
            events=redacted_events,
            links=span.links,
            kind=span.kind,
            status=span.status,
            start_time=span.start_time,
            end_time=span.end_time,
            instrumentation_scope=span.instrumentation_scope,
        )

    def _redact_event(self, event):
        name = getattr(event, "name", "") or ""
        if not any(name.startswith(p) for p in self.SENSITIVE_EVENT_PREFIXES):
            return event
        # Build a new Event with redacted attributes but preserved name/timestamp.
        from opentelemetry.sdk.trace import Event
        ev_attrs = dict(getattr(event, "attributes", None) or {})
        redacted = {k: "[REDACTED]" for k in ev_attrs}
        return Event(name=name, attributes=redacted, timestamp=getattr(event, "timestamp", None))

    def shutdown(self) -> None:
        self._inner.shutdown()

    def force_flush(self, timeout_millis: int = 30_000) -> bool:
        return self._inner.force_flush(timeout_millis)


def install_consent_pipeline() -> None:
    """Install BaggageSnapshotProcessor on the active TracerProvider and replace
    the exporter in any BatchSpanProcessor that targets OTEL with a
    ConsentSpanExporter wrapper.

    Called from `shared.telemetry.init_telemetry` when
    TELEMETRY_CAPTURE_BODIES=consented.
    """
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider

    provider = trace.get_tracer_provider()
    if not isinstance(provider, TracerProvider):
        log.warning("install_consent_pipeline: TracerProvider is not SDK type; skipping")
        return

    provider.add_span_processor(BaggageSnapshotProcessor())

    # Walk the provider's active MultiSpanProcessor, find BatchSpanProcessor
    # instances, and wrap their exporter with ConsentSpanExporter. This depends
    # on SDK internals but the layout has been stable since opentelemetry-sdk 1.20.
    multi_processor = getattr(provider, "_active_span_processor", None)
    if multi_processor is None:
        log.warning("install_consent_pipeline: no active span processor found")
        return
    span_processors = getattr(multi_processor, "_span_processors", None)
    if span_processors is None:
        log.warning("install_consent_pipeline: no _span_processors accessor")
        return

    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    for sp in span_processors:
        if not isinstance(sp, BatchSpanProcessor):
            continue
        # SDK 1.27+: actual exporter lives on sp._batch_processor._exporter
        # (sp.span_exporter is a read-only property). Fall back to the
        # property name for older SDKs where it was still writable.
        bp = getattr(sp, "_batch_processor", None)
        if bp is not None and hasattr(bp, "_exporter"):
            inner = bp._exporter
            if inner is not None and not isinstance(inner, ConsentSpanExporter):
                bp._exporter = ConsentSpanExporter(inner)
                log.info(
                    "install_consent_pipeline: wrapped BatchProcessor._exporter with ConsentSpanExporter"
                )
                continue
        inner = getattr(sp, "span_exporter", None)
        if inner is not None and not isinstance(inner, ConsentSpanExporter):
            try:
                sp.span_exporter = ConsentSpanExporter(inner)
                log.info("install_consent_pipeline: wrapped span_exporter (legacy path)")
            except AttributeError:
                log.warning(
                    "install_consent_pipeline: could not wrap exporter — "
                    "neither _batch_processor._exporter nor span_exporter is mutable"
                )
