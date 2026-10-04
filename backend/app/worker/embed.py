from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from collections.abc import Sequence
from functools import lru_cache
from typing import Any

from fastembed import TextEmbedding
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.embedding import EMBEDDING_DIMENSION, EMBEDDING_MODEL
from app.db.models.source_fragment import SourceFragment
from app.worker.parse import ParsedFragment, chunk_fragments, parse_document

_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+")


def lexical_search_vector(text: str) -> str:
    """Build a compact textual index from the fragment text."""
    tokens = {token.lower() for token in _TOKEN_PATTERN.findall(text) if len(token) > 1}
    return " ".join(sorted(tokens))


@lru_cache(maxsize=1)
def _local_embedding_model() -> TextEmbedding:
    return TextEmbedding(model_name=EMBEDDING_MODEL)


def embed_texts(texts: Sequence[str], *, dimension: int = EMBEDDING_DIMENSION) -> list[list[float]]:
    """Create local semantic embeddings for a sequence of strings."""
    if dimension != EMBEDDING_DIMENSION:
        raise ValueError(f"Embedding dimension must be {EMBEDDING_DIMENSION}.")
    if not texts:
        return []

    embeddings = [
        [float(value) for value in embedding]
        for embedding in _local_embedding_model().embed(list(texts))
    ]
    if len(embeddings) != len(texts):
        raise ValueError("FastEmbed returned an unexpected number of embeddings.")
    if any(len(embedding) != EMBEDDING_DIMENSION for embedding in embeddings):
        raise ValueError(
            f"FastEmbed returned an embedding that is not {EMBEDDING_DIMENSION}-dimensional."
        )
    return embeddings


def build_embedding(text: str, *, dimension: int = EMBEDDING_DIMENSION) -> list[float]:
    """Create one local semantic embedding vector for a piece of text."""
    return embed_texts([text], dimension=dimension)[0]


def embedding_reference(text: str) -> str:
    """Return a stable reference string for the embedded content."""
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return f"embedding://{digest}"


def _to_fragment_payload(
    fragment: ParsedFragment,
    embedding: Sequence[float],
) -> dict[str, Any]:
    text = fragment.text.strip()
    return {
        "locator": fragment.locator,
        "text": text,
        "excerpt": fragment.excerpt[:220],
        "extraction_status": fragment.extraction_status,
        "lexical_search_vector": lexical_search_vector(text),
        "embedding_reference": embedding_reference(text),
        "embedding": list(embedding),
        "display_excerpt": fragment.excerpt[:220],
    }


def build_fragment_embeddings(
    text: str,
    *,
    media_type: str | None = None,
    source_url: str | None = None,
    max_chars: int = 1200,
    overlap_chars: int = 200,
) -> list[dict[str, Any]]:
    """Run document extraction -> chunking -> embedding for the word-bearing RAG pipeline."""
    parsed = parse_document(text, media_type=media_type, source_url=source_url)
    return _build_fragment_embeddings_from_parsed(parsed)


def _build_fragment_embeddings_from_parsed(
    parsed: list[ParsedFragment],
) -> list[dict[str, Any]]:
    chunked = chunk_fragments(parsed)
    fragments = [fragment for fragment in chunked if fragment.text]
    embeddings = embed_texts([fragment.text.strip() for fragment in fragments])
    return [
        _to_fragment_payload(fragment, embedding)
        for fragment, embedding in zip(fragments, embeddings, strict=True)
    ]


async def persist_fragment_embeddings(
    session: AsyncSession,
    *,
    source_version_id: object,
    fragment_payloads: Sequence[dict[str, Any]],
) -> int:
    """Persist chunk rows to source_fragments and return the number written."""
    rows_written = 0
    for payload in fragment_payloads:
        fragment = SourceFragment(
            source_version_id=source_version_id,
            locator=str(payload["locator"]),
            extracted_text=str(payload["text"]),
            excerpt=str(payload["excerpt"]),
            extraction_status=str(payload["extraction_status"]),
            lexical_search_vector=str(payload["lexical_search_vector"]),
            embedding_reference=str(payload["embedding_reference"]),
            embedding=list(payload["embedding"]),
            display_excerpt=str(payload["display_excerpt"]),
        )
        session.add(fragment)
        rows_written += 1
    await session.flush()
    return rows_written


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    """Compute cosine similarity between two embedding vectors."""
    if len(left) != len(right):
        raise ValueError("Embedding vectors must have the same length.")

    numerator = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return numerator / (left_norm * right_norm)


def demo_pipeline(
    document_name: str, text: str, *, media_type: str | None = None
) -> dict[str, Any]:
    """Build a small in-memory demo record for manual RAG reporting."""
    parsed = parse_document(text, media_type=media_type, source_url=document_name)
    fragments = _build_fragment_embeddings_from_parsed(parsed)
    preview = [item["text"][:180] for item in fragments[:5]]
    return {
        "document_name": document_name,
        "extracted_character_count": sum(len(fragment.text) for fragment in parsed),
        "chunk_count": len(fragments),
        "first_chunks": preview,
        "embedding_dimension": EMBEDDING_DIMENSION,
        "rows_written": len(fragments),
    }


def _parse_cli_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "RAG demo for the source fetch/parse/chunk/embed pipeline using "
            f"the local {EMBEDDING_MODEL} model."
        )
    )
    parser.add_argument(
        "--document-name",
        default="demo-document",
        help="Document name to report in the demo output",
    )
    parser.add_argument(
        "--text",
        default="",
        help="Raw document text to process. If omitted, a small built-in demo is used.",
    )
    parser.add_argument(
        "--media-type",
        default="text/html",
        help="Media type to parse as, such as text/html or application/pdf",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_cli_args()
    demo_text = args.text or (
        "<html><body><h2>Section 1</h2>"
        "<p>Registration closes on October 20 for both Fall and Spring terms.</p>"
        "<h2>Section 2</h2>"
        "<p>Students should confirm program requirements with their adviser before registering.</p>"
        "</body></html>"
    )
    print(
        json.dumps(
            demo_pipeline(args.document_name, demo_text, media_type=args.media_type), indent=2
        )
    )


__all__ = [
    "build_embedding",
    "build_fragment_embeddings",
    "cosine_similarity",
    "demo_pipeline",
    "embed_texts",
    "embedding_reference",
    "lexical_search_vector",
    "persist_fragment_embeddings",
]
