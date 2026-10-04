from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from time import time
from typing import Any
from urllib.parse import urlencode, urlsplit

import httpx
import jwt
from jwt.exceptions import PyJWTError

from app.core.config import AppSettings


class OIDCError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class OIDCProviderMetadata:
    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str

    @classmethod
    def from_json(cls, payload: dict[str, Any], expected_issuer: str) -> OIDCProviderMetadata:
        if payload.get("issuer") != expected_issuer:
            raise OIDCError("Identity provider configuration is invalid.")

        issuer = payload.get("issuer")
        authorization_endpoint = payload.get("authorization_endpoint")
        token_endpoint = payload.get("token_endpoint")
        jwks_uri = payload.get("jwks_uri")
        if (
            not isinstance(issuer, str)
            or not isinstance(authorization_endpoint, str)
            or not isinstance(token_endpoint, str)
            or not isinstance(jwks_uri, str)
            or not all(
                _is_https_url(value)
                for value in (issuer, authorization_endpoint, token_endpoint, jwks_uri)
            )
        ):
            raise OIDCError("Identity provider configuration is invalid.")

        return cls(
            issuer=issuer,
            authorization_endpoint=authorization_endpoint,
            token_endpoint=token_endpoint,
            jwks_uri=jwks_uri,
        )


def _is_https_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
        return parsed.scheme == "https" and bool(parsed.hostname) and parsed.port != 0
    except ValueError:
        return False


def validate_redirect_uri(value: str) -> None:
    try:
        parsed = urlsplit(value)
        is_local_http = parsed.scheme == "http" and parsed.hostname in {
            "localhost",
            "127.0.0.1",
            "::1",
        }
        if not parsed.hostname or (parsed.scheme != "https" and not is_local_http):
            raise ValueError
        _ = parsed.port
    except ValueError as exc:
        raise OIDCError("OIDC redirect URI must use HTTPS.") from exc


def build_code_challenge(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def build_authorization_url(
    *,
    authorization_endpoint: str,
    client_id: str,
    redirect_uri: str,
    state: str,
    nonce: str,
    code_verifier: str,
) -> str:
    validate_redirect_uri(redirect_uri)
    if not _is_https_url(authorization_endpoint):
        raise OIDCError("Identity provider configuration is invalid.")

    parameters = urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid profile",
            "state": state,
            "nonce": nonce,
            "code_challenge": build_code_challenge(code_verifier),
            "code_challenge_method": "S256",
        }
    )
    separator = "&" if "?" in authorization_endpoint else "?"
    return f"{authorization_endpoint}{separator}{parameters}"


def validate_id_token(
    token: str,
    jwks: dict[str, Any],
    *,
    issuer: str,
    audience: str,
    nonce: str,
    now: int | None = None,
) -> dict[str, Any]:
    try:
        header = jwt.get_unverified_header(token)
        key_id = header.get("kid")
        if header.get("alg") != "RS256" or not isinstance(key_id, str):
            raise OIDCError("Identity provider token is invalid.")

        keys = jwks.get("keys")
        if not isinstance(keys, list):
            raise OIDCError("Identity provider signing keys are invalid.")
        jwk = next(
            (
                item
                for item in keys
                if isinstance(item, dict)
                and item.get("kid") == key_id
                and item.get("use", "sig") == "sig"
                and item.get("alg", "RS256") == "RS256"
            ),
            None,
        )
        if jwk is None:
            raise OIDCError("Identity provider signing key is unavailable.")

        signing_key = jwt.PyJWK.from_dict(jwk, algorithm="RS256").key
        claims = jwt.decode(
            token,
            signing_key,
            algorithms=["RS256"],
            audience=audience,
            issuer=issuer,
            options={
                "require": ["exp", "iat", "iss", "aud", "sub", "nonce"],
            },
            leeway=60,
        )
        if now is not None:
            expiration = claims.get("exp")
            if not isinstance(expiration, (int, float)) or expiration <= now:
                raise OIDCError("Identity provider token has expired.")
        actual_nonce = claims.get("nonce")
        if not isinstance(actual_nonce, str) or not hmac.compare_digest(actual_nonce, nonce):
            raise OIDCError("Identity provider token nonce is invalid.")
        if not isinstance(claims.get("sub"), str) or not claims["sub"]:
            raise OIDCError("Identity provider token subject is invalid.")
        return claims
    except OIDCError:
        raise
    except (PyJWTError, TypeError, ValueError, KeyError) as exc:
        raise OIDCError("Identity provider token is invalid.") from exc


