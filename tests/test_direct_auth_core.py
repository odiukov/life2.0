from datetime import UTC, datetime
from uuid import UUID

import jwt
import pytest


def test_google_url_uses_state_nonce_and_pkce():
    from orchestrator.app.direct_auth import provider_authorization_url

    url = provider_authorization_url(
        "google", "client-id", "https://app.test/auth/google/callback", "state", "nonce", "verifier"
    )
    assert "accounts.google.com" in url
    assert "state=state" in url
    assert "nonce=nonce" in url
    assert "code_challenge_method=S256" in url


def test_apple_url_requests_form_post():
    from orchestrator.app.direct_auth import provider_authorization_url

    url = provider_authorization_url(
        "apple", "service-id", "https://app.test/auth/apple/callback", "state", "nonce", "verifier"
    )
    assert "appleid.apple.com" in url
    assert "response_mode=form_post" in url
    assert "code_challenge" not in url


def test_access_token_requires_issuer_audience_and_session():
    from orchestrator.app.direct_auth import issue_access, decode_access

    secret = "x" * 32
    user = UUID("11111111-1111-1111-1111-111111111111")
    sid = UUID("22222222-2222-2222-2222-222222222222")
    token = issue_access(user, sid, secret, now=datetime.now(UTC))
    assert decode_access(token, secret) == (user, sid)
    wrong = jwt.encode(
        {"sub": str(user), "sid": str(sid), "iss": "evil", "aud": "lifeagents", "exp": 9999999999},
        secret,
        algorithm="HS256",
    )
    with pytest.raises(jwt.InvalidTokenError):
        decode_access(wrong, secret)


def test_provider_token_rejects_wrong_nonce():
    from orchestrator.app.direct_auth import decode_provider_identity
    from tests.fixtures.jwt_factory import build, jwks

    with pytest.raises(jwt.InvalidTokenError):
        decode_provider_identity("google", build("123"), "test-client", "expected", jwks())


def test_google_accepts_both_documented_issuer_forms():
    from orchestrator.app.direct_auth import decode_provider_identity
    from tests.fixtures.jwt_factory import build, jwks

    identity = decode_provider_identity(
        "google",
        build("provider-user", iss="accounts.google.com"),
        "test-client",
        "test-nonce",
        jwks(),
    )
    assert identity["subject"] == "provider-user"
