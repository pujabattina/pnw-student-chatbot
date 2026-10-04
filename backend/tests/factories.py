from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.reviewer import ReviewerRole, UserRoleAssignment
from app.db.models.source import Source
from app.db.models.source_approval import ApprovalStatus, SourceApproval
from app.db.models.source_fragment import SourceFragment
from app.db.models.source_version import ParseStatus, SourceVersion


@dataclass(frozen=True, slots=True)
class SourceRecord:
    source: Source
    version: SourceVersion
    approval: SourceApproval
    fragments: tuple[SourceFragment, ...]


async def create_source(
    session: AsyncSession,
    *,
    canonical_url: str | None = None,
    title: str = "Test source",
    owner_subject: str = "source-owner",
    owner_organization: str = "PNW",
    content_fingerprint: str | None = None,
    parse_status: ParseStatus = ParseStatus.INTERPRETABLE,
    approval_status: ApprovalStatus = ApprovalStatus.CANDIDATE,
    effective_context: dict[str, list[str]] | None = None,
    effective_date_start: date | None = None,
    effective_date_end: date | None = None,
    fragment_count: int = 1,
) -> SourceRecord:
    if fragment_count < 0:
        raise ValueError("fragment_count cannot be negative.")

    source_id = uuid4()
    source = Source(
        id=source_id,
        canonical_url=canonical_url or f"https://pnw.edu/test/{source_id}",
        title=title,
        media_type="text/html",
        owner_subject=owner_subject,
        owner_organization=owner_organization,
    )
    session.add(source)
    await session.flush()

    version = SourceVersion(
        id=uuid4(),
        source_id=source_id,
        content_fingerprint=content_fingerprint or f"sha256:{uuid4().hex}",
        captured_at=datetime.now(UTC),
        extracted_content_ref=f"protected://test/{source_id}",
        parse_status=parse_status,
    )
    session.add(version)
    await session.flush()
    source.current_version_id = version.id

    approval = SourceApproval(
        id=uuid4(),
        source_version_id=version.id,
        status=approval_status,
        approver_subject=(owner_subject if approval_status == ApprovalStatus.APPROVED else None),
        approved_at=(datetime.now(UTC) if approval_status == ApprovalStatus.APPROVED else None),
        disabled_at=(datetime.now(UTC) if approval_status == ApprovalStatus.DISABLED else None),
        disable_reason=("test_setup" if approval_status == ApprovalStatus.DISABLED else None),
        effective_context=effective_context or {},
        effective_date_start=effective_date_start,
        effective_date_end=effective_date_end,
    )
    session.add(approval)

    fragments = tuple(
        SourceFragment(
            id=uuid4(),
            source_version_id=version.id,
            locator=f"section-{index + 1}",
            extracted_text=f"Test source content {index + 1}.",
            excerpt=f"Test excerpt {index + 1}.",
            extraction_status="interpretable",
        )
        for index in range(fragment_count)
    )
    session.add_all(fragments)
    await session.flush()
    return SourceRecord(source, version, approval, fragments)


async def create_reviewer(
    session: AsyncSession,
    *,
    institutional_subject: str = "test-reviewer",
    role: ReviewerRole = ReviewerRole.REVIEWER,
    active: bool = True,
    assigned_by: str = "test-administrator",
) -> UserRoleAssignment:
    assignment = UserRoleAssignment(
        id=uuid4(),
        institutional_subject=institutional_subject,
        role=role,
        active=active,
        assigned_at=datetime.now(UTC),
        assigned_by=assigned_by,
    )
    session.add(assignment)
    await session.flush()
    return assignment