class OIDCClient:
    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings
        self._metadata: OIDCProviderMetadata | None = None

    def _configuration(self) -> tuple[str, str, str, str]:
        issuer = self._settings.oidc_issuer
        client_id = self._settings.oidc_client_id
        client_secret = self._settings.oidc_client_secret
        redirect_uri = self._settings.oidc_redirect_uri
        if not issuer or not client_id or not client_secret or not redirect_uri:
            raise OIDCError("Institutional sign-in is not configured.")
        if not _is_https_url(issuer):
            raise OIDCError("Institutional sign-in is not configured.")
        validate_redirect_uri(redirect_uri)
        return issuer, client_id, client_secret, redirect_uri

    async def discover(self) -> OIDCProviderMetadata:
        if self._metadata is not None:
            return self._metadata

        issuer, _, _, _ = self._configuration()
        discovery_url = f"{issuer.rstrip('/')}/.well-known/openid-configuration"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(discovery_url)
                response.raise_for_status()
                payload = response.json()
            if not isinstance(payload, dict):
                raise OIDCError("Identity provider configuration is invalid.")
            self._metadata = OIDCProviderMetadata.from_json(payload, issuer)
            return self._metadata
        except OIDCError:
            raise
        except (httpx.HTTPError, ValueError) as exc:
            raise OIDCError("Identity provider is temporarily unavailable.") from exc

    async def exchange_code(
        self,
        *,
        code: str,
        code_verifier: str,
    ) -> dict[str, Any]:
        _, client_id, client_secret, redirect_uri = self._configuration()
        metadata = await self.discover()
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(
                    metadata.token_endpoint,
                    data={
                        "grant_type": "authorization_code",
                        "code": code,
                        "redirect_uri": redirect_uri,
                        "code_verifier": code_verifier,
                    },
                    auth=(client_id, client_secret),
                )
                response.raise_for_status()
                payload = response.json()
            if not isinstance(payload, dict) or not isinstance(payload.get("id_token"), str):
                raise OIDCError("Identity provider token response is invalid.")
            return payload
        except OIDCError:
            raise
        except (httpx.HTTPError, ValueError) as exc:
            raise OIDCError("Identity provider is temporarily unavailable.") from exc

    async def get_signing_keys(self) -> dict[str, Any]:
        metadata = await self.discover()
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(metadata.jwks_uri)
                response.raise_for_status()
                payload = response.json()
            if not isinstance(payload, dict):
                raise OIDCError("Identity provider signing keys are invalid.")
            return payload
        except OIDCError:
            raise
        except (httpx.HTTPError, ValueError) as exc:
            raise OIDCError("Identity provider is temporarily unavailable.") from exc

    def new_transaction(self) -> dict[str, str]:
        self._configuration()
        return {
            "state": secrets.token_urlsafe(32),
            "nonce": secrets.token_urlsafe(32),
            "code_verifier": secrets.token_urlsafe(64),
        }

    async def authorization_url(self, transaction: dict[str, str]) -> str:
        metadata = await self.discover()
        _, client_id, _, redirect_uri = self._configuration()
        return build_authorization_url(
            authorization_endpoint=metadata.authorization_endpoint,
            client_id=client_id,
            redirect_uri=redirect_uri,
            state=transaction["state"],
            nonce=transaction["nonce"],
            code_verifier=transaction["code_verifier"],
        )

    def validate_token(
        self,
        token: str,
        jwks: dict[str, Any],
        nonce: str,
    ) -> dict[str, Any]:
        issuer, client_id, _, _ = self._configuration()
        return validate_id_token(
            token,
            jwks,
            issuer=issuer,
            audience=client_id,
            nonce=nonce,
            now=int(time()),
        )
