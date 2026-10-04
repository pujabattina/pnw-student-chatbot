from __future__ import annotations

import os
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from app.db.models import Base, ReviewerRole, UserRoleAssignment
from app.db.models.source_approval import ApprovalStatus
from app.db.models.source_version import ParseStatus
from tests.factories import SourceRecord, create_reviewer, create_source

SourceFactory = Callable[..., Awaitable[SourceRecord]]
ReviewerFactory = Callable[..., Awaitable[UserRoleAssignment]]


@pytest_asyncio.fixture
async def db_engine() -> AsyncIterator[AsyncEngine]:
    database_url = os.getenv("TEST_DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    engine = create_async_engine(database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with db_engine.connect() as connection:
        outer_transaction = await connection.begin()
        session = AsyncSession(
            bind=connection,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        try:
            yield session
        finally:
            await session.close()
            await outer_transaction.rollback()


@pytest.fixture
def source_factory(db_session: AsyncSession) -> SourceFactory:
    async def factory(
        *,
        approval_status: ApprovalStatus = ApprovalStatus.CANDIDATE,
        parse_status: ParseStatus = ParseStatus.INTERPRETABLE,
        **kwargs: Any,
    ) -> SourceRecord:
        return await create_source(
            db_session,
            approval_status=approval_status,
            parse_status=parse_status,
            **kwargs,
        )

    return factory


@pytest.fixture
def reviewer_factory(db_session: AsyncSession) -> ReviewerFactory:
    async def factory(
        *,
        institutional_subject: str = "test-reviewer",
        role: ReviewerRole = ReviewerRole.REVIEWER,
        active: bool = True,
        assigned_by: str = "test-administrator",
    ) -> UserRoleAssignment:
        return await create_reviewer(
            db_session,
            institutional_subject=institutional_subject,
            role=role,
            active=active,
            assigned_by=assigned_by,
        )

    return factory
