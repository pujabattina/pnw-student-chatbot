from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    String,
    Text,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.base import Base

if TYPE_CHECKING:
    from app.db.models.source_version import SourceVersion


class ApprovalStatus(StrEnum):
    CANDIDATE = "candidate"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    DISABLED = "disabled"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class SourceApproval(Base):
    __tablename__ = "source_approvals"
    __table_args__ = (
        CheckConstraint(
            "status IN ('candidate', 'pending_review', 'approved', 'disabled', "
            "'rejected', 'superseded')",
            name="ck_source_approvals_status",
        ),
        CheckConstraint(
            "status != 'approved' OR (approver_subject IS NOT NULL AND approved_at IS NOT NULL)",
            name="ck_source_approvals_approved_fields",
        ),
        CheckConstraint(
            "status != 'disabled' OR (disabled_at IS NOT NULL AND disable_reason IS NOT NULL)",
            name="ck_source_approvals_disabled_fields",
        ),
        CheckConstraint(
            "effective_date_start IS NULL OR effective_date_end IS NULL "
            "OR effective_date_start <= effective_date_end",
            name="ck_source_approvals_effective_date_range",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    source_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("source_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[ApprovalStatus] = mapped_column(
        Enum(
            ApprovalStatus,
            name="source_approval_status",
            native_enum=False,
            create_constraint=False,
            length=32,
            values_callable=lambda status_enum: [status.value for status in status_enum],
        ),
        nullable=False,
    )
    approver_subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    disable_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    effective_context: Mapped[dict[str, list[str]]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )
    effective_date_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_date_end: Mapped[date | None] = mapped_column(Date, nullable=True)

    source_version: Mapped[SourceVersion] = relationship(
        "SourceVersion",
        back_populates="approvals",
    )
