from __future__ import annotations

import logging
from uuid import UUID

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.telemetry.aggregates import TelemetryAggregates
from app.telemetry.logging import PrivacyLogFilter
from app.telemetry.middleware import PrivacyTelemetryMiddleware
from app.telemetry.redaction import redact_for_telemetry, redact_text


def test_redact_text_removes_email_student_id_ssn_and_phone() -> None:
    result = redact_text(
        "Email jane.doe@pnw.edu, Student ID: PNW-12345678, SSN 123-45-6789, "
        "phone (219) 555-1234, identifier 87654321"
    )

    assert result.text.count("[REDACTED]") == 5
    assert result.redaction_count == 5
    assert "jane.doe@pnw.edu" not in result.text
    assert "PNW-12345678" not in result.text


def test_redact_for_telemetry_tracks_only_redaction_count_on_request_state() -> None:
    app = FastAPI()

    @app.get("/")
    async def endpoint(request: Request) -> dict[str, str]:
        redacted = redact_for_telemetry(
            request,
            "Contact jane.doe@pnw.edu; student ID: 12345678",
        )
        return {"redacted": redacted}

    with TestClient(app) as client:
        response = client.get("/")

    assert response.json() == {"redacted": "Contact [REDACTED]; [REDACTED]"}


def test_aggregates_keep_only_allowlisted_outcomes_and_latency_buckets() -> None:
    aggregates = TelemetryAggregates()
    aggregates.record_request(
        outcome="supported",
        latency_ms=120,
        pii_redaction_count=2,
    )
    aggregates.record_request(
        outcome="student question jane@example.edu",
        latency_ms=8000,
        pii_redaction_count=-1,
    )

    snapshot = aggregates.snapshot()
    assert snapshot.outcome_counts == {"supported": 1, "unknown": 1}
    assert snapshot.latency_counts == {"le_250ms": 1, "gt_5000ms": 1}
    assert snapshot.pii_redaction_count == 2
    assert all(
        outcome in {"supported", "clarification_needed", "referral", "unknown", "error"}
        for outcome in snapshot.outcome_counts
    )


def test_privacy_middleware_sets_fresh_uuid_header_and_records_aggregates() -> None:
    aggregates = TelemetryAggregates()
    app = FastAPI()
    app.add_middleware(PrivacyTelemetryMiddleware, aggregates=aggregates)

    @app.get("/")
    async def endpoint(request: Request) -> dict[str, str]:
        request.state.telemetry_outcome = "referral"
        request.state.pii_redaction_count = 1
        return {"correlationId": request.state.correlation_id}

    with TestClient(app) as client:
        first = client.get("/", headers={"X-Correlation-ID": "client-chosen"})
        second = client.get("/")

    first_id = UUID(first.headers["X-Correlation-ID"])
    second_id = UUID(second.headers["X-Correlation-ID"])
    assert str(first_id) == first.json()["correlationId"]
    assert str(second_id) == second.json()["correlationId"]
    assert first_id != second_id
    assert first_id != UUID("00000000-0000-0000-0000-000000000000")
    snapshot = aggregates.snapshot()
    assert snapshot.outcome_counts == {"referral": 2}
    assert snapshot.pii_redaction_count == 2


def test_privacy_log_filter_discards_message_arguments_and_exceptions() -> None:
    log_filter = PrivacyLogFilter()
    try:
        raise RuntimeError("question jane.doe@pnw.edu")
    except RuntimeError:
        record = logging.LogRecord(
            "test",
            logging.ERROR,
            __file__,
            1,
            "Failed for %s",
            ("jane.doe@pnw.edu",),
            __import__("sys").exc_info(),
        )
    record.ip_address = "192.0.2.10"
    record.student_id = "12345678"

    assert log_filter.filter(record) is True
    assert record.getMessage() == "application_error"
    assert record.exc_info is None
    assert "ip_address" not in record.__dict__
    assert "student_id" not in record.__dict__
