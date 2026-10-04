from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.dialects import postgresql

from app.api.schemas.chat import QuestionContext
from app.chat.retrieval import EMBEDDING_DIMENSION, retrieval_statement


def test_retrieval_statement_combines_full_text_and_pgvector_ranking() -> None:
    statement = retrieval_statement(
        "registration deadline",
        [0.0] * EMBEDDING_DIMENSION,
        QuestionContext(academicTerm="Fall 2026"),
        as_of=date(2026, 10, 3),
    )
    sql = str(statement.compile(dialect=postgresql.dialect()))

    assert "plainto_tsquery" in sql
    assert "ts_rank_cd" in sql
    assert "<=>" in sql
    assert "source_approvals.status" in sql
    assert "sources.current_version_id = source_versions.id" in sql
    assert "effective_date_end" in sql
    assert "source_fragments.extraction_status" in sql


def test_retrieval_statement_uses_lexical_only_when_no_embedding_is_supplied() -> None:
    statement = retrieval_statement("registration deadline")
    sql = str(statement.compile(dialect=postgresql.dialect()))

    assert "plainto_tsquery" in sql
    assert "source_fragments.embedding <=>" not in sql
    assert "source_fragments.extraction_status" in sql


def test_retrieval_rejects_embedding_with_wrong_dimension() -> None:
    with pytest.raises(ValueError, match=f"{EMBEDDING_DIMENSION} values"):
        retrieval_statement("registration deadline", [0.0, 1.0])
