from __future__ import annotations

import asyncio
import os
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import RequestResponseEndpoint
from starlette.middleware.sessions import SessionMiddleware

from app.api.error_handlers import register_error_handlers
from app.api.router import api_router
from app.core.config import get_settings
from app.core.database import database_lifespan
from app.telemetry.aggregates import TelemetryAggregates
from app.telemetry.logging import install_privacy_log_filter
from app.telemetry.middleware import PrivacyTelemetryMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    app.state.settings = settings
    install_privacy_log_filter()
    async with database_lifespan(app, settings):
        yield


app = FastAPI(title="PNW Student Information Chatbot", lifespan=lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET_KEY") or secrets.token_urlsafe(32),
    session_cookie="pnw_reviewer_session",
    max_age=3600,
    same_site="lax",
    https_only=os.getenv("APP_ENV", "development").lower() == "production",
    path="/api/v1",
)
app.add_middleware(
    PrivacyTelemetryMiddleware,
    aggregates=TelemetryAggregates(),
)
register_error_handlers(app)
app.include_router(api_router, prefix="/api/v1")


@app.middleware("http")
async def enforce_request_deadline(
    request: Request,
    call_next: RequestResponseEndpoint,
) -> Response:
    settings = request.app.state.settings
    timeout_seconds = settings.request_timeout_seconds

    try:
        async with asyncio.timeout(timeout_seconds):
            return await call_next(request)
    except TimeoutError:
        return JSONResponse(
            status_code=504,
            content={"detail": "Request timed out."},
        )


@app.get("/health")
async def health() -> dict[str, str]:
    settings = get_settings()
    return {
        "status": "ok",
        "environment": settings.app_env,
    }


@app.get("/")
async def root() -> dict[str, str]:
    return {"status": "ok"}
