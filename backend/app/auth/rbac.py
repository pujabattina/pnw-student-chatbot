from __future__ import annotations

from collections.abc import Callable
from time import time
from typing import Any

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models.reviewer import ReviewerRole, UserRoleAssignment


def identity_from_session(session: dict[str, Any], *, now: int | None = None) -> str | None:
    subject = session.get("sub")
    expires_at = session.get("exp")
    current_time = int(time()) if now is None else now
    if (
        not isinstance(subject, str)
        or not subject
        or not isinstance(expires_at, (int, float))
        or isinstance(expires_at, bool)
        or expires_at <= current_time
    ):
        return None
    return subject


async def get_current_subject(request: Request) -> str:
    subject = identity_from_session(request.session)
    if subject is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Institutional authentication required.",
            headers={"WWW-Authenticate": "Session"},
        )
    return subject


async def get_active_roles(app: Any, subject: str) -> set[ReviewerRole]:
    session_factory: async_sessionmaker[AsyncSession] | None = getattr(
        app.state,
        "db_session_factory",
        None,
    )
    if session_factory is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service is temporarily unavailable.",
        )

    async with session_factory() as session:
        result = await session.execute(
            select(UserRoleAssignment.role).where(
                UserRoleAssignment.institutional_subject == subject,
                UserRoleAssignment.active.is_(True),
            )
        )
        return set(result.scalars().all())


def enforce_roles(
    actual_roles: set[ReviewerRole],
    required_roles: set[ReviewerRole],
) -> None:
    if not required_roles or actual_roles.isdisjoint(required_roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Authenticated identity lacks the required role.",
        )


def require_roles(*required_roles: ReviewerRole) -> Callable[..., Any]:
    required = set(required_roles)

    async def dependency(
        request: Request,
        subject: str = Depends(get_current_subject),
    ) -> str:
        roles = await get_active_roles(request.app, subject)
        enforce_roles(roles, required)
        request.state.institutional_subject = subject
        request.state.reviewer_roles = roles
        return subject

    return dependency
