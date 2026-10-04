from __future__ import annotations

from datetime import date

from sqlalchemy.dialects import postgresql

from app.api.schemas.chat import QuestionContext
from app.corpus.eligibility import (
    eligible_source_fragment_statement,
    eligible_source_version_statement,
)


def test_version_eligibility_query_requires_current_approved_interpretable_sources() -> None:
    statement = eligible_source_version_statement(as_of=date(2026, 10, 3))
    sql = str(statement.compile(dialect=postgresql.dialect()))

    assert "sources.current_version_id = source_versions.id" in sql
    assert "source_versions.parse_status" in sql
    assert "source_versions.change_detected_at IS NULL" in sql
    assert "source_versions.withdrawn_at IS NULL" in sql
    assert "source_approvals.status" in sql
    assert "effective_date_start" in sql
    assert "effective_date_end" in sql
    assert "DISTINCT" in sql


def test_fragment_query_matches_each_provided_context_and_keeps_scoped_records_out() -> None:
    statement = eligible_source_fragment_statement(
        QuestionContext(
            campus="Hammond",
            college="Engineering",
            program="Computer Science",
            course="CS 101",
            academicTerm="Fall 2026",
        ),
        as_of=date(2026, 10, 3),
    )
    sql = str(statement.compile(dialect=postgresql.dialect()))

    assert "source_fragments.source_version_id = source_versions.id" in sql
    assert sql.count("@>") == 5
    assert "effective_date_start" in sql
    assert "effective_date_end" in sql


def test_unprovided_context_excludes_approvals_scoped_to_that_dimension() -> None:
    statement = eligible_source_version_statement(
        QuestionContext(campus="Hammond"),
        as_of=date(2026, 10, 3),
    )
    compiled = statement.compile(dialect=postgresql.dialect())
    sql = str(compiled)

    assert sql.count("@>") == 1
    assert ["Hammond"] in compiled.params.values()
