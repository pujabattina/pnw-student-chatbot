from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.auth.rbac import enforce_roles, get_active_roles
from app.db.models.reviewer import ReviewerRole


class _ScalarResult:
    def __init__(self, values: list[ReviewerRole]) -> None:
        self._values = values

    def scalars(self) -> _ScalarResult:
        return self

    def all(self) -> list[ReviewerRole]:
        return self._values


class _Session:
    def __init__(self, roles: list[ReviewerRole]) -> None:
        self.roles = roles

    async def __aenter__(self) -> _Session:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def execute(self, _statement: object) -> _ScalarResult:
        return _ScalarResult(self.roles)


class _SessionFactory:
    def __init__(self, roles: list[ReviewerRole]) -> None:
        self.roles = roles

    def __call__(self) -> _Session:
        return _Session(self.roles)


@pytest.mark.asyncio
async def test_active_roles_are_loaded_from_database_session() -> None:
    app = SimpleNamespace(
        state=SimpleNamespace(db_session_factory=_SessionFactory([ReviewerRole.REVIEWER]))
    )

    roles = await get_active_roles(app, "signed-in-subject")

    assert roles == {ReviewerRole.REVIEWER}


def test_role_checks_deny_by_default_and_require_an_explicit_match() -> None:
    with pytest.raises(HTTPException) as missing:
        enforce_roles(set(), {ReviewerRole.REVIEWER})
    assert missing.value.status_code == 403

    with pytest.raises(HTTPException) as wrong:
        enforce_roles({ReviewerRole.REVIEWER}, {ReviewerRole.SOURCE_OWNER})
    assert wrong.value.status_code == 403

    enforce_roles(
        {ReviewerRole.SOURCE_OWNER, ReviewerRole.REVIEWER},
        {ReviewerRole.SOURCE_OWNER},
    )


def test_expired_or_missing_subject_is_not_an_authenticated_identity() -> None:
    from app.auth.rbac import identity_from_session

    assert identity_from_session({}) is None
    assert identity_from_session({"sub": "person", "exp": 1}, now=2) is None
    assert identity_from_session({"sub": "person", "exp": 10}, now=2) == "person"
