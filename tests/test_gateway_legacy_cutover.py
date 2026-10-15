"""The transitional host does not expose moved route inputs during validation."""

import logging

import pytest
from fastapi.exceptions import RequestValidationError
from starlette.requests import Request

from orchestrator.app import main


@pytest.mark.parametrize("path", ["/integrations/garmin/connect", "/me/profile"])
async def test_moved_routes_validation_never_logs_or_echoes_input(path, caplog):
    private = "private-test-credential"

    async def receive():
        return {"type": "http.request", "body": private.encode(), "more_body": False}

    request = Request({"type": "http", "method": "POST", "path": path, "headers": []}, receive)
    error = RequestValidationError(
        [{"type": "value_error", "loc": ("body", "password"), "input": private}]
    )
    with caplog.at_level(logging.WARNING):
        response = await main._log_validation_error(request, error)
    assert response.status_code == 422
    assert private not in caplog.text
    assert private.encode() not in response.body
