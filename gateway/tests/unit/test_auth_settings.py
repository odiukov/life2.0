import pytest
from fastapi import HTTPException


def test_provider_config_rejects_missing_client():
    from gateway.auth.routes import provider_config
    from gateway.auth.settings import AuthSettings

    with pytest.raises(HTTPException) as error:
        provider_config(AuthSettings(google_auth_client_id=""), "google")
    assert error.value.status_code == 503


def test_refresh_token_has_session_prefix():
    from uuid import uuid4

    from gateway.auth.tokens import InvalidRefreshToken, new_refresh_token, parse_refresh_token

    sid = uuid4()
    token = new_refresh_token(sid)
    assert parse_refresh_token(token)[0] == sid
    with pytest.raises(InvalidRefreshToken):
        parse_refresh_token("malformed")


def test_apple_client_secret_is_signed_for_service_id():
    import jwt
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from gateway.auth.tokens import apple_client_secret

    key = ec.generate_private_key(ec.SECP256R1())
    private_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    signed = apple_client_secret(
        team_id="team-id", key_id="key-id", private_key=private_pem, client_id="service-id"
    )
    claims = jwt.decode(
        signed,
        key.public_key(),
        algorithms=["ES256"],
        audience="https://appleid.apple.com",
        issuer="team-id",
    )
    assert claims["sub"] == "service-id"
    assert jwt.get_unverified_header(signed)["kid"] == "key-id"


@pytest.mark.parametrize(
    "values", [{"auth_mode": "dev", "env": "prod"}, {"auth_jwt_secret": "short"}]
)
def test_invalid_settings_refused(values):
    from gateway.auth.settings import AuthSettings
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        AuthSettings(**values)
