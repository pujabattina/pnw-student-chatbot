from __future__ import annotations

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from starlette.middleware.sessions import SessionMiddleware

from app.auth import session as session_routes
from app.auth.rbac import require_roles
from app.auth.session import router as auth_router
from app.core.config import AppSettings
from app.db.models.reviewer import ReviewerRole


class _RolesResult:
    def scalars(self) -> _RolesResult:
        return self

    def all(self) -> list[ReviewerRole]:
        return [ReviewerRole.REVIEWER]


class _DatabaseSession:
    async def __aenter__(self) -> _DatabaseSession:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def execute(self, _statement: object) -> _RolesResult:
        return _RolesResult()


class _SessionFactory:
    def __call__(self) -> _DatabaseSession:
        return _DatabaseSession()


class _OIDCClient:
    def __init__(self, _settings: AppSettings) -> None:
        pass

    def new_transaction(self) -> dict[str, str]:
        return {
            "state": "expected-state",
            "nonce": "expected-nonce",
            "code_verifier": "expected-verifier",
        }

    async def authorization_url(self, transaction: dict[str, str]) -> str:
        assert transaction["state"] == "expected-state"
        return "https://id.example.edu/authorize?state=expected-state"

    async def exchange_code(self, *, code: str, code_verifier: str) -> dict[str, str]:
        assert code == "valid-code"
        assert code_verifier == "expected-verifier"
        return {"id_token": "signed-id-token"}

    async def get_signing_keys(self) -> dict[str, object]:
        return {"keys": []}

    def validate_token(
        self,
        token: str,
        _jwks: dict[str, object],
        nonce: str,
    ) -> dict[str, object]:
        assert token == "signed-id-token"
        assert nonce == "expected-nonce"
        return {"sub": "institutional-subject", "exp": 4_000_000_000}


def _test_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(
        SessionMiddleware,
        secret_key="test-session-secret",
        session_cookie="pnw_reviewer_session",
        same_site="lax",
        https_only=True,
        path="/api/v1",
    )
    app.include_router(auth_router, prefix="/api/v1")

    @app.get("/api/v1/reviewer-check")
    async def reviewer_check(
        _subject: str = Depends(require_roles(ReviewerRole.REVIEWER)),
    ) -> dict[str, str]:
        return {"status": "authorized"}

    @app.get("/api/v1/owner-check")
    async def owner_check(
        _subject: str = Depends(require_roles(ReviewerRole.SOURCE_OWNER)),
    ) -> dict[str, str]:
        return {"status": "authorized"}

    app.state.settings = AppSettings(
        database_url="postgresql+asyncpg://localhost/test",
        session_secret_key="test-session-secret",
        worker_shared_secret="worker-secret",
        oidc_issuer="https://id.example.edu",
        oidc_client_id="pnw-client",
        oidc_client_secret="client-secret",
        oidc_redirect_uri="https://chat.pnw.edu/api/v1/auth/callback",
    )
    app.state.db_session_factory = _SessionFactory()
    return app


def test_login_callback_and_current_reviewer_use_session_and_database_roles(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(session_routes, "OIDCClient", _OIDCClient)
    with TestClient(_test_app(), base_url="https://chat.pnw.edu") as client:
        login = client.get("/api/v1/auth/login", follow_redirects=False)
        assert login.status_code == 302
        assert login.headers["location"].startswith("https://id.example.edu/authorize?")
        assert "pnw_reviewer_session" in login.headers["set-cookie"]

        callback = client.get(
            "/api/v1/auth/callback",
            params={"code": "valid-code", "state": "expected-state"},
            follow_redirects=False,
        )
        assert callback.status_code == 303
        assert "secure" in callback.headers["set-cookie"].lower()
        assert "httponly" in callback.headers["set-cookie"].lower()

        current = client.get("/api/v1/auth/me")
        assert current.status_code == 200
        assert current.json() == {
            "subject": "institutional-subject",
            "roles": ["reviewer"],
        }
        assert client.get("/api/v1/reviewer-check").json() == {"status": "authorized"}
        assert client.get("/api/v1/owner-check").status_code == 403

        logout = client.post("/api/v1/auth/logout")
        assert logout.status_code == 204
        assert client.get("/api/v1/auth/me").status_code == 401


def test_callback_rejects_state_mismatch_and_clears_transaction(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(session_routes, "OIDCClient", _OIDCClient)
    with TestClient(_test_app(), base_url="https://chat.pnw.edu") as client:
        client.get("/api/v1/auth/login", follow_redirects=False)
        callback = client.get(
            "/api/v1/auth/callback",
            params={"code": "valid-code", "state": "attacker-state"},
        )

    assert callback.status_code == 400
    assert "attacker-state" not in callback.text
