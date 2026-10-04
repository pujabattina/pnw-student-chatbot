from __future__ import annotations

from collections.abc import Sequence

from app.api.schemas.chat import Citation
from app.chat.retrieval import RetrievalResult


def assemble_citations(results: Sequence[RetrievalResult]) -> list[Citation]:
    """Build citation schema objects from eligible retrieval results."""
    return [
        Citation.model_validate(
            {
                "sourceId": result.source.id,
                "title": result.source.title,
                "url": result.source.canonical_url,
                "locator": result.locator,
            }
        )
        for result in results
    ]
