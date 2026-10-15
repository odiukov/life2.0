import json
from uuid import uuid4

import httpx
import pytest
from orchestrator.adapters.sync import HttpHealthSync
from orchestrator.application.ports import SyncUnavailable


async def test_sync_posts_user_and_returns_service_results() -> None:
    user = uuid4()
    results = [{"service": "garmin", "status": "ok", "written": 3}]

    def respond(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url == "http://sync/sync/user"
        assert json.loads(request.content) == {"user_id": str(user)}
        return httpx.Response(200, json={"results": results})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        assert await HttpHealthSync(http, "http://sync/").sync_user(user) == results


@pytest.mark.parametrize(
    "body",
    [
        None,
        [],
        {},
        {"results": None},
        {"results": "bad"},
        {"results": [1]},
        {"results": [{}]},
        {"results": [{"service": 1, "status": "ok", "written": 0}]},
    ],
)
async def test_malformed_results_are_unavailable(body: object) -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=body))
    ) as http:
        with pytest.raises(SyncUnavailable):
            await HttpHealthSync(http, "http://sync").sync_user(uuid4())


async def test_http_error_is_sanitized() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(503, text="secret provider text"))
    ) as http:
        with pytest.raises(SyncUnavailable) as error:
            await HttpHealthSync(http, "http://sync").sync_user(uuid4())
    assert "secret" not in str(error.value)
