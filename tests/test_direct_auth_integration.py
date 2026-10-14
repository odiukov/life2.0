"""A provider callback creates a profile and a revocable application session."""

from urllib.parse import parse_qs, urlsplit
from hashlib import sha256

import pytest
import respx
from fastapi import HTTPException

from tests.fixtures.jwt_factory import build, jwks

pytestmark = pytest.mark.integration


async def test_google_callback_ticket_refresh_replay_and_revoke(monkeypatch):
    from orchestrator.app import auth, auth_routes
    from orchestrator.app.direct_auth import token_hash
    from shared.db import close_db_pool, get_pool

    monkeypatch.setenv("GOOGLE_AUTH_CLIENT_ID", "test-client")
    monkeypatch.setenv("GOOGLE_AUTH_CLIENT_SECRET", "test-secret")
    monkeypatch.setenv("AUTH_PUBLIC_URL", "http://localhost:8000")
    monkeypatch.setenv("AUTH_JWT_SECRET", "x" * 32)
    monkeypatch.setattr(auth, "AUTH_MODE", "oauth")
    monkeypatch.setattr(auth, "POST_AUTH_HOOKS", [])
    await close_db_pool()
    pool = await get_pool()
    try:
        verifier = "private-app-verifier"
        challenge = sha256(verifier.encode()).hexdigest()
        await pool.execute(
            "INSERT INTO auth_flows (state_hash,provider,code_verifier,nonce,app_challenge,expires_at) "
            "VALUES ($1,'google','verifier','test-nonce',$2,now() + interval '5 minutes')",
            token_hash("state"),
            challenge,
        )
        with respx.mock:
            respx.post("https://oauth2.googleapis.com/token").respond(
                json={"id_token": build("provider-sub")}
            )
            respx.get("https://www.googleapis.com/oauth2/v3/certs").respond(json=jwks())
            redirect = await auth_routes.google_callback("state", "provider-code")
        ticket = parse_qs(urlsplit(redirect.headers["location"]).query)["ticket"][0]
        with pytest.raises(HTTPException):
            await auth_routes.exchange(auth_routes.TicketBody(ticket=ticket, app_verifier="wrong"))
        session = await auth_routes.exchange(
            auth_routes.TicketBody(ticket=ticket, app_verifier=verifier)
        )
        assert session["user"]["id"]
        with pytest.raises(HTTPException):
            await auth_routes.exchange(auth_routes.TicketBody(ticket=ticket, app_verifier=verifier))
        refreshed = await auth_routes.refresh(
            auth_routes.RefreshBody(refresh_token=session["refresh_token"])
        )
        assert refreshed["refresh_token"] != session["refresh_token"]
        assert await auth.current_user("Bearer " + refreshed["access_token"], None)
        with pytest.raises(HTTPException):
            await auth_routes.refresh(
                auth_routes.RefreshBody(refresh_token=session["refresh_token"])
            )
        with pytest.raises(HTTPException):
            await auth.current_user("Bearer " + refreshed["access_token"], None)
    finally:
        await close_db_pool()


async def test_google_and_apple_with_same_email_have_separate_profiles():
    from orchestrator.app.auth_routes import _find_or_create_user
    from shared.db import close_db_pool

    await close_db_pool()
    identity = {"subject": "provider-sub", "email": "same@example.test", "name": "Example"}
    try:
        google = await _find_or_create_user("google", identity)
        assert await _find_or_create_user("google", identity) == google
        apple = await _find_or_create_user("apple", identity)
        assert apple != google
    finally:
        await close_db_pool()


async def test_sign_out_revokes_the_access_token(monkeypatch):
    from uuid import uuid4

    from orchestrator.app import auth, auth_routes
    from orchestrator.app.direct_auth import issue_access, token_hash
    from shared.db import close_db_pool, get_pool

    monkeypatch.setenv("AUTH_JWT_SECRET", "x" * 32)
    monkeypatch.setattr(auth, "AUTH_MODE", "oauth")
    monkeypatch.setattr(auth, "POST_AUTH_HOOKS", [])
    await close_db_pool()
    pool = await get_pool()
    try:
        user = uuid4()
        sid = uuid4()
        await pool.execute("INSERT INTO users (id,name) VALUES ($1,'test')", user)
        await pool.execute(
            "INSERT INTO auth_sessions (id,user_id,refresh_hash,expires_at) "
            "VALUES ($1,$2,$3,now() + interval '1 day')",
            sid,
            user,
            token_hash("refresh"),
        )
        bearer = "Bearer " + issue_access(user, sid, "x" * 32)
        assert await auth.current_user(bearer, None) == user
        await auth_routes.sign_out(bearer)
        with pytest.raises(HTTPException):
            await auth.current_user(bearer, None)
    finally:
        await close_db_pool()
