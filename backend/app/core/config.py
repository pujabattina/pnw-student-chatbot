from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


def _env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None:
        return default
    value = value.strip()
    if not value:
        return default
    return value


@dataclass(frozen=True, slots=True)
class AppSettings:
    app_env: str = "development"
    database_url: str = ""
    session_secret_key: str = ""
    worker_shared_secret: str = ""
    model_provider: str | None = None
    model_provider_api_key: str | None = None
    oidc_issuer: str | None = None
    oidc_client_id: str | None = None
    oidc_client_secret: str | None = None
    oidc_redirect_uri: str | None = None
    request_timeout_seconds: int = 5

    @classmethod
    def from_env(cls) -> AppSettings:
        timeout_env = _env("REQUEST_TIMEOUT_SECONDS", "5")
        try:
            timeout_seconds = int(timeout_env) if timeout_env is not None else 5
        except ValueError as exc:  # pragma: no cover - defensive config validation
            raise ValueError("REQUEST_TIMEOUT_SECONDS must be an integer.") from exc

        return cls(
            app_env=_env("APP_ENV", "development") or "development",
            database_url=_env("DATABASE_URL") or "",
            session_secret_key=_env("SESSION_SECRET_KEY") or "",
            worker_shared_secret=_env("WORKER_SHARED_SECRET") or "",
            model_provider=_env("MODEL_PROVIDER"),
            model_provider_api_key=_env("MODEL_PROVIDER_API_KEY"),
            oidc_issuer=_env("OIDC_ISSUER"),
            oidc_client_id=_env("OIDC_CLIENT_ID"),
            oidc_client_secret=_env("OIDC_CLIENT_SECRET"),
            oidc_redirect_uri=_env("OIDC_REDIRECT_URI"),
            request_timeout_seconds=timeout_seconds,
        )

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    def validate(self) -> AppSettings:
        errors: list[str] = []

        if not self.database_url:
            errors.append("DATABASE_URL is required.")
        if not self.session_secret_key:
            errors.append("SESSION_SECRET_KEY is required.")
        if not self.worker_shared_secret:
            errors.append("WORKER_SHARED_SECRET is required.")
        if self.request_timeout_seconds <= 0:
            errors.append("REQUEST_TIMEOUT_SECONDS must be greater than zero.")

        if self.model_provider and not self.model_provider_api_key:
            errors.append("MODEL_PROVIDER_API_KEY is required when MODEL_PROVIDER is set.")
        if self.model_provider_api_key and not self.model_provider:
            errors.append("MODEL_PROVIDER is required when MODEL_PROVIDER_API_KEY is set.")

        oidc_fields = [
            ("OIDC_ISSUER", self.oidc_issuer),
            ("OIDC_CLIENT_ID", self.oidc_client_id),
            ("OIDC_CLIENT_SECRET", self.oidc_client_secret),
            ("OIDC_REDIRECT_URI", self.oidc_redirect_uri),
        ]
        configured_oidc = sum(1 for _, value in oidc_fields if value)
        if configured_oidc:
            missing_fields = [name for name, value in oidc_fields if not value]
            if missing_fields:
                errors.append(
                    "OIDC configuration is incomplete: " + ", ".join(missing_fields) + "."
                )

        if self.is_production:
            required_prod = [
                ("MODEL_PROVIDER", self.model_provider),
                ("MODEL_PROVIDER_API_KEY", self.model_provider_api_key),
                ("OIDC_ISSUER", self.oidc_issuer),
                ("OIDC_CLIENT_ID", self.oidc_client_id),
                ("OIDC_CLIENT_SECRET", self.oidc_client_secret),
                ("OIDC_REDIRECT_URI", self.oidc_redirect_uri),
            ]
            missing_prod = [name for name, value in required_prod if not value]
            if missing_prod:
                errors.append(
                    "Production environment requires configuration for: "
                    + ", ".join(missing_prod)
                    + "."
                )

        if errors:
            raise ValueError("Invalid application configuration: " + "; ".join(errors))

        return self


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    return AppSettings.from_env().validate()
