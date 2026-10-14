"""structlog setup: JSON (containers) or console (TTY), trace ids on every line, private errors."""

from __future__ import annotations

import logging
import re
import sys
from collections.abc import Iterator, MutableMapping
from contextlib import contextmanager
from typing import Any

import structlog
from opentelemetry import trace

from shared.config import TelemetrySettings

_HANDLER_NAME = "shared.structlog"
_STRING_FIELDS = frozenset(
    {
        "service_name",
        "agent",
        "skill_id",
        "user_id",
        "task_id",
        "context_id",
        "peer",
        "provider",
        "model",
        "state",
        "error_type",
        "exc_type",
        "trace_id",
        "span_id",
        "logger",
        "level",
        "timestamp",
    }
)
_METRIC_FIELDS = frozenset(
    {
        "items",
        "count",
        "attempt",
        "attempts",
        "retry_attempt",
        "duration_ms",
        "elapsed_s",
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "status_code",
    }
)


class _PrivateStreamHandler(logging.StreamHandler[Any]):
    def handleError(self, record: logging.LogRecord) -> None:  # noqa: N802
        # ProcessorFormatter sanitizes a copy; the original record is still private.
        # Never send it or the exception text to logging's default stderr diagnostic.
        if record.levelno < logging.INFO:
            super().handleError(record)
            return
        if logging.raiseExceptions:
            try:
                sys.stderr.write("logging_sink_failed\n")
            except (OSError, ValueError):
                pass


def _add_trace_ids(
    logger: Any, method_name: str, event: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    context = trace.get_current_span().get_span_context()
    event["trace_id"] = format(context.trace_id, "032x") if context.is_valid else None
    event["span_id"] = format(context.span_id, "016x") if context.is_valid else None
    return event


def _private_errors(
    logger: Any, method_name: str, event: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """INFO+ accepts identifiers and known scalar metadata; bodies belong in traces.

    Callers must use literal event names and trusted identifiers for string metadata.
    An identifier pattern cannot distinguish every possible user message.
    """
    if method_name == "debug":
        return event
    exc_info = event.pop("exc_info", None)
    if exc_info is True:
        exc_info = sys.exc_info()
    if isinstance(exc_info, BaseException):
        event.setdefault("error_type", type(exc_info).__name__)
    elif isinstance(exc_info, tuple) and len(exc_info) == 3 and exc_info[0] is not None:
        event.setdefault("error_type", exc_info[0].__name__)
    for key, value in list(event.items()):
        if key in {"event", "_record", "_from_structlog"}:
            continue
        if key in _STRING_FIELDS and (isinstance(value, str) or value is None):
            continue
        if key in _METRIC_FIELDS and isinstance(value, int | float | bool):
            continue
        event.pop(key, None)
    if event.get("_from_structlog") is False:
        event["event"] = "stdlib_log"
        event.pop("positional_args", None)
    elif not isinstance(event.get("event"), str) or not re.fullmatch(
        r"[A-Za-z0-9_.:-]+", event["event"]
    ):
        event["event"] = "structured_log"
    return event


def configure_logging(settings: TelemetrySettings) -> None:
    level = logging.getLevelNamesMapping()[settings.log_level]
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        _add_trace_ids,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
    ]
    renderer: Any = (
        structlog.processors.JSONRenderer(ensure_ascii=False)
        if settings.log_format == "json"
        else structlog.dev.ConsoleRenderer()
    )
    handler = _PrivateStreamHandler()
    handler.set_name(_HANDLER_NAME)
    handler.setLevel(level)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            # Formatting untrusted vendor args can fail before privacy processors run;
            # logging.handleError would then print the raw message and arguments.
            use_get_message=False,
            pass_foreign_args=True,
            foreign_pre_chain=shared_processors,
            processors=[
                _private_errors,
                structlog.stdlib.PositionalArgumentsFormatter(),
                structlog.processors.format_exc_info,
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                renderer,
            ],
        )
    )
    root = logging.getLogger()
    # Existing output handlers can bypass redaction (including propagate=False loggers).
    # Configure logging once, before services start: all output uses this privacy pipeline.
    root.handlers = [handler]
    for logger in logging.Logger.manager.loggerDict.values():
        if isinstance(logger, logging.Logger):
            logger.handlers = []
            logger.propagate = True
    # A later handlerless logger can disable propagation and fall back here.
    logging.lastResort = handler
    root.setLevel(level)
    structlog.configure(
        processors=[*shared_processors, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.make_filtering_bound_logger(level),
        cache_logger_on_first_use=False,
    )


def get_logger(name: str) -> Any:
    return structlog.get_logger(name)


@contextmanager
def logging_context(**values: Any) -> Iterator[None]:
    tokens = structlog.contextvars.bind_contextvars(**values)
    try:
        yield
    finally:
        structlog.contextvars.reset_contextvars(**tokens)
