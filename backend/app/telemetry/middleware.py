from __future__ import annotations

from time import perf_counter
from uuid import uuid4

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

from app.telemetry.aggregates import TelemetryAggregates


class PrivacyTelemetryMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, aggregates: TelemetryAggregates) -> None:
        super().__init__(app)
        self._aggregates = aggregates

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        correlation_id = str(uuid4())
        request.state.correlation_id = correlation_id
        request.state.telemetry_outcome = "unknown"
        request.state.pii_redaction_count = 0
        started_at = perf_counter()

        try:
            response = await call_next(request)
            response.headers["X-Correlation-ID"] = correlation_id
            if response.status_code >= 500:
                request.state.telemetry_outcome = "error"
            return response
        except Exception:
            request.state.telemetry_outcome = "error"
            raise
        finally:
            self._aggregates.record_request(
                outcome=request.state.telemetry_outcome,
                latency_ms=(perf_counter() - started_at) * 1000,
                pii_redaction_count=request.state.pii_redaction_count,
            )
