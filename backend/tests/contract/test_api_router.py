from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.api.error_handlers import register_error_handlers
from app.api.router import api_router


class _Connection:
    def __init__(self, failure: Exception | None = None) -> None:
        self.failure = failure

    async def execute(self, _statement: object) -> None:
        if self.failure is not None:
            raise self.failure


class _Engine:
    def __init__(self, failure: Exception | None = None) -> None:
        self.failure = failure

    @asynccontextmanager
    async def connect(self) -> AsyncIterator[_Connection]:
        yield _Connection(self.failure)


def _test_app() -> FastAPI:
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(api_router, prefix="/api/v1")
    return app


def test_health_route_checks_database_readiness() -> None:
    app = _test_app()
    app.state.db_engine = _Engine()

    with TestClient(app) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_route_returns_safe_503_when_database_is_unavailable() -> None:
    app = _test_app()
    app.state.db_engine = _Engine(
        OperationalError("SELECT 1", {}, RuntimeError("private connection details"))
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Service is temporarily unavailable.",
    }
    assert "private connection details" not in response.text


def test_validation_error_is_standardized_and_request_body_is_not_echoed() -> None:
    app = _test_app()

    @app.post("/api/v1/validate")
    async def validate(payload: dict[str, int]) -> dict[str, int]:
        return payload

    with TestClient(app) as client:
        response = client.post("/api/v1/validate", json={"count": "student-private-value"})

    assert response.status_code == 400
    assert response.json()["code"] == "validation_error"
    assert response.json()["detail"][0]["loc"] == ["body", "count"]
    assert "student-private-value" not in response.text


def test_http_503_and_unexpected_errors_return_safe_standard_error() -> None:
    app = _test_app()

    @app.get("/api/v1/unavailable")
    async def unavailable() -> None:
        raise HTTPException(status_code=503, detail="secret internal error")

    @app.get("/api/v1/failure")
    async def failure() -> None:
        raise RuntimeError("secret database URL")

    with TestClient(app, raise_server_exceptions=False) as client:
        unavailable_response = client.get("/api/v1/unavailable")
        failure_response = client.get("/api/v1/failure")

    assert unavailable_response.status_code == 503
    assert unavailable_response.json()["detail"] == "Service is temporarily unavailable."
    assert "secret internal error" not in unavailable_response.text
    assert failure_response.status_code == 503
    assert failure_response.json()["code"] == "service_unavailable"
    assert "secret database URL" not in failure_response.text
