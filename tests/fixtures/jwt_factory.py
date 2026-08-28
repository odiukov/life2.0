"""Builds Supabase-shaped JWTs signed with an ephemeral RSA key for tests.

The keypair is generated once per test session in memory — nothing is written
to disk and no private key material lives in the repository.
"""
from __future__ import annotations

import json
import time
from functools import lru_cache

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

KID = "testkid"
ISSUER = "https://test.supabase.co/auth/v1"
AUDIENCE = "authenticated"


@lru_cache(maxsize=1)
def _keypair() -> tuple[bytes, bytes]:
    """Generate (private_pem, public_pem) once per process."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_pem, public_pem


def build(
    user_id: str,
    aud: str = AUDIENCE,
    iss: str = ISSUER,
    ttl: int = 3600,
    kid: str = KID,
) -> str:
    """Return a signed JWT with Supabase-shaped claims."""
    private_pem, _ = _keypair()
    return jwt.encode(
        {
            "sub": user_id,
            "aud": aud,
            "iss": iss,
            "exp": int(time.time()) + ttl,
            "iat": int(time.time()),
            "role": "authenticated",
        },
        private_pem,
        algorithm="RS256",
        headers={"kid": kid},
    )


def jwks() -> dict:
    """Return a JWKS dict matching the test public key."""
    _, public_pem = _keypair()
    pub = serialization.load_pem_public_key(public_pem)
    jwk = json.loads(RSAAlgorithm.to_jwk(pub))
    jwk.update({"kid": KID, "use": "sig", "alg": "RS256"})
    return {"keys": [jwk]}
