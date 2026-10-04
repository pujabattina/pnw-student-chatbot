from __future__ import annotations

from collections.abc import Sequence
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.chat import Citation
from app.chat import retrieval
from app.chat.citations import assemble_citations
from app.chat.retrieval import RetrievalResult, retrieve_fragments
from app.core.embedding import EMBEDDING_DIMENSION


class _Session(AsyncSession):
    def __init__(self, rows: Sequence[tuple[object, object, float, float]]) -> None:
        super().__init__()
        self.rows = rows

    async def execute(self, statement: object) -> SimpleNamespace:
        return SimpleNamespace(all=lambda: self.rows)


@pytest.mark.asyncio
async def test_retrieval_ranks_results_and_preserves_source_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(retrieval, "build_embedding", lambda _question: [0.0] * EMBEDDING_DIMENSION)
    source = SimpleNamespace(
        id=uuid4(),
        title="Registration Guide",
        canonical_url="https://www.pnw.edu/registration",
    )
    fragment = SimpleNamespace(
        locator="section-4",
        excerpt="Fall registration deadlines close on Friday.",
        extracted_text="Fall registration deadlines close on Friday.",
    )
    session = _Session([(fragment, source, 0.5, 0.8)])

    results = await retrieve_fragments(session, "registration deadline")

    assert len(results) == 1
    assert results[0].source.title == "Registration Guide"
    assert results[0].locator == "section-4"


def test_citations_preserve_locator_and_url() -> None:
    source = type(
        "SourceStub",
        (),
        {
            "id": uuid4(),
            "title": "Student Handbook",
            "canonical_url": "https://www.pnw.edu/handbook",
        },
    )()
    fragment = type(
        "FragmentStub",
        (),
        {"locator": "table-3", "source": source},
    )()

    result = RetrievalResult(
        fragment=fragment,
        source=source,
        locator="table-3",
        score=0.93,
        lexical_score=0.84,
        semantic_score=0.8,
        coverage=0.8,
    )

    citations = assemble_citations([result])
    assert isinstance(citations[0], Citation)
    assert citations[0].source_id == source.id
    assert citations[0].title == "Student Handbook"
    assert citations[0].locator == "table-3"
    assert str(citations[0].url) == "https://www.pnw.edu/handbook"
