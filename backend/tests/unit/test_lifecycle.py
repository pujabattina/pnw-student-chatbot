from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest
from fastapi import HTTPException, Request

from app.corpus.lifecycle import (
    ApprovalTransitionError,
    approve_source,
    disable_source,
    submit_for_review,
)
from app.db.models.source import Source
from app.db.models.source_approval import ApprovalStatus, SourceApproval
from app.db.models.source_version import ParseStatus, SourceVersion


class _Result:
    def __init__(self, row: tuple[SourceApproval, SourceVersion, Source] | None = None) -> None:
        self.row = row

    def one_or_none(self) -> tuple[SourceApproval, SourceVersion, Source] | None:
        return self.row

    def scalar_one_or_none(self) -> object:
        return object()


class _Session:
    def __init__(
        self,
        status: ApprovalStatus = ApprovalStatus.CANDIDATE,
        *,
        current_version: bool = True,
        parse_status: ParseStatus = ParseStatus.INTERPRETABLE,
        owner_subject: str = "owner-subject",
    ) -> None:
        version_id = uuid4()
        self.approval = SourceApproval(
            id=uuid4(),
            source_version_id=version_id,
            status=status,
            effective_context={},
        )
        self.version = SourceVersion(
            id=version_id,
            source_id=uuid4(),
            content_fingerprint="sha256:" + "a" * 64,
            extracted_content_ref="protected://content/version",
            parse_status=parse_status,
        )
        self.source = Source(
            id=self.version.source_id,
            canonical_url="https://pnw.edu/policy",
            title="Policy",
            media_type="text/html",
            owner_subject=owner_subject,
            owner_organization="PNW",
            current_version_id=version_id if current_version else uuid4(),
        )
        self.row = (self.approval, self.version, self.source)
        self.added: list[object] = []
        self.executed = 0

    async def execute(self, statement: object) -> _Result:
        if "user_role_assignments" in str(statement):
            return _Result()
        return _Result(self.row)

    def add(self, value: object) -> None:
        self.added.append(value)


def _request() -> Request:
    request = Request({"type": "http", "http_version": "1.1", "method": "POST", "path": "/"})
    request.state.correlation_id = str(uuid4())
    return request


@pytest.mark.asyncio
async def test_candidate_must_be_submitted_for_review_before_approval() -> None:
    session = _Session()
    request = _request()

    pending = await submit_for_review(
        session,  # type: ignore[arg-type]
        request,
        approval_id=session.approval.id,
        actor_subject="owner-subject",
    )
    assert pending.status == ApprovalStatus.PENDING_REVIEW
    assert len(session.added) == 1

    approved = await approve_source(
        session,  # type: ignore[arg-type]
        request,
        approval_id=session.approval.id,
        actor_subject="owner-subject",
    )
    assert approved.status == ApprovalStatus.APPROVED
    assert approved.approver_subject == "owner-subject"
    assert approved.approved_at is not None
    assert len(session.added) == 2


@pytest.mark.asyncio
async def test_disabled_source_requires_its_owner_to_reapprove() -> None:
    session = _Session(ApprovalStatus.APPROVED)
    request = _request()
    disabled = await disable_source(
        session,  # type: ignore[arg-type]
        request,
        approval_id=session.approval.id,
        actor_subject="owner-subject",
        reason="conflict",
    )

    assert disabled.status == ApprovalStatus.DISABLED
    assert disabled.disabled_at is not None
    assert disabled.disable_reason == "conflict"
    await submit_for_review(
        session,  # type: ignore[arg-type]
        request,
        approval_id=session.approval.id,
        actor_subject="owner-subject",
    )
    approved = await approve_source(
        session,  # type: ignore[arg-type]
        request,
        approval_id=session.approval.id,
        actor_subject="owner-subject",
    )
    assert approved.status == ApprovalStatus.APPROVED
    assert approved.disabled_at is None
    assert approved.disable_reason is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("reason", "updated_field"),
    [
        ("changed", "change_detected_at"),
        ("withdrawn", "withdrawn_at"),
        ("parse_failure", "parse_status"),
    ],
)
async def test_disable_reason_marks_version_unavailable(
    reason: str,
    updated_field: str,
) -> None:
    session = _Session(ApprovalStatus.APPROVED)
    await disable_source(
        session,  # type: ignore[arg-type]
        _request(),
        approval_id=session.approval.id,
        actor_subject="owner-subject",
        reason=reason,
    )

    assert getattr(session.version, updated_field) is not None
    if reason == "parse_failure":
        assert session.version.parse_status == ParseStatus.UNINTERPRETABLE


@pytest.mark.asyncio
async def test_expiry_can_only_disable_after_effective_end_date() -> None:
    session = _Session(ApprovalStatus.APPROVED)
    session.approval.effective_date_end = date(2026, 10, 4)
    with pytest.raises(ApprovalTransitionError):
        await disable_source(
            session,  # type: ignore[arg-type]
            _request(),
            approval_id=session.approval.id,
            actor_subject="owner-subject",
            reason="expired",
            as_of=date(2026, 10, 3),
        )

    session.approval.effective_date_end = date(2026, 10, 2)
    disabled = await disable_source(
        session,  # type: ignore[arg-type]
        _request(),
        approval_id=session.approval.id,
        actor_subject="owner-subject",
        reason="expired",
        as_of=date(2026, 10, 3),
    )
    assert disabled.status == ApprovalStatus.DISABLED


@pytest.mark.asyncio
async def test_rejects_invalid_transitions_wrong_owner_and_uninterpretable_version() -> None:
    request = _request()
    candidate = _Session()
    with pytest.raises(ApprovalTransitionError):
        await approve_source(
            candidate,  # type: ignore[arg-type]
            request,
            approval_id=candidate.approval.id,
            actor_subject="owner-subject",
        )

    wrong_owner = _Session(owner_subject="different-owner")
    with pytest.raises(HTTPException) as denied:
        await submit_for_review(
            wrong_owner,  # type: ignore[arg-type]
            request,
            approval_id=wrong_owner.approval.id,
            actor_subject="owner-subject",
        )
    assert denied.value.status_code == 403

    uninterpretable = _Session(
        ApprovalStatus.PENDING_REVIEW,
        parse_status=ParseStatus.UNINTERPRETABLE,
    )
    with pytest.raises(ApprovalTransitionError):
        await approve_source(
            uninterpretable,  # type: ignore[arg-type]
            request,
            approval_id=uninterpretable.approval.id,
            actor_subject="owner-subject",
        )


@pytest.mark.asyncio
async def test_rejects_stale_source_version_and_missing_approval() -> None:
    session = _Session(ApprovalStatus.PENDING_REVIEW, current_version=False)
    with pytest.raises(ApprovalTransitionError):
        await approve_source(
            session,  # type: ignore[arg-type]
            _request(),
            approval_id=session.approval.id,
            actor_subject="owner-subject",
        )

    missing = _Session()
    missing.row = None  # type: ignore[assignment]
    with pytest.raises(HTTPException) as not_found:
        await submit_for_review(
            missing,  # type: ignore[arg-type]
            _request(),
            approval_id=uuid4(),
            actor_subject="owner-subject",
        )
    assert not_found.value.status_code == 404
