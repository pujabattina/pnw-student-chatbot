from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.schemas.errors import ApiError, ValidationError, ValidationIssue

logger = logging.getLogger(__name__)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def handle_request_validation_error(
        _request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        issues = [
            ValidationIssue(
                loc=list(error["loc"]),
                msg=error["msg"],
                type=error["type"],
            )
            for error in exc.errors()
        ]
        response = ValidationError(detail=issues)
        return JSONResponse(
            status_code=400,
            content=response.model_dump(mode="json", by_alias=True, exclude_none=True),
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(
        _request: Request,
        exc: StarletteHTTPException,
    ) -> JSONResponse:
        detail = (
            "Service is temporarily unavailable." if exc.status_code == 503 else str(exc.detail)
        )
        response = ApiError(detail=detail)
        return JSONResponse(
            status_code=exc.status_code,
            content=response.model_dump(mode="json", by_alias=True, exclude_none=True),
            headers=exc.headers,
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_exception(
        _request: Request,
        exc: Exception,
    ) -> JSONResponse:
        logger.error("Unhandled request failure: %s", type(exc).__name__)
        response = ApiError(
            detail="Service is temporarily unavailable.",
            code="service_unavailable",
        )
        return JSONResponse(
            status_code=503,
            content=response.model_dump(mode="json", by_alias=True, exclude_none=True),
        )
