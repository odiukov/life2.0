import pytest
from fastapi import HTTPException


def test_provider_config_rejects_missing_client(monkeypatch):
    from orchestrator.app.auth_routes import provider_config

    monkeypatch.delenv("GOOGLE_AUTH_CLIENT_ID", raising=False)
    with pytest.raises(HTTPException) as error:
        provider_config("google")
    assert error.value.status_code == 503


def test_refresh_token_has_session_prefix():
    from uuid import uuid4
    from orchestrator.app.auth_routes import new_refresh_token, parse_refresh_token

    sid = uuid4()
    token = new_refresh_token(sid)
    assert parse_refresh_token(token)[0] == sid
    with pytest.raises(HTTPException):
        parse_refresh_token("malformed")


def test_apple_client_secret_is_signed_for_service_id(monkeypatch):
    import jwt
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    from orchestrator.app.auth_routes import apple_client_secret

    key = ec.generate_private_key(ec.SECP256R1())
    private_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    monkeypatch.setenv("APPLE_AUTH_TEAM_ID", "team-id")
    monkeypatch.setenv("APPLE_AUTH_KEY_ID", "key-id")
    monkeypatch.setenv("APPLE_AUTH_PRIVATE_KEY", private_pem)
    signed = apple_client_secret("service-id")
    claims = jwt.decode(
        signed,
        key.public_key(),
        algorithms=["ES256"],
        audience="https://appleid.apple.com",
        issuer="team-id",
    )
    assert claims["sub"] == "service-id"
    assert jwt.get_unverified_header(signed)["kid"] == "key-id"
