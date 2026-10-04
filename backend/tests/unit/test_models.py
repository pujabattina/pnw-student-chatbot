from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    ApprovalStatus,
    Base,
    ParseStatus,
    ReviewerAuditEvent,
    ReviewerRole,
    SourceApproval,
    SourceFragment,
    SourceVersion,
    UserRoleAssignment,
)
from app.db.models.reviewer import _prevent_audit_event_mutation
from app.db.models.source import Source, normalize_https_url
from tests.factories import create_source


class _MigrationOperations:
    def __init__(self) -> None:
        self.extensions: list[str] = []
        self.tables: dict[str, tuple[object, ...]] = {}
        self.indexes: list[tuple[object, ...]] = []
        self.dropped_tables: list[str] = []
        self.dropped_extensions: list[str] = []

    def execute(self, statement: str) -> None:
        self.extensions.append(statement)

    def f(self, name: str) -> str:
        return name

    def create_table(self, name: str, *elements: object, **_kwargs: object) -> None:
        self.tables[name] = elements

    def create_index(self, *args: object, **_kwargs: object) -> None:
        self.indexes.append(args)

    def drop_index(self, *_args: object, **_kwargs: object) -> None:
        return None

    def drop_table(self, name: str) -> None:
        self.dropped_tables.append(name)


def _load_initial_migration() -> ModuleType:
    migration_path = Path(__file__).parents[2] / "alembic" / "versions" / "0001_initial_schema.py"
    spec = importlib.util.spec_from_file_location("initial_schema_migration", migration_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_initial_migration_creates_required_tables_extensions_and_constraints(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _load_initial_migration()
    operations = _MigrationOperations()
    monkeypatch.setattr(migration, "op", operations)

    migration.upgrade()

    assert operations.extensions == [
        "CREATE EXTENSION IF NOT EXISTS pgcrypto",
        "CREATE EXTENSION IF NOT EXISTS vector",
    ]
    assert set(operations.tables) == {
        "sources",
        "source_versions",
        "source_approvals",
        "source_fragments",
        "referrals",
        "user_role_assignments",
        "reviewer_audit_events",
        "ingestion_jobs",
    }
    version_elements = operations.tables["source_versions"]
    assert any(
        getattr(element, "name", None) == "uq_source_versions_source_fingerprint"
        for element in version_elements
    )
    role_elements = operations.tables["user_role_assignments"]
    assert any(
        getattr(element, "name", None) == "ck_user_role_assignments_role"
        for element in role_elements
    )
    approval_elements = operations.tables["source_approvals"]
    assert {
        "ck_source_approvals_status",
        "ck_source_approvals_approved_fields",
        "ck_source_approvals_disabled_fields",
        "ck_source_approvals_effective_date_range",
    }.issubset(
        {
            getattr(element, "name", None)
            for element in approval_elements
            if getattr(element, "name", None)
        }
    )


def test_initial_migration_downgrade_drops_tables_and_extensions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _load_initial_migration()
    operations = _MigrationOperations()
    monkeypatch.setattr(migration, "op", operations)

    migration.downgrade()

    assert operations.dropped_tables == [
        "ingestion_jobs",
        "reviewer_audit_events",
        "user_role_assignments",
        "referrals",
        "source_fragments",
        "source_approvals",
        "source_versions",
        "sources",
    ]
    assert operations.extensions == [
        "DROP EXTENSION IF EXISTS vector",
        "DROP EXTENSION IF EXISTS pgcrypto",
    ]


def test_model_metadata_contains_governance_tables_and_integrity_constraints() -> None:
    assert {
        "sources",
        "source_versions",
        "source_approvals",
        "source_fragments",
        "referrals",
        "user_role_assignments",
        "reviewer_audit_events",
        "ingestion_jobs",
    }.issubset(Base.metadata.tables)

    source_version_constraints = {
        constraint.name for constraint in Base.metadata.tables["source_versions"].constraints
    }
    assert "uq_source_versions_source_fingerprint" in source_version_constraints
    assert "ck_source_versions_parse_status" in source_version_constraints


def test_canonical_source_url_is_normalized_and_rejects_unsafe_urls() -> None:
    assert normalize_https_url(" HTTPS://WWW.PNW.EDU:443/policy#section ") == (
        "https://www.pnw.edu/policy"
    )
    with pytest.raises(ValueError):
        normalize_https_url("http://pnw.edu/policy")
    with pytest.raises(ValueError):
        normalize_https_url("https://user:password@pnw.edu/policy")

    source = Source(
        canonical_url="HTTPS://WWW.PNW.EDU:443/policy",
        title="Policy",
        media_type="text/html",
        owner_subject="owner",
        owner_organization="PNW",
    )
    assert source.canonical_url == "https://www.pnw.edu/policy"


@pytest.mark.asyncio
async def test_database_enforces_unique_normalized_source_url(
    db_session: AsyncSession,
) -> None:
    await create_source(db_session, canonical_url="https://pnw.edu/policy")

    with pytest.raises(IntegrityError):
        await create_source(db_session, canonical_url="HTTPS://PNW.EDU:443/policy")


@pytest.mark.asyncio
async def test_database_enforces_source_version_hash_uniqueness_per_source(
    db_session: AsyncSession,
) -> None:
    record = await create_source(db_session, content_fingerprint="same-fingerprint")
    db_session.add(
        SourceVersion(
            id=uuid4(),
            source_id=record.source.id,
            content_fingerprint="same-fingerprint",
            extracted_content_ref="protected://duplicate",
            parse_status=ParseStatus.INTERPRETABLE,
        )
    )

    with pytest.raises(IntegrityError):
        await db_session.flush()


@pytest.mark.asyncio
async def test_approval_and_role_database_checks_reject_unknown_values(
    db_session: AsyncSession,
) -> None:
    record = await create_source(db_session)
    record.approval.status = "unknown"  # type: ignore[assignment]
    db_session.add(
        UserRoleAssignment(
            id=uuid4(),
            institutional_subject="reviewer",
            role="unknown",  # type: ignore[arg-type]
            active=True,
            assigned_by="administrator",
        )
    )

    with pytest.raises(IntegrityError):
        await db_session.flush()


def test_audit_events_are_immutable_and_reject_student_content() -> None:
    audit_event = ReviewerAuditEvent(
        actor_subject="reviewer",
        role=ReviewerRole.REVIEWER,
        action="source.read",
        target_type="source",
        target_id=uuid4(),
        correlation_id=uuid4(),
        details={},
    )
    with pytest.raises(ValueError, match="append-only"):
        _prevent_audit_event_mutation()

    with pytest.raises(ValueError, match="student content"):
        audit_event.details = {"nested": {"student-question": "not allowed"}}

    approval = SourceApproval(
        source_version_id=uuid4(),
        status=ApprovalStatus.CANDIDATE,
        effective_context={},
    )
    fragment = SourceFragment(
        source_version_id=uuid4(),
        locator="section-1",
        extracted_text="Policy",
        excerpt="Policy",
        extraction_status="interpretable",
    )
    assert approval.status == ApprovalStatus.CANDIDATE
    assert fragment.locator == "section-1"
