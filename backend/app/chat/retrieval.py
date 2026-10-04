from __future__ import annotations

import asyncio
import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import Float, and_, cast, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select
from sqlalchemy.sql.elements import ColumnElement

from app.api.schemas.chat import QuestionContext
from app.core.embedding import EMBEDDING_DIMENSION
from app.corpus.eligibility import eligible_source_fragment_statement
from app.db.models.source import Source
from app.db.models.source_fragment import SourceFragment
from app.worker.embed import build_embedding

_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+")
_STOP_WORDS = {
    "about",
    "and",
    "are",
    "does",
    "for",
    "from",
    "how",
    "what",
    "when",
    "where",
    "which",
    "with",
}


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    fragment: SourceFragment
    score: float
    lexical_score: float
    semantic_score: float
    coverage: float
    locator: str
    source: Source


def _tokens(value: str) -> set[str]:
    return {
        token.lower()
        for token in _TOKEN_PATTERN.findall(value)
        if len(token) > 1 and token.lower() not in _STOP_WORDS
    }


def _coverage(question: str, text: str) -> float:
    query_terms = _tokens(question)
    if not query_terms:
        return 0.0
    return len(query_terms & _tokens(text)) / len(query_terms)


def _normalized_lexical_score(rank: float) -> float:
    return min(1.0, max(0.0, 1.0 - math.exp(-4.0 * max(rank, 0.0))))


def _hybrid_score(lexical_score: float, semantic_score: float) -> float:
    return 0.5 * lexical_score + 0.5 * semantic_score


def retrieval_statement(
    question: str,
    query_embedding: Sequence[float] | None = None,
    context: QuestionContext | None = None,
    *,
    as_of: date | None = None,
) -> Select[Any]:
    """Build a PostgreSQL hybrid search over only eligible source fragments."""
    if query_embedding is not None and len(query_embedding) != EMBEDDING_DIMENSION:
        raise ValueError(f"query_embedding must contain {EMBEDDING_DIMENSION} values.")

    lexical_document = func.to_tsvector(
        "english",
        func.concat_ws(
            " ",
            SourceFragment.lexical_search_vector,
            SourceFragment.extracted_text,
            SourceFragment.excerpt,
        ),
    )
    lexical_query = func.plainto_tsquery("english", question)
    lexical_rank = func.ts_rank_cd(lexical_document, lexical_query)
    relevant: ColumnElement[bool]

    if query_embedding is None:
        semantic_score = cast(0.0, Float)
        relevant = lexical_document.op("@@")(lexical_query)
    else:
        semantic_score = 1.0 - SourceFragment.embedding.cosine_distance(list(query_embedding))
        relevant = or_(
            lexical_document.op("@@")(lexical_query),
            SourceFragment.embedding.is_not(None),
        )

    eligible_fragments = eligible_source_fragment_statement(context, as_of=as_of)
    return (
        eligible_fragments.add_columns(
            Source,
            lexical_rank.label("lexical_rank"),
            semantic_score.label("semantic_score"),
        )
        .where(and_(relevant, SourceFragment.extraction_status == "interpretable"))
        .order_by(
            (lexical_rank + semantic_score).desc(),
            SourceFragment.id,
        )
    )


async def retrieve_fragments(
    session: AsyncSession,
    question: str,
    *,
    query_embedding: Sequence[float] | None = None,
    context: QuestionContext | None = None,
    top_k: int = 5,
    relevance_threshold: float = 0.25,
    coverage_threshold: float = 0.2,
    as_of: date | None = None,
) -> list[RetrievalResult]:
    """Retrieve and rank relevant fragments from the approved current corpus."""
    if not question.strip():
        return []
    if top_k < 1:
        raise ValueError("top_k must be at least one.")
    if not 0.0 <= relevance_threshold <= 1.0:
        raise ValueError("relevance_threshold must be between zero and one.")
    if not 0.0 <= coverage_threshold <= 1.0:
        raise ValueError("coverage_threshold must be between zero and one.")
    if query_embedding is not None and any(not math.isfinite(value) for value in query_embedding):
        raise ValueError("query_embedding values must be finite.")
    if query_embedding is None:
        query_embedding = await asyncio.to_thread(build_embedding, question)

    statement = retrieval_statement(
        question,
        query_embedding,
        context,
        as_of=as_of,
    )
    rows = (await session.execute(statement)).all()
    results: list[RetrievalResult] = []
    for fragment, source, lexical_rank, raw_semantic_score in rows:
        lexical_score = _normalized_lexical_score(float(lexical_rank or 0.0))
        semantic_score = min(1.0, max(0.0, float(raw_semantic_score or 0.0)))
        content = " ".join(value for value in (fragment.excerpt, fragment.extracted_text) if value)
        coverage = _coverage(question, content)
        score = _hybrid_score(lexical_score, semantic_score)
        if score < relevance_threshold:
            continue
        if coverage < coverage_threshold and semantic_score < relevance_threshold:
            continue
        results.append(
            RetrievalResult(
                fragment=fragment,
                score=score,
                lexical_score=lexical_score,
                semantic_score=semantic_score,
                coverage=coverage,
                locator=fragment.locator,
                source=source,
            )
        )

    results.sort(
        key=lambda result: (result.score, result.coverage, result.lexical_score),
        reverse=True,
    )
    return results[:top_k]
