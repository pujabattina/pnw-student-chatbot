from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    String,
    UniqueConstraint,
    Uuid,
    event,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, validates

from app.db.models.base import Base


class ReviewerRole(StrEnum):
    REVIEWER = "reviewer"
    SOURCE_OWNER = "source_owner"
    ADMIN = "admin"
    CONFLICT_RESOLVER = "conflict_resolver"


class UserRoleAssignment(Base):
    __tablename__ = "user_role_assignments"
    __table_args__ = (
        UniqueConstraint(
            "institutional_subject",
            "role",
            name="uq_user_role_assignments_subject_role",
        ),
        CheckConstraint(
            "role IN ('reviewer', 'source_owner', 'admin', 'conflict_resolver')",
            name="ck_user_role_assignments_role",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    institutional_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[ReviewerRole] = mapped_column(
        Enum(
            ReviewerRole,
            name="reviewer_role",
            native_enum=False,
            create_constraint=False,
            length=32,
            values_callable=lambda role_enum: [role.value for role in role_enum],
        ),
        nullable=False,
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    assigned_by: Mapped[str] = mapped_column(String(255), nullable=False)


class ReviewerAuditEvent(Base):
    __tablename__ = "reviewer_audit_events"

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    actor_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[ReviewerRole] = mapped_column(
        Enum(
            ReviewerRole,
            name="reviewer_audit_role",
            native_enum=False,
            create_constraint=False,
            length=32,
            values_callable=lambda role_enum: [role.value for role in role_enum],
        ),
        nullable=False,
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    correlation_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    before_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    after_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    details: Mapped[dict[str, object]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )

    @validates("details")
    def _validate_details(self, _key: str, value: dict[str, object]) -> dict[str, object]:
        if not isinstance(value, dict):
            raise ValueError("Reviewer audit details must be an object.")

        def check_keys(item: object) -> None:
            if isinstance(item, dict):
                for key, nested_value in item.items():
                    normalized_key = str(key).lower().replace("-", "_")
                    if any(
                        term in normalized_key
                        for term in (
                            "answer",
                            "prompt",
                            "question",
                            "query",
                            "response",
                            "transcript",
                        )
                    ):
                        raise ValueError("Reviewer audit details cannot contain student content.")
                    check_keys(nested_value)
            elif isinstance(item, (list, tuple)):
                for nested_value in item:
                    check_keys(nested_value)

        check_keys(value)
        return value


@event.listens_for(ReviewerAuditEvent, "before_update")
@event.listens_for(ReviewerAuditEvent, "before_delete")
def _prevent_audit_event_mutation(*_args: object) -> None:
    raise ValueError("Reviewer audit events are append-only.")
