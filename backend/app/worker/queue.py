from __future__ import annotations

from datetime import UTC, datetime, timedelta
from enum import StrEnum
from uuid import UUID

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.ingestion_job import IngestionJob, IngestionJobStatus, IngestionJobType


class SafeJobErrorCode(StrEnum):
    SOURCE_UNAVAILABLE = "source_unavailable"
    PARSE_FAILED = "parse_failed"
    EMBEDDING_FAILED = "embedding_failed"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    INVALID_JOB = "invalid_job"
    INTERNAL_ERROR = "internal_error"
    RETRY_EXHAUSTED = "retry_exhausted"


class JobClaimLostError(RuntimeError):
    pass


def _utc_now(value: datetime | None) -> datetime:
    now = value or datetime.now(UTC)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Worker timestamps must include a timezone.")
    return now.astimezone(UTC)


async def enqueue_job(
    session: AsyncSession,
    *,
    source_id: UUID,
    job_type: IngestionJobType,
    payload: dict[str, object] | None = None,
    available_at: datetime | None = None,
) -> IngestionJob:
    job = IngestionJob(
        source_id=source_id,
        job_type=job_type,
        status=IngestionJobStatus.QUEUED,
        attempt_count=0,
        available_at=_utc_now(available_at),
        payload=payload or {},
    )
    session.add(job)
    await session.flush()
    return job


async def claim_next_job(
    session: AsyncSession,
    *,
    worker_id: str,
    now: datetime | None = None,
    claim_timeout: timedelta = timedelta(minutes=5),
    max_attempts: int = 5,
) -> IngestionJob | None:
    if not worker_id or len(worker_id) > 255:
        raise ValueError("Worker ID must be between 1 and 255 characters.")
    if max_attempts < 1 or claim_timeout.total_seconds() <= 0:
        raise ValueError("Worker retry and claim limits must be positive.")
    current_time = _utc_now(now)
    stale_before = current_time - claim_timeout

    exhausted = and_(
        IngestionJob.attempt_count >= max_attempts,
        or_(
            and_(
                IngestionJob.status == IngestionJobStatus.QUEUED,
                IngestionJob.available_at <= current_time,
            ),
            and_(
                IngestionJob.status == IngestionJobStatus.CLAIMED,
                IngestionJob.claimed_at <= stale_before,
            ),
        ),
    )
    await session.execute(
        update(IngestionJob)
        .where(exhausted)
        .values(
            status=IngestionJobStatus.FAILED,
            last_error_code=SafeJobErrorCode.RETRY_EXHAUSTED.value,
            claimed_at=None,
            claimed_by=None,
        )
    )

    claimable = and_(
        IngestionJob.attempt_count < max_attempts,
        or_(
            and_(
                IngestionJob.status == IngestionJobStatus.QUEUED,
                IngestionJob.available_at <= current_time,
            ),
            and_(
                IngestionJob.status == IngestionJobStatus.CLAIMED,
                IngestionJob.claimed_at <= stale_before,
            ),
        ),
    )
    result = await session.execute(
        select(IngestionJob)
        .where(claimable)
        .order_by(IngestionJob.available_at, IngestionJob.created_at, IngestionJob.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    job = result.scalar_one_or_none()
    if job is None:
        return None

    job.status = IngestionJobStatus.CLAIMED
    job.claimed_at = current_time
    job.claimed_by = worker_id
    job.attempt_count += 1
    job.last_error_code = None
    await session.flush()
    return job


async def _claimed_job(
    session: AsyncSession,
    *,
    job_id: UUID,
    worker_id: str,
) -> IngestionJob:
    result = await session.execute(
        select(IngestionJob)
        .where(
            IngestionJob.id == job_id,
            IngestionJob.status == IngestionJobStatus.CLAIMED,
            IngestionJob.claimed_by == worker_id,
        )
        .with_for_update()
    )
    job = result.scalar_one_or_none()
    if job is None:
        raise JobClaimLostError("Worker no longer owns this ingestion job.")
    return job


async def complete_job(
    session: AsyncSession,
    *,
    job_id: UUID,
    worker_id: str,
) -> IngestionJob:
    job = await _claimed_job(session, job_id=job_id, worker_id=worker_id)
    job.status = IngestionJobStatus.COMPLETED
    job.claimed_at = None
    job.claimed_by = None
    job.last_error_code = None
    await session.flush()
    return job


async def retry_or_fail_job(
    session: AsyncSession,
    *,
    job_id: UUID,
    worker_id: str,
    error_code: SafeJobErrorCode,
    retryable: bool,
    attempt_count: int,
    max_attempts: int = 5,
    now: datetime | None = None,
    base_retry_seconds: int = 30,
    max_retry_seconds: int = 3600,
) -> IngestionJob:
    if attempt_count < 1 or max_attempts < 1:
        raise ValueError("Worker retry and attempt limits must be positive.")
    if base_retry_seconds < 1 or max_retry_seconds < base_retry_seconds:
        raise ValueError("Worker retry delays must be positive and ordered.")

    job = await _claimed_job(session, job_id=job_id, worker_id=worker_id)
    exhausted = attempt_count >= max_attempts
    if retryable and not exhausted:
        delay_seconds = min(base_retry_seconds * (2 ** (attempt_count - 1)), max_retry_seconds)
        job.status = IngestionJobStatus.QUEUED
        job.available_at = _utc_now(now) + timedelta(seconds=delay_seconds)
        job.last_error_code = error_code.value
    else:
        job.status = IngestionJobStatus.FAILED
        job.last_error_code = (
            SafeJobErrorCode.RETRY_EXHAUSTED.value if exhausted else error_code.value
        )
    job.claimed_at = None
    job.claimed_by = None
    await session.flush()
    return job
