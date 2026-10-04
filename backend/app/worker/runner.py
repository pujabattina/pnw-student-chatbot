from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models.ingestion_job import IngestionJob, IngestionJobStatus, IngestionJobType
from app.worker.queue import (
    JobClaimLostError,
    SafeJobErrorCode,
    claim_next_job,
    complete_job,
    retry_or_fail_job,
)

JobHandler = Callable[[IngestionJob], Awaitable[None]]


class JobExecutionError(Exception):
    def __init__(self, error_code: SafeJobErrorCode, *, retryable: bool) -> None:
        super().__init__(error_code.value)
        self.error_code = error_code
        self.retryable = retryable


@dataclass(frozen=True, slots=True)
class JobRunResult:
    job_id: UUID | None
    status: IngestionJobStatus | None
    error_code: SafeJobErrorCode | None = None


async def run_one_job(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    worker_id: str,
    handlers: Mapping[IngestionJobType, JobHandler],
    now: datetime | None = None,
    max_attempts: int = 5,
) -> JobRunResult:
    async with session_factory() as session:
        async with session.begin():
            job = await claim_next_job(
                session,
                worker_id=worker_id,
                now=now,
                max_attempts=max_attempts,
            )
            if job is None:
                return JobRunResult(job_id=None, status=None)
            job_id = job.id
            job_type = job.job_type
            attempt_count = job.attempt_count

    try:
        handler = handlers.get(job_type)
        if handler is None:
            raise JobExecutionError(SafeJobErrorCode.INVALID_JOB, retryable=False)
        await handler(job)
    except JobExecutionError as exc:
        error_code = exc.error_code
        retryable = exc.retryable
    except Exception:
        error_code = SafeJobErrorCode.INTERNAL_ERROR
        retryable = True
    else:
        async with session_factory() as session:
            async with session.begin():
                try:
                    completed = await complete_job(
                        session,
                        job_id=job_id,
                        worker_id=worker_id,
                    )
                except JobClaimLostError:
                    return JobRunResult(
                        job_id=job_id,
                        status=IngestionJobStatus.CLAIMED,
                    )
                return JobRunResult(job_id=job_id, status=completed.status)

    async with session_factory() as session:
        async with session.begin():
            try:
                updated = await retry_or_fail_job(
                    session,
                    job_id=job_id,
                    worker_id=worker_id,
                    error_code=error_code,
                    retryable=retryable,
                    attempt_count=attempt_count,
                    max_attempts=max_attempts,
                    now=now,
                )
            except JobClaimLostError:
                return JobRunResult(
                    job_id=job_id,
                    status=IngestionJobStatus.CLAIMED,
                    error_code=error_code,
                )
            return JobRunResult(
                job_id=job_id,
                status=updated.status,
                error_code=error_code,
            )
