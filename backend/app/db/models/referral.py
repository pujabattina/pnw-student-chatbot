from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import Boolean, ForeignKey, String, Text, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.base import Base

if TYPE_CHECKING:
    from app.db.models.source_approval import SourceApproval


class Referral(Base):
    __tablename__ = "referrals"

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    campus: Mapped[str | None] = mapped_column(String(64), nullable=True)
    term: Mapped[str | None] = mapped_column(String(64), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    source_approval_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("source_approvals.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    source_approval: Mapped[SourceApproval] = relationship("SourceApproval")
