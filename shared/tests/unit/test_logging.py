import json
import logging
from collections.abc import Iterator
from typing import Literal

import pytest
import structlog
from shared.config import TelemetrySettings
from shared.observability.logging import configure_logging, get_logger, logging_context


def lines(err: str) -> list[dict[str, object]]:
    return [json.loads(line) for line in err.strip().splitlines() if line.startswith("{")]


def test_json_lines_carry_trace_fields_and_context(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(TelemetrySettings(log_level="INFO", log_format="json"))
    with logging_context(agent="nutrition"):
        get_logger("t").info("meal_logged", items=2)
    record = lines(capsys.readouterr().err)[-1]
    assert record["event"] == "meal_logged"
    assert record["agent"] == "nutrition"
    assert record["items"] == 2
    assert "trace_id" in record
    assert "span_id" in record


def test_vendor_messages_are_redacted_above_debug(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(TelemetrySettings(log_level="INFO", log_format="json"))
    logging.getLogger("httpx").warning("POST body=%s", "secret user text")
    record = lines(capsys.readouterr().err)[-1]
    assert record["event"] == "stdlib_log"
    assert "secret user text" not in json.dumps(record, ensure_ascii=False)


def test_exceptions_keep_only_their_type(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(TelemetrySettings(log_level="INFO", log_format="json"))
    try:
        raise ValueError("contains user text")
    except ValueError:
        get_logger("t").exception("skill_failed")
    record = lines(capsys.readouterr().err)[-1]
    assert record["error_type"] == "ValueError"
    assert "contains user text" not in json.dumps(record, ensure_ascii=False)
    structlog.reset_defaults()


@pytest.fixture(autouse=True)
def restore_logging() -> Iterator[None]:
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    last_resort = logging.lastResort
    config = structlog.get_config().copy()
    saved = [
        (logger, logger.handlers[:], logger.propagate)
        for logger in logging.Logger.manager.loggerDict.values()
        if isinstance(logger, logging.Logger)
    ]
    yield
    root.handlers, root.level = handlers, level
    logging.lastResort = last_resort
    for logger, prior_handlers, propagate in saved:
        logger.handlers, logger.propagate = prior_handlers, propagate
    structlog.configure(**config)
    structlog.contextvars.clear_contextvars()


@pytest.mark.parametrize("log_format", ["json", "console"])
def test_all_existing_output_handlers_obey_privacy(
    capsys: pytest.CaptureFixture[str], log_format: Literal["json", "console"]
) -> None:
    import sys

    root = logging.getLogger()
    root.addHandler(logging.StreamHandler(sys.stdout))
    vendor = logging.getLogger("privacy.vendor")
    vendor.addHandler(logging.StreamHandler(sys.stderr))
    vendor.propagate = False
    configure_logging(TelemetrySettings(log_level="INFO", log_format=log_format))
    try:
        raise ValueError("secret exception text")
    except ValueError:
        vendor.exception("secret user body: %s", "secret LLM output")
    captured = capsys.readouterr()
    output = captured.out + captured.err
    assert "stdlib_log" in output
    assert "ValueError" in output
    assert "secret" not in output
    assert "Traceback" not in output


def test_structured_sensitive_values_are_private(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(TelemetrySettings(log_level="INFO"))
    get_logger("t").info(
        "llm_finished",
        user_message="secret user text",
        llm_output="secret response",
        prompt="secret prompt",
        body={"text": "secret body"},
        error=ValueError("secret error"),
        items=2,
    )
    captured = capsys.readouterr()
    assert "secret" not in captured.out + captured.err
    assert lines(captured.err)[-1]["items"] == 2


def test_debug_vendor_messages_remain_visible(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(TelemetrySettings(log_level="DEBUG"))
    logging.getLogger("httpx").debug("body=%s", "debug text")
    assert "debug text" in capsys.readouterr().err


def test_info_is_private_even_when_debug_enabled(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(TelemetrySettings(log_level="DEBUG"))
    logging.getLogger("httpx").info("body=%s", "secret text")
    assert "secret text" not in capsys.readouterr().err


def test_logging_context_restores_outer_and_clears(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(TelemetrySettings())
    with logging_context(agent="sleep"):
        with logging_context(agent="nutrition"):
            get_logger("t").info("inner")
        get_logger("t").info("outer")
    get_logger("t").info("cleared")
    records = lines(capsys.readouterr().err)
    assert [record.get("agent") for record in records] == ["nutrition", "sleep", None]


def test_trace_ids_follow_current_span(capsys: pytest.CaptureFixture[str]) -> None:
    from opentelemetry import trace

    context = trace.SpanContext(
        trace_id=0x1234, span_id=0xABCD, is_remote=False, trace_flags=trace.TraceFlags(1)
    )
    configure_logging(TelemetrySettings())
    with trace.use_span(trace.NonRecordingSpan(context)):
        get_logger("t").info("traced")
        logging.getLogger("httpx").warning("vendor warning")
    records = lines(capsys.readouterr().err)
    assert len(records) == 2
    for record in records:
        assert record["trace_id"] == "00000000000000000000000000001234"
        assert record["span_id"] == "000000000000abcd"


def test_repeated_configuration_does_not_duplicate_output(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging(TelemetrySettings())
    configure_logging(TelemetrySettings())
    get_logger("t").info("once")
    assert len(lines(capsys.readouterr().err)) == 1


def test_unapproved_fields_and_free_text_event_are_private(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging(TelemetrySettings())
    get_logger("t").info(
        "secret user event text",
        arbitrary="secret LLM body",
        payload={"nested": {"text": "secret text"}},
        items="secret non-numeric metric",
        user_id="user-123",
        count=2,
    )
    captured = capsys.readouterr()
    assert "secret" not in captured.out + captured.err
    record = lines(captured.err)[-1]
    assert record["event"] == "structured_log"
    assert record["user_id"] == "user-123"
    assert record["count"] == 2


def test_existing_non_output_handler_cannot_retain_private_records() -> None:
    from logging.handlers import BufferingHandler

    buffered = BufferingHandler(10)
    logging.getLogger().addHandler(buffered)
    configure_logging(TelemetrySettings())
    logging.getLogger("vendor").warning("secret body")
    assert buffered.buffer == []


def test_debug_structured_fields_and_exceptions_remain_visible(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging(TelemetrySettings(log_level="DEBUG"))
    try:
        raise ValueError("debug exception")
    except ValueError:
        get_logger("t").debug("debug_event", arbitrary="debug response", exc_info=True)
    output = capsys.readouterr().err
    assert "debug response" in output
    assert "debug exception" in output


def test_invalid_vendor_interpolation_cannot_leak_via_logging_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging(TelemetrySettings())
    logging.getLogger("vendor").warning("secret body %d", "secret response")
    captured = capsys.readouterr()
    assert "secret" not in captured.out + captured.err
    assert lines(captured.err)[-1]["event"] == "stdlib_log"


def test_configured_level_filters_vendor_with_explicit_debug_level(
    capsys: pytest.CaptureFixture[str],
) -> None:
    vendor = logging.getLogger("vendor.explicit_debug")
    previous_level = vendor.level
    try:
        vendor.setLevel(logging.DEBUG)
        configure_logging(TelemetrySettings(log_level="INFO"))
        vendor.debug("debug body")
        assert capsys.readouterr().err == ""
    finally:
        vendor.setLevel(previous_level)


@pytest.mark.parametrize("log_format", ["json", "console"])
@pytest.mark.parametrize("level", [logging.WARNING, logging.ERROR])
@pytest.mark.parametrize("created_after_configure", [False, True])
def test_handlerless_non_propagating_loggers_obey_privacy(
    capsys: pytest.CaptureFixture[str],
    log_format: Literal["json", "console"],
    level: int,
    created_after_configure: bool,
) -> None:
    name = f"privacy.handlerless.{log_format}.{level}.{created_after_configure}"
    if created_after_configure:
        configure_logging(TelemetrySettings(log_format=log_format))
    vendor = logging.getLogger(name)
    vendor.handlers = []
    vendor.propagate = False
    if not created_after_configure:
        configure_logging(TelemetrySettings(log_format=log_format))
    try:
        raise ValueError("secret exception text")
    except ValueError:
        vendor.log(level, "secret user body=%s", "secret LLM output", exc_info=True)
    captured = capsys.readouterr()
    output = captured.out + captured.err
    assert "stdlib_log" in output
    assert "ValueError" in output
    assert "secret" not in output
    assert "Traceback" not in output
    if log_format == "json":
        records = lines(captured.err)
        assert len(records) == 1
        assert records[0]["level"] == logging.getLevelName(level).lower()
        assert "trace_id" in records[0]
        assert "span_id" in records[0]


@pytest.mark.parametrize("log_level", ["INFO", "DEBUG"])
def test_last_resort_respects_configured_level_and_debug_policy_after_reconfiguration(
    capsys: pytest.CaptureFixture[str], log_level: Literal["INFO", "DEBUG"]
) -> None:
    configure_logging(TelemetrySettings(log_level=log_level))
    configure_logging(TelemetrySettings(log_level=log_level))
    vendor = logging.getLogger(f"privacy.last_resort.debug.{log_level}")
    vendor.handlers = []
    vendor.propagate = False
    prior_level = vendor.level
    try:
        vendor.setLevel(logging.DEBUG)
        vendor.debug("body=%s", "debug user text")
        captured = capsys.readouterr()
        if log_level == "DEBUG":
            records = lines(captured.err)
            assert len(records) == 1
            assert records[0]["event"] == "body=debug user text"
        else:
            assert captured.out + captured.err == ""
    finally:
        vendor.setLevel(prior_level)
