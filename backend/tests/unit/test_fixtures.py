from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.reviewer import ReviewerAuditEvent, ReviewerRole, UserRoleAssignment
from app.db.models.source import Source
from app.db.models.source_approval import ApprovalStatus
from app.db.models.source_fragment import SourceFragment
from app.db.models.source_version import SourceVersion
from tests.conftest import ReviewerFactory, SourceFactory


@pytest.mark.asyncio
async def test_source_and_reviewer_factories_create_a_related_governance_graph(
    db_session: AsyncSession,
    source_factory: SourceFactory,
    reviewer_factory: ReviewerFactory,
) -> None:
    source_record = await source_factory(
        approval_status=ApprovalStatus.APPROVED,
        effective_context={"campus": ["Hammond"]},
        fragment_count=2,
    )
    reviewer = await reviewer_factory(
        institutional_subject="reviewer-123",
        role=ReviewerRole.SOURCE_OWNER,
    )

    stored_source = await db_session.get(Source, source_record.source.id)
    assert stored_source is not None
    assert stored_source.current_version_id == source_record.version.id
    assert source_record.approval.source_version_id == source_record.version.id
    assert len(source_record.fragments) == 2
    assert reviewer.institutional_subject == "reviewer-123"
    assert reviewer.role == ReviewerRole.SOURCE_OWNER


@pytest.mark.asyncio
async def test_each_database_session_rolls_back_even_if_test_commits(
    db_session: AsyncSession,
    source_factory: SourceFactory,
) -> None:
    source_record = await source_factory()
    source_id = source_record.source.id
    await db_session.commit()
    assert await db_session.get(Source, source_id) is not None


@pytest.mark.asyncio
async def test_database_fixture_starts_clean_after_prior_test_rollback(
    db_session: AsyncSession,
) -> None:
    assert await db_session.scalar(select(func.count()).select_from(Source)) == 0
    assert await db_session.scalar(select(func.count()).select_from(SourceVersion)) == 0
    assert await db_session.scalar(select(func.count()).select_from(SourceFragment)) == 0
    assert await db_session.scalar(select(func.count()).select_from(UserRoleAssignment)) == 0
    assert await db_session.scalar(select(func.count()).select_from(ReviewerAuditEvent)) == 0
    assert await db_session.get(Source, uuid4()) is None


@pytest.mark.asyncio
async def test_reviewer_factory_can_create_inactive_assignment(
    db_session: AsyncSession,
    reviewer_factory: ReviewerFactory,
) -> None:
    assignment = await reviewer_factory(active=False)

    stored = await db_session.get(UserRoleAssignment, assignment.id)
    assert stored is not None
    assert stored.active is False
