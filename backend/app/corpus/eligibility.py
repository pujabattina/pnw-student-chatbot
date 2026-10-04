from __future__ import annotations

from datetime import date

from sqlalchemy import and_, cast, or_, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select
from sqlalchemy.sql.elements import ColumnElement

from app.api.schemas.chat import QuestionContext
from app.db.models.source import Source
from app.db.models.source_approval import ApprovalStatus, SourceApproval
from app.db.models.source_fragment import SourceFragment
from app.db.models.source_version import ParseStatus, SourceVersion

_CONTEXT_FIELDS = ("campus", "college", "program", "course", "academic_term")


def _context_conditions(context: QuestionContext | None) -> list[ColumnElement[bool]]:
    effective_context = cast(SourceApproval.effective_context, JSONB)
    requested_context = context or QuestionContext()
    conditions = []

    for field in _CONTEXT_FIELDS:
        requested_value = getattr(requested_context, field)
        if isinstance(requested_value, str):
            requested_value = requested_value.strip() or None

        scope = effective_context[field]
        unrestricted = or_(scope.is_(None), scope == cast("[]", JSONB))
        if requested_value is None:
            conditions.append(unrestricted)
        else:
            conditions.append(
                or_(
                    unrestricted,
                    scope.contains([requested_value]),
                )
            )

    return conditions


def eligible_source_version_statement(
    context: QuestionContext | None = None,
    *,
    as_of: date | None = None,
) -> Select[SourceVersion]:
    """Build a fail-closed query for current, approved, interpretable versions."""
    effective_date = as_of or date.today()
    return (
        select(SourceVersion)
        .join(Source, Source.current_version_id == SourceVersion.id)
        .join(SourceApproval, SourceApproval.source_version_id == SourceVersion.id)
        .where(
            SourceVersion.source_id == Source.id,
            SourceVersion.parse_status == ParseStatus.INTERPRETABLE,
            SourceVersion.change_detected_at.is_(None),
            SourceVersion.withdrawn_at.is_(None),
            SourceApproval.status == ApprovalStatus.APPROVED,
            or_(
                SourceApproval.effective_date_start.is_(None),
                SourceApproval.effective_date_start <= effective_date,
            ),
            or_(
                SourceApproval.effective_date_end.is_(None),
                SourceApproval.effective_date_end >= effective_date,
            ),
            and_(*_context_conditions(context)),
        )
        .distinct()
    )


def eligible_source_fragment_statement(
    context: QuestionContext | None = None,
    *,
    as_of: date | None = None,
) -> Select[SourceFragment]:
    effective_date = as_of or date.today()
    return (
        select(SourceFragment)
        .join(SourceVersion, SourceFragment.source_version_id == SourceVersion.id)
        .join(Source, Source.current_version_id == SourceVersion.id)
        .join(SourceApproval, SourceApproval.source_version_id == SourceVersion.id)
        .where(
            SourceVersion.source_id == Source.id,
            SourceVersion.parse_status == ParseStatus.INTERPRETABLE,
            SourceVersion.change_detected_at.is_(None),
            SourceVersion.withdrawn_at.is_(None),
            SourceApproval.status == ApprovalStatus.APPROVED,
            or_(
                SourceApproval.effective_date_start.is_(None),
                SourceApproval.effective_date_start <= effective_date,
            ),
            or_(
                SourceApproval.effective_date_end.is_(None),
                SourceApproval.effective_date_end >= effective_date,
            ),
            and_(*_context_conditions(context)),
        )
        .distinct()
    )


async def get_eligible_source_versions(
    session: AsyncSession,
    context: QuestionContext | None = None,
    *,
    as_of: date | None = None,
) -> list[SourceVersion]:
    result = await session.scalars(eligible_source_version_statement(context, as_of=as_of))
    return list(result.unique().all())


async def get_eligible_source_fragments(
    session: AsyncSession,
    context: QuestionContext | None = None,
    *,
    as_of: date | None = None,
) -> list[SourceFragment]:
    result = await session.scalars(eligible_source_fragment_statement(context, as_of=as_of))
    return list(result.unique().all())
