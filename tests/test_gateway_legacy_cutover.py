"""The transitional host no longer overrides private route validation."""

from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from orchestrator.app import main


def test_legacy_body_logging_handler_is_removed():
    assert (
        main.app.exception_handlers[RequestValidationError] is request_validation_exception_handler
    )
