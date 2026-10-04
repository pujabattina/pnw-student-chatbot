from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException, Request

from app.corpus.audit import write_reviewer_audit_event
from app.db.models.reviewer import ReviewerAuditEvent, ReviewerRole


class _RoleResult:
    def __init__(self, authorized: bool) -> None:
        self.authorized = authorized

    def scalar_one_or_none(self) -> int | None:
        return 1 if self.authorized else None


class _AuditSession:
    def __init__(self, authorized: bool = True) -> None:
        self.authorized = authorized
        self.added: list[object] = []

    async def execute(self, _statement: object) -> _RoleResult:
        return _RoleResult(self.authorized)

    def add(self, event: object) -> None:
        self.added.append(event)


def _request() -> Request:
    request = Request({"type": "http", "http_version": "1.1", "method": "POST", "path": "/"})
    request.state.correlation_id = str(uuid4())
    return request


@pytest.mark.asyncio
async def test_audit_writer_checks_active_role_and_adds_event_to_callers_transaction() -> None:
    session = _AuditSession()
    target_id = uuid4()

    event = await write_reviewer_audit_event(
        session,  # type: ignore[arg-type]
        _request(),
        actor_subject="institutional-subject",
        actor_role=ReviewerRole.SOURCE_OWNER,
        action="source.approve",
        target_type="source_approval",
        target_id=target_id,
        before_status="pending_review",
        after_status="approved",
        details={
            "reason_code": "owner_approval",
            "before_context": {"campus": ["west-lafayette"]},
        },
    )

    assert isinstance(event, ReviewerAuditEvent)
    assert session.added == [event]
    assert event.actor_subject == "institutional-subject"
    assert event.role == ReviewerRole.SOURCE_OWNER
    assert event.target_id == target_id
    assert event.correlation_id is not None
    assert event.details == {
        "reason_code": "owner_approval",
        "before_context": {"campus": ["west-lafayette"]},
    }


@pytest.mark.asyncio
async def test_audit_writer_denies_inactive_role_without_adding_event() -> None:
    session = _AuditSession(authorized=False)

    with pytest.raises(HTTPException) as denied:
        await write_reviewer_audit_event(
            session,  # type: ignore[arg-type]
            _request(),
            actor_subject="institutional-subject",
            actor_role=ReviewerRole.ADMIN,
            action="role.assign",
            target_type="user_role_assignment",
            target_id=uuid4(),
        )

    assert denied.value.status_code == 403
    assert session.added == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "details",
    [
        {"question": "student question"},
        {"notes": "potentially sensitive free text"},
        {"before_context": {"unexpected": ["value"]}},
    ],
)
async def test_audit_writer_rejects_non_allowlisted_details(
    details: dict[str, object],
) -> None:
    session = _AuditSession()
    with pytest.raises(ValueError):
        await write_reviewer_audit_event(
            session,  # type: ignore[arg-type]
            _request(),
            actor_subject="institutional-subject",
            actor_role=ReviewerRole.REVIEWER,
            action="source.read",
            target_type="source",
            target_id=uuid4(),
            details=details,
        )
    assert session.added == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("dependency_name", "role"),
    [
        ("require_reviewer", ReviewerRole.REVIEWER),
        ("require_source_owner", ReviewerRole.SOURCE_OWNER),
        ("require_admin", ReviewerRole.ADMIN),
        ("require_conflict_resolver", ReviewerRole.CONFLICT_RESOLVER),
    ],
)
async def test_named_dependencies_enforce_their_database_role(
    dependency_name: str,
    role: ReviewerRole,
) -> None:
    from app.auth.dependencies import (
        require_admin,
        require_conflict_resolver,
        require_reviewer,
        require_source_owner,
    )

    dependencies = {
        "require_admin": require_admin,
        "require_conflict_resolver": require_conflict_resolver,
        "require_reviewer": require_reviewer,
        "require_source_owner": require_source_owner,
    }
    app = FastAPI()
    app.state.db_session_factory = _RoleSessionFactory({role})
    request = Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "path": "/",
            "app": app,
        }
    )

    result = await dependencies[dependency_name](request, subject="assigned-subject")

    assert result == "assigned-subject"
    assert request.state.reviewer_roles == {role}


class _RoleSessionFactory:
    def __init__(self, roles: set[ReviewerRole]) -> None:
        self.roles = list(roles)

    def __call__(self) -> _RoleSession:
        return _RoleSession(self.roles)


class _RoleSession:
    def __init__(self, roles: list[ReviewerRole]) -> None:
        self.roles = roles

    async def __aenter__(self) -> _RoleSession:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def execute(self, _statement: object) -> _RoleResult:
        class Result(_RoleResult):
            def all(self) -> list[ReviewerRole]:
                return self._roles

            def __init__(self, values: list[ReviewerRole]) -> None:
                self._roles = values

            def scalars(self) -> Result:
                return self

        return Result(self.roles)
