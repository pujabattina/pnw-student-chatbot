from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.base import Base

if TYPE_CHECKING:
    from app.db.models.source_approval import SourceApproval
    from app.db.models.source_fragment import SourceFragment


class ParseStatus(StrEnum):
    INTERPRETABLE = "interpretable"
    UNINTERPRETABLE = "uninterpretable"


class SourceVersion(Base):
    __tablename__ = "source_versions"
    __table_args__ = (
        CheckConstraint(
            "parse_status IN ('interpretable', 'uninterpretable')",
            name="ck_source_versions_parse_status",
        ),
        UniqueConstraint(
            "source_id",
            "content_fingerprint",
            name="uq_source_versions_source_fingerprint",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    source_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("sources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    content_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    change_detected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    extracted_content_ref: Mapped[str] = mapped_column(Text, nullable=False)
    parse_status: Mapped[ParseStatus] = mapped_column(
        Enum(
            ParseStatus,
            name="source_parse_status",
            native_enum=False,
            create_constraint=False,
            length=32,
            values_callable=lambda status_enum: [status.value for status in status_enum],
        ),
        nullable=False,
    )

    fragments: Mapped[list[SourceFragment]] = relationship(
        "SourceFragment",
        back_populates="source_version",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    approvals: Mapped[list[SourceApproval]] = relationship(
        "SourceApproval",
        back_populates="source_version",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
