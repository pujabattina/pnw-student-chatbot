from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import UUID

from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.corpus.audit import write_reviewer_audit_event
from app.db.models.reviewer import ReviewerRole
from app.db.models.source import Source
from app.db.models.source_approval import ApprovalStatus, SourceApproval
from app.db.models.source_version import ParseStatus, SourceVersion

_DISABLE_REASONS = {"changed", "withdrawn", "parse_failure", "expired", "conflict"}


class ApprovalTransitionError(ValueError):
    """A source approval cannot make the requested lifecycle transition."""


async def _locked_approval(
    session: AsyncSession,
    approval_id: UUID,
) -> tuple[SourceApproval, SourceVersion, Source]:
    result = await session.execute(
        select(SourceApproval, SourceVersion, Source)
        .join(SourceVersion, SourceApproval.source_version_id == SourceVersion.id)
        .join(Source, SourceVersion.source_id == Source.id)
        .where(SourceApproval.id == approval_id)
        .with_for_update(of=(SourceApproval, SourceVersion, Source))
    )
    record = result.one_or_none()
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source approval was not found.",
        )
    approval, version, source = record
    return approval, version, source


def _require_effective_dates(approval: SourceApproval, effective_date: date) -> None:
    if approval.effective_date_start is not None and approval.effective_date_start > effective_date:
        raise ApprovalTransitionError("The source approval is not yet effective.")
    if approval.effective_date_end is not None and approval.effective_date_end < effective_date:
        raise ApprovalTransitionError("The source approval has expired.")


def _require_owner(source: Source, actor_subject: str) -> None:
    if source.owner_subject != actor_subject:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the source owner may approve this source.",
        )


def _require_current_interpretable(source: Source, version: SourceVersion) -> None:
    if source.current_version_id != version.id:
        raise ApprovalTransitionError("Only the current source version can be approved.")
    if (
        version.parse_status != ParseStatus.INTERPRETABLE
        or version.change_detected_at is not None
        or version.withdrawn_at is not None
    ):
        raise ApprovalTransitionError("Only an unchanged interpretable version can be approved.")


async def submit_for_review(
    session: AsyncSession,
    request: Request,
    *,
    approval_id: UUID,
    actor_subject: str,
) -> SourceApproval:
    approval, version, source = await _locked_approval(session, approval_id)
    _require_owner(source, actor_subject)
    if approval.status not in {ApprovalStatus.CANDIDATE, ApprovalStatus.DISABLED}:
        raise ApprovalTransitionError("Only candidate or disabled sources can enter review.")
    _require_current_interpretable(source, version)

    before_status = approval.status.value
    await write_reviewer_audit_event(
        session,
        request,
        actor_subject=actor_subject,
        actor_role=ReviewerRole.SOURCE_OWNER,
        action="source.submit_for_review",
        target_type="source_approval",
        target_id=approval.id,
        before_status=before_status,
        after_status=ApprovalStatus.PENDING_REVIEW.value,
    )
    approval.status = ApprovalStatus.PENDING_REVIEW
    approval.disabled_at = None
    approval.disable_reason = None
    return approval


async def approve_source(
    session: AsyncSession,
    request: Request,
    *,
    approval_id: UUID,
    actor_subject: str,
) -> SourceApproval:
    approval, version, source = await _locked_approval(session, approval_id)
    _require_owner(source, actor_subject)
    if approval.status != ApprovalStatus.PENDING_REVIEW:
        raise ApprovalTransitionError("Only sources pending review can be approved.")
    _require_current_interpretable(source, version)
    _require_effective_dates(approval, date.today())

    before_status = approval.status.value
    await write_reviewer_audit_event(
        session,
        request,
        actor_subject=actor_subject,
        actor_role=ReviewerRole.SOURCE_OWNER,
        action="source.approve",
        target_type="source_approval",
        target_id=approval.id,
        before_status=before_status,
        after_status=ApprovalStatus.APPROVED.value,
    )
    approval.status = ApprovalStatus.APPROVED
    approval.approver_subject = actor_subject
    approval.approved_at = datetime.now(UTC)
    approval.disabled_at = None
    approval.disable_reason = None
    return approval


async def disable_source(
    session: AsyncSession,
    request: Request,
    *,
    approval_id: UUID,
    actor_subject: str,
    reason: str,
    actor_role: ReviewerRole = ReviewerRole.SOURCE_OWNER,
    as_of: date | None = None,
) -> SourceApproval:
    if reason not in _DISABLE_REASONS:
        raise ValueError("Source disable reason is not permitted.")

    approval, version, source = await _locked_approval(session, approval_id)
    if actor_role == ReviewerRole.SOURCE_OWNER:
        _require_owner(source, actor_subject)
    elif actor_role not in {
        ReviewerRole.ADMIN,
        ReviewerRole.CONFLICT_RESOLVER,
    }:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This role cannot disable source approvals.",
        )
    if approval.status != ApprovalStatus.APPROVED:
        raise ApprovalTransitionError("Only approved sources can be disabled.")
    if reason == "expired" and (
        approval.effective_date_end is None
        or approval.effective_date_end >= (as_of or date.today())
    ):
        raise ApprovalTransitionError("The source approval has not expired.")

    before_status = approval.status.value
    disabled_at = datetime.now(UTC)
    await write_reviewer_audit_event(
        session,
        request,
        actor_subject=actor_subject,
        actor_role=actor_role,
        action=f"source.disable_{reason}",
        target_type="source_approval",
        target_id=approval.id,
        before_status=before_status,
        after_status=ApprovalStatus.DISABLED.value,
        details={"source_version_id": str(version.id)},
    )
    approval.status = ApprovalStatus.DISABLED
    approval.disabled_at = disabled_at
    approval.disable_reason = reason
    if reason == "changed":
        version.change_detected_at = disabled_at
    elif reason == "withdrawn":
        version.withdrawn_at = disabled_at
    elif reason == "parse_failure":
        version.parse_status = ParseStatus.UNINTERPRETABLE
    return approval
