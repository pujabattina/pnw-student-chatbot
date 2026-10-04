from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.db.models.ingestion_job import IngestionJob, IngestionJobStatus, IngestionJobType
from app.worker.queue import SafeJobErrorCode
from app.worker.runner import JobExecutionError, run_one_job


class _Result:
    def __init__(self, job: IngestionJob | None) -> None:
        self.job = job

    def scalar_one_or_none(self) -> IngestionJob | None:
        return self.job


class _Transaction:
    async def __aenter__(self) -> _Transaction:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None


class _Session:
    def __init__(self, job: IngestionJob) -> None:
        self.job = job

    def begin(self) -> _Transaction:
        return _Transaction()

    async def execute(self, statement: object) -> _Result:
        if str(statement).lstrip().upper().startswith("SELECT"):
            sql = str(statement)
            if "ingestion_jobs.claimed_by =" in sql:
                params = statement.compile().params.values()
                if (
                    self.job.status != IngestionJobStatus.CLAIMED
                    or self.job.claimed_by not in params
                ):
                    return _Result(None)
            return _Result(self.job)
        return _Result(None)

    async def flush(self) -> None:
        return None


class _SessionFactory:
    def __init__(self, job: IngestionJob) -> None:
        self.job = job

    def __call__(self) -> _SessionContext:
        return _SessionContext(_Session(self.job))


class _SessionContext:
    def __init__(self, session: _Session) -> None:
        self.session = session

    async def __aenter__(self) -> _Session:
        return self.session

    async def __aexit__(self, *_args: object) -> None:
        return None


def _job() -> IngestionJob:
    return IngestionJob(
        id=uuid4(),
        source_id=uuid4(),
        job_type=IngestionJobType.FETCH,
        status=IngestionJobStatus.QUEUED,
        attempt_count=0,
        payload={"refresh": True},
    )


@pytest.mark.asyncio
async def test_runner_claims_dispatches_and_completes_job() -> None:
    job = _job()
    received: list[IngestionJob] = []

    async def handle_fetch(ingestion_job: IngestionJob) -> None:
        received.append(ingestion_job)

    result = await run_one_job(
        _SessionFactory(job),  # type: ignore[arg-type]
        worker_id="worker-1",
        handlers={IngestionJobType.FETCH: handle_fetch},
        now=datetime(2026, 10, 3, tzinfo=UTC),
    )

    assert received == [job]
    assert result.job_id == job.id
    assert result.status == IngestionJobStatus.COMPLETED
    assert result.error_code is None
    assert job.claimed_by is None


@pytest.mark.asyncio
async def test_runner_retries_safe_handler_failures_without_persisting_exception_text() -> None:
    job = _job()

    async def fail_fetch(_ingestion_job: IngestionJob) -> None:
        raise JobExecutionError(SafeJobErrorCode.SOURCE_UNAVAILABLE, retryable=True)

    result = await run_one_job(
        _SessionFactory(job),  # type: ignore[arg-type]
        worker_id="worker-1",
        handlers={IngestionJobType.FETCH: fail_fetch},
        now=datetime(2026, 10, 3, tzinfo=UTC),
        max_attempts=3,
    )

    assert result.status == IngestionJobStatus.QUEUED
    assert result.error_code == SafeJobErrorCode.SOURCE_UNAVAILABLE
    assert job.last_error_code == SafeJobErrorCode.SOURCE_UNAVAILABLE.value
    assert job.attempt_count == 1


@pytest.mark.asyncio
async def test_runner_maps_unexpected_handler_error_to_safe_code_and_fails_after_limit() -> None:
    job = _job()
    job.attempt_count = 2

    async def fail_fetch(_ingestion_job: IngestionJob) -> None:
        raise RuntimeError("raw parser exception with untrusted source text")

    result = await run_one_job(
        _SessionFactory(job),  # type: ignore[arg-type]
        worker_id="worker-1",
        handlers={IngestionJobType.FETCH: fail_fetch},
        max_attempts=3,
    )

    assert result.status == IngestionJobStatus.FAILED
    assert result.error_code == SafeJobErrorCode.INTERNAL_ERROR
    assert job.last_error_code == SafeJobErrorCode.RETRY_EXHAUSTED.value


@pytest.mark.asyncio
async def test_runner_marks_missing_handler_as_permanent_safe_failure() -> None:
    job = _job()
    result = await run_one_job(
        _SessionFactory(job),  # type: ignore[arg-type]
        worker_id="worker-1",
        handlers={},
    )

    assert result.status == IngestionJobStatus.FAILED
    assert result.error_code == SafeJobErrorCode.INVALID_JOB
