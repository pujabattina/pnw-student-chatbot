from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, validates

from app.db.models.base import Base

_STUDENT_CONTENT_KEYS = {"answer", "prompt", "question", "query", "response", "transcript"}


class IngestionJobType(StrEnum):
    FETCH = "fetch"
    PARSE = "parse"
    EMBED = "embed"
    CHANGE_CHECK = "change_check"


class IngestionJobStatus(StrEnum):
    QUEUED = "queued"
    CLAIMED = "claimed"
    COMPLETED = "completed"
    FAILED = "failed"


def _validate_configuration_payload(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("Ingestion job payload must be a configuration object.")

    def check_keys(item: Any) -> None:
        if isinstance(item, Mapping):
            for key, nested_value in item.items():
                normalized_key = str(key).lower().replace("-", "_")
                if normalized_key in _STUDENT_CONTENT_KEYS or any(
                    term in normalized_key
                    for term in ("prompt", "question", "transcript", "response")
                ):
                    raise ValueError("Ingestion job payload cannot contain student content.")
                check_keys(nested_value)
        elif isinstance(item, (list, tuple)):
            for nested_value in item:
                check_keys(nested_value)

    check_keys(value)
    return dict(value)


class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"
    __table_args__ = (
        CheckConstraint(
            "job_type IN ('fetch', 'parse', 'embed', 'change_check')",
            name="ck_ingestion_jobs_job_type",
        ),
        CheckConstraint(
            "status IN ('queued', 'claimed', 'completed', 'failed')",
            name="ck_ingestion_jobs_status",
        ),
        CheckConstraint("attempt_count >= 0", name="ck_ingestion_jobs_attempt_count"),
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
    job_type: Mapped[IngestionJobType] = mapped_column(
        Enum(
            IngestionJobType,
            name="ingestion_job_type",
            native_enum=False,
            create_constraint=False,
            length=32,
            values_callable=lambda job_type_enum: [job_type.value for job_type in job_type_enum],
        ),
        nullable=False,
    )
    status: Mapped[IngestionJobStatus] = mapped_column(
        Enum(
            IngestionJobStatus,
            name="ingestion_job_status",
            native_enum=False,
            create_constraint=False,
            length=16,
            values_callable=lambda status_enum: [status.value for status in status_enum],
        ),
        nullable=False,
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    claimed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        server_default=text("'{}'"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    @validates("payload")
    def _validate_payload(self, _key: str, value: Mapping[str, Any]) -> dict[str, Any]:
        return _validate_configuration_payload(value)
