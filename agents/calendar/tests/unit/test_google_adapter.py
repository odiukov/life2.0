import httpx
import pytest
import respx
from calendar_agent.adapters.google import API, TOKEN_URL, HttpGoogleCalendar, HttpGoogleOAuth
from calendar_agent.application.ports import (
    CalendarAuthError,
    CalendarUnavailable,
    EventGone,
    InvalidGrant,
    PreconditionFailed,
)


@pytest.fixture
async def http():
    async with httpx.AsyncClient() as client:
        yield client


@respx.mock
async def test_invalid_grant_is_distinguished_from_outages(http) -> None:
    oauth = HttpGoogleOAuth(http, client_id="id", client_secret=None, redirect_uri="app:/cb")
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(400, json={"error": "invalid_grant"}))
    with pytest.raises(InvalidGrant):
        await oauth.refresh("r")
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(503))
    with pytest.raises(CalendarUnavailable):
        await oauth.refresh("r")
    respx.post(TOKEN_URL).mock(side_effect=httpx.ConnectError("down"))
    with pytest.raises(CalendarUnavailable):
        await oauth.refresh("r")


@respx.mock
async def test_refresh_parses_tokens_and_sends_no_secret_when_unset(http) -> None:
    route = respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "a2", "expires_in": 1200})
    )
    tokens = await HttpGoogleOAuth(
        http, client_id="id", client_secret=None, redirect_uri="x"
    ).refresh("r")
    assert (tokens.access_token, tokens.refresh_token, tokens.expires_in) == ("a2", None, 1200)
    assert b"client_secret" not in route.calls.last.request.content


@respx.mock
async def test_patch_sends_if_match_and_maps_statuses(http) -> None:
    google = HttpGoogleCalendar(http)
    route = respx.patch(f"{API}/ev%2F1").mock(return_value=httpx.Response(200, json={"id": "ev/1"}))
    await google.patch_event("t", "ev/1", {"summary": "x"}, '"7"')
    assert route.calls.last.request.headers["If-Match"] == '"7"'
    for status, error in (
        (412, PreconditionFailed),
        (404, EventGone),
        (401, CalendarAuthError),
        (500, CalendarUnavailable),
    ):
        respx.delete(f"{API}/e").mock(return_value=httpx.Response(status))
        with pytest.raises(error):
            await google.delete_event("t", "e", '"1"')


@respx.mock
@pytest.mark.parametrize("error", ["invalid_request", "unauthorized_client", "invalid_client"])
async def test_refresh_configuration_errors_do_not_revoke_connection(http, error) -> None:
    oauth = HttpGoogleOAuth(http, client_id="id", client_secret=None, redirect_uri="app:/cb")
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(400, json={"error": error}))
    with pytest.raises(CalendarUnavailable):
        await oauth.refresh("r")
