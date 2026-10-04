from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

from app.db.models.ingestion_job import IngestionJob, IngestionJobStatus, IngestionJobType
from app.worker.queue import (
    JobClaimLostError,
    SafeJobErrorCode,
    claim_next_job,
    complete_job,
    enqueue_job,
    retry_or_fail_job,
)


class _Result:
    def __init__(self, row: IngestionJob | None = None, rowcount: int = 1) -> None:
        self.row = row
        self.rowcount = rowcount

    def scalar_one_or_none(self) -> IngestionJob | None:
        return self.row


class _Session:
    def __init__(self, job: IngestionJob | None = None) -> None:
        self.job = job
        self.added: list[object] = []
        self.statements: list[object] = []
        self.flush_count = 0

    async def execute(self, statement: object) -> _Result:
        self.statements.append(statement)
        if self.job is not None and str(statement).lstrip().upper().startswith("SELECT"):
            sql = str(statement)
            if "ingestion_jobs.claimed_by =" in sql:
                params = statement.compile(dialect=postgresql.dialect()).params.values()
                if (
                    self.job.status != IngestionJobStatus.CLAIMED
                    or self.job.claimed_by not in params
                ):
                    return _Result()
            return _Result(self.job)
        return _Result()

    def add(self, value: object) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        self.flush_count += 1


@pytest.mark.asyncio
async def test_enqueue_persists_only_source_and_configuration_payload() -> None:
    session = _Session()
    source_id = uuid4()
    job = await enqueue_job(
        session,  # type: ignore[arg-type]
        source_id=source_id,
        job_type=IngestionJobType.FETCH,
        payload={"force_refresh": True, "parser_version": "v3"},
    )

    assert isinstance(job, IngestionJob)
    assert job.source_id == source_id
    assert job.status == IngestionJobStatus.QUEUED
    assert job.attempt_count == 0
    assert session.added == [job]
    assert session.flush_count == 1

    with pytest.raises(ValueError, match="student content"):
        await enqueue_job(
            session,  # type: ignore[arg-type]
            source_id=source_id,
            job_type=IngestionJobType.FETCH,
            payload={"parser": {"question_text": "not allowed"}},
        )


@pytest.mark.asyncio
async def test_claim_is_locked_skips_busy_rows_and_advances_attempt_count() -> None:
    job = IngestionJob(
        id=uuid4(),
        source_id=uuid4(),
        job_type=IngestionJobType.PARSE,
        status=IngestionJobStatus.QUEUED,
        attempt_count=0,
        payload={},
    )
    session = _Session(job)
    now = datetime(2026, 10, 3, tzinfo=UTC)

    claimed = await claim_next_job(
        session,  # type: ignore[arg-type]
        worker_id="worker-a",
        now=now,
    )

    sql = str(session.statements[-1].compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE SKIP LOCKED" in sql
    assert claimed is job
    assert job.status == IngestionJobStatus.CLAIMED
    assert job.claimed_by == "worker-a"
    assert job.claimed_at == now
    assert job.attempt_count == 1


@pytest.mark.asyncio
async def test_completion_requires_claim_owner_and_stores_success_without_payload() -> None:
    job = IngestionJob(
        id=uuid4(),
        source_id=uuid4(),
        job_type=IngestionJobType.EMBED,
        status=IngestionJobStatus.CLAIMED,
        attempt_count=2,
        claimed_by="worker-a",
        claimed_at=datetime.now(UTC),
        payload={},
    )
    session = _Session(job)

    await complete_job(session, job_id=job.id, worker_id="worker-a")  # type: ignore[arg-type]
    assert len(session.statements) == 1
    sql = str(session.statements[0].compile(dialect=postgresql.dialect()))
    assert "ingestion_jobs.status = %(status_1)s" in sql
    assert "ingestion_jobs.claimed_by = %(claimed_by_1)s" in sql

    with pytest.raises(JobClaimLostError, match="no longer owns"):
        await complete_job(session, job_id=job.id, worker_id="worker-b")  # type: ignore[arg-type]
    assert job.status == IngestionJobStatus.COMPLETED


@pytest.mark.asyncio
async def test_retry_backoff_and_attempt_limit_use_only_safe_error_codes() -> None:
    session = _Session()
    now = datetime(2026, 10, 3, tzinfo=UTC)
    job = IngestionJob(
        id=uuid4(),
        source_id=uuid4(),
        job_type=IngestionJobType.CHANGE_CHECK,
        status=IngestionJobStatus.CLAIMED,
        attempt_count=1,
        claimed_by="worker-a",
        claimed_at=now,
        payload={},
    )
    session.job = job

    retry = await retry_or_fail_job(
        session,  # type: ignore[arg-type]
        job_id=job.id,
        worker_id="worker-a",
        error_code=SafeJobErrorCode.SOURCE_UNAVAILABLE,
        retryable=True,
        attempt_count=1,
        max_attempts=3,
        now=now,
    )
    assert retry.status == IngestionJobStatus.QUEUED
    assert retry.last_error_code == SafeJobErrorCode.SOURCE_UNAVAILABLE.value
    assert retry.available_at == now + timedelta(seconds=30)
    assert retry.claimed_by is None

    job.status = IngestionJobStatus.CLAIMED
    job.claimed_by = "worker-a"
    job.claimed_at = now
    job.attempt_count = 3
    exhausted = await retry_or_fail_job(
        session,  # type: ignore[arg-type]
        job_id=job.id,
        worker_id="worker-a",
        error_code=SafeJobErrorCode.SOURCE_UNAVAILABLE,
        retryable=True,
        attempt_count=3,
        max_attempts=3,
        now=now,
    )
    assert exhausted.status == IngestionJobStatus.FAILED
    assert exhausted.last_error_code == SafeJobErrorCode.RETRY_EXHAUSTED.value
