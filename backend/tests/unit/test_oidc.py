from __future__ import annotations

import time
from urllib.parse import parse_qs, urlparse

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.auth.oidc import build_code_challenge, validate_id_token


def _key_pair() -> tuple[object, dict[str, object]]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_numbers = private_key.public_key().public_numbers()
    jwk: dict[str, object] = {
        "kty": "RSA",
        "kid": "test-key",
        "use": "sig",
        "alg": "RS256",
        "n": jwt.utils.base64url_encode(
            public_numbers.n.to_bytes((public_numbers.n.bit_length() + 7) // 8, "big")
        ).decode(),
        "e": jwt.utils.base64url_encode(
            public_numbers.e.to_bytes((public_numbers.e.bit_length() + 7) // 8, "big")
        ).decode(),
    }
    return private_key, jwk


def _token(
    private_key: object,
    *,
    issuer: str = "https://id.example.edu",
    audience: str = "pnw-client",
    nonce: str = "expected-nonce",
    expires_at: int | None = None,
) -> str:
    now = int(time.time())
    return jwt.encode(
        {
            "iss": issuer,
            "aud": audience,
            "sub": "institutional-subject",
            "iat": now,
            "exp": expires_at or now + 300,
            "nonce": nonce,
        },
        private_key,
        algorithm="RS256",
        headers={"kid": "test-key"},
    )


def test_code_challenge_uses_pkce_s256() -> None:
    assert build_code_challenge("verifier-value") == "GPXfFfmq30W8w5PWMLNtzZR2q9pxnxZ4FkY2A8xIsF4"


def test_id_token_verifies_signature_issuer_audience_expiry_and_nonce() -> None:
    private_key, jwk = _key_pair()
    claims = validate_id_token(
        _token(private_key),
        {"keys": [jwk]},
        issuer="https://id.example.edu",
        audience="pnw-client",
        nonce="expected-nonce",
    )

    assert claims["sub"] == "institutional-subject"
    assert claims["iss"] == "https://id.example.edu"


@pytest.mark.parametrize(
    ("token_options", "expected_nonce"),
    [
        ({"issuer": "https://attacker.example"}, "expected-nonce"),
        ({"audience": "another-client"}, "expected-nonce"),
        ({}, "another-nonce"),
        ({"expires_at": 1}, "expected-nonce"),
    ],
)
def test_id_token_rejects_invalid_claims(
    token_options: dict[str, object],
    expected_nonce: str,
) -> None:
    private_key, jwk = _key_pair()
    with pytest.raises(ValueError):
        validate_id_token(
            _token(private_key, **token_options),
            {"keys": [jwk]},
            issuer="https://id.example.edu",
            audience="pnw-client",
            nonce=expected_nonce,
        )


def test_authorization_request_contains_state_nonce_and_pkce_parameters() -> None:
    from app.auth.oidc import build_authorization_url

    url = build_authorization_url(
        authorization_endpoint="https://id.example.edu/authorize",
        client_id="pnw-client",
        redirect_uri="https://chat.pnw.edu/api/v1/auth/callback",
        state="random-state",
        nonce="random-nonce",
        code_verifier="verifier-value",
    )
    query = parse_qs(urlparse(url).query)

    assert query["response_type"] == ["code"]
    assert query["state"] == ["random-state"]
    assert query["nonce"] == ["random-nonce"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["code_challenge"] == [build_code_challenge("verifier-value")]
