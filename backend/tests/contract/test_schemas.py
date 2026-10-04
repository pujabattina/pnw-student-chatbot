from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import TypeAdapter, ValidationError

from app.api.schemas import (
    ChangeEvent,
    ChatOutcome,
    ChatRequest,
    SourceInput,
)
from app.api.schemas import (
    ValidationError as ApiValidationError,
)


def test_chat_request_accepts_contract_fields_and_rejects_extra_fields() -> None:
    request = ChatRequest.model_validate(
        {
            "question": "Where can I find registration dates?",
            "context": {"campus": "Hammond", "academicTerm": "Fall 2026"},
        }
    )

    assert request.context is not None
    assert request.context.academic_term == "Fall 2026"
    assert request.model_dump(by_alias=True)["context"]["academicTerm"] == "Fall 2026"

    with pytest.raises(ValidationError):
        ChatRequest.model_validate({"question": "Question", "unexpected": True})
    with pytest.raises(ValidationError):
        ChatRequest.model_validate({"question": ""})


def test_chat_outcome_union_validates_all_contract_variants() -> None:
    adapter = TypeAdapter(ChatOutcome)
    citation_id = uuid4()

    supported = adapter.validate_python(
        {
            "outcome": "supported",
            "answer": "Check the academic calendar.",
            "citations": [
                {
                    "sourceId": str(citation_id),
                    "title": "Academic Calendar",
                    "url": "https://www.pnw.edu/calendar/",
                }
            ],
            "appliedContext": {"academicTerm": "Fall 2026"},
        }
    )
    assert supported.model_dump(by_alias=True)["citations"][0]["sourceId"] == citation_id

    clarification = adapter.validate_python(
        {
            "outcome": "clarification_needed",
            "question": "Which campus?",
            "missingFields": ["campus"],
        }
    )
    assert clarification.missing_fields == ["campus"]

    referral = adapter.validate_python(
        {
            "outcome": "referral",
            "limitation": "I cannot access account records.",
            "reason": "account_specific",
            "referrals": [{"name": "Registrar"}],
        }
    )
    assert referral.reason == "account_specific"

    with pytest.raises(ValidationError):
        adapter.validate_python(
            {
                "outcome": "supported",
                "answer": "Unsupported without citations.",
                "citations": [],
                "appliedContext": {},
            }
        )


def test_review_source_requires_https_and_change_event_matches_contract() -> None:
    source = SourceInput.model_validate(
        {
            "canonicalUrl": "https://www.pnw.edu/catalog/",
            "title": "Catalog",
            "ownerSubject": "source-owner",
            "effectiveContext": {"campus": ["Hammond"]},
        }
    )
    assert str(source.canonical_url) == "https://www.pnw.edu/catalog/"

    with pytest.raises(ValidationError):
        SourceInput.model_validate(
            {
                "canonicalUrl": "http://www.pnw.edu/catalog/",
                "title": "Catalog",
                "ownerSubject": "source-owner",
                "effectiveContext": {},
            }
        )

    change = ChangeEvent.model_validate(
        {
            "observedAt": datetime.now(UTC).isoformat(),
            "contentFingerprint": "sha256:abc",
            "event": "withdrawn",
        }
    )
    assert change.event.value == "withdrawn"

    with pytest.raises(ValidationError):
        ChangeEvent.model_validate(
            {
                "observedAt": "not-a-date",
                "contentFingerprint": "sha256:abc",
                "event": "changed",
            }
        )


def test_validation_error_schema_matches_fastapi_error_envelope() -> None:
    error = ApiValidationError.model_validate(
        {
            "detail": [{"loc": ["body", "question"], "msg": "required", "type": "missing"}],
            "correlationId": "request-id",
        }
    )

    assert error.code == "validation_error"
    assert error.model_dump(by_alias=True)["correlationId"] == "request-id"
