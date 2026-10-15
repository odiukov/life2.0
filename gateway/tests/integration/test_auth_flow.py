"""OAuth tickets and rotating sessions exercised as app_rw over gateway HTTP."""

from hashlib import sha256
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
import respx
from fastapi import FastAPI
from gateway.auth.settings import AuthSettings
from gateway.composition import build_gateway, mount
from gateway.settings import GatewaySettings
from jwt_factory import build, jwks

pytestmark = pytest.mark.integration


@pytest.fixture
async def client(clean_db):
    gateway = build_gateway(
        GatewaySettings.model_validate({"database": {"dsn": clean_db.rw}}),
        auth=AuthSettings(
            auth_mode="oauth",
            google_auth_client_id="test-client",
            google_auth_client_secret="test-secret",
            auth_public_url="http://localhost:8000",
            auth_jwt_secret="x" * 32,
            apple_auth_service_id="test-client",
        ),
    )
    app = FastAPI()
    mount(app, gateway)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            yield client
    finally:
        await gateway.aclose()


async def sign_in(client, subject="provider-sub"):
    verifier = "private-app-verifier"
    response = await client.get(
        "/auth/google/start", params={"app_challenge": sha256(verifier.encode()).hexdigest()}
    )
    assert response.status_code == 307
    params = parse_qs(urlsplit(response.headers["location"]).query)
    assert params["code_challenge"]
    assert params["code_challenge_method"] == ["S256"]
    with respx.mock:
        respx.post("https://oauth2.googleapis.com/token").respond(
            json={"id_token": build(subject, nonce=params["nonce"][0])}
        )
        respx.get("https://www.googleapis.com/oauth2/v3/certs").respond(json=jwks())
        response = await client.get(
            "/auth/google/callback", params={"state": params["state"][0], "code": "provider-code"}
        )
        replay = await client.get(
            "/auth/google/callback", params={"state": params["state"][0], "code": "provider-code"}
        )
    assert response.status_code == 303
    assert replay.status_code == 401
    ticket = parse_qs(urlsplit(response.headers["location"]).query)["ticket"][0]
    wrong = await client.post("/auth/exchange", json={"ticket": ticket, "app_verifier": "wrong"})
    assert wrong.status_code == 401
    response = await client.post(
        "/auth/exchange", json={"ticket": ticket, "app_verifier": verifier}
    )
    assert response.status_code == 200
    replay = await client.post("/auth/exchange", json={"ticket": ticket, "app_verifier": verifier})
    assert replay.status_code == 401
    return response.json()


async def test_google_callback_ticket_refresh_replay_and_revoke(client):
    session = await sign_in(client)
    refreshed = await client.post("/auth/refresh", json={"refresh_token": session["refresh_token"]})
    assert refreshed.status_code == 200
    assert refreshed.json()["refresh_token"] != session["refresh_token"]
    headers = {"Authorization": "Bearer " + refreshed.json()["access_token"]}
    assert (await client.get("/household", headers=headers)).status_code == 200
    replay = await client.post("/auth/refresh", json={"refresh_token": session["refresh_token"]})
    assert replay.status_code == 401
    assert (await client.get("/household", headers=headers)).status_code == 401


async def test_provider_identity_is_stable(client):
    first = await sign_in(client)
    second = await sign_in(client)
    assert first["user"]["id"] == second["user"]["id"]
    # Separation across providers with the same email is also checked at the SQL boundary.


async def test_sign_out_revokes_the_access_token(client):
    session = await sign_in(client)
    headers = {"Authorization": "Bearer " + session["access_token"]}
    assert (await client.get("/household", headers=headers)).status_code == 200
    assert (await client.post("/auth/sign-out", headers=headers)).status_code == 204
    assert (await client.get("/household", headers=headers)).status_code == 401
