from __future__ import annotations

import re
from uuid import UUID

from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.reviewer import ReviewerAuditEvent, ReviewerRole, UserRoleAssignment

_SLUG = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")
_CONTEXT_FIELDS = {"campus", "college", "program", "course", "academic_term"}


def _validate_tag(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not _SLUG.fullmatch(value):
        raise ValueError(f"Audit {field_name} must be a safe identifier.")
    return value


def _validate_details(details: dict[str, object] | None) -> dict[str, object]:
    if details is None:
        return {}
    if not isinstance(details, dict):
        raise ValueError("Audit details must be an object.")

    validated: dict[str, object] = {}
    for key, value in details.items():
        if key == "reason_code":
            validated[key] = _validate_tag(value, key)
        elif key == "source_version_id":
            if not isinstance(value, str):
                raise ValueError("Audit source_version_id must be a UUID.")
            try:
                validated[key] = str(UUID(value))
            except ValueError as exc:
                raise ValueError("Audit source_version_id must be a UUID.") from exc
        elif key in {"before_context", "after_context"}:
            if not isinstance(value, dict) or set(value) - _CONTEXT_FIELDS:
                raise ValueError(f"Audit {key} contains unsupported context fields.")
            context: dict[str, list[str]] = {}
            for field, values in value.items():
                if (
                    not isinstance(values, list)
                    or len(values) > 32
                    or not all(
                        isinstance(item, str)
                        and len(item) <= 100
                        and item.isprintable()
                        and not any(char in item for char in "\r\n\t")
                        for item in values
                    )
                ):
                    raise ValueError(f"Audit {key} contains invalid context values.")
                context[field] = values
            validated[key] = context
        else:
            raise ValueError(f"Audit detail field {key!r} is not permitted.")
    return validated


async def write_reviewer_audit_event(
    session: AsyncSession,
    request: Request,
    *,
    actor_subject: str,
    actor_role: ReviewerRole,
    action: str,
    target_type: str,
    target_id: UUID,
    before_status: str | None = None,
    after_status: str | None = None,
    details: dict[str, object] | None = None,
) -> ReviewerAuditEvent:
    """Add an authorized, content-safe audit row to the caller's transaction."""
    if not actor_subject or len(actor_subject) > 255:
        raise ValueError("Audit actor subject is invalid.")
    action = _validate_tag(action, "action")
    target_type = _validate_tag(target_type, "target_type")
    if before_status is not None:
        before_status = _validate_tag(before_status, "before_status")
    if after_status is not None:
        after_status = _validate_tag(after_status, "after_status")

    correlation_id = getattr(request.state, "correlation_id", None)
    try:
        correlation_uuid = UUID(str(correlation_id))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError("Audit correlation ID is missing or invalid.") from exc

    authorized_role = await session.execute(
        select(UserRoleAssignment.id).where(
            UserRoleAssignment.institutional_subject == actor_subject,
            UserRoleAssignment.role == actor_role,
            UserRoleAssignment.active.is_(True),
        )
    )
    if authorized_role.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Authenticated identity lacks the audit role.",
        )

    event = ReviewerAuditEvent(
        actor_subject=actor_subject,
        role=actor_role,
        action=action,
        target_type=target_type,
        target_id=target_id,
        correlation_id=correlation_uuid,
        before_status=before_status,
        after_status=after_status,
        details=_validate_details(details),
    )
    session.add(event)
    return event
