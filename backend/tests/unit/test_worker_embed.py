from __future__ import annotations

from unittest.mock import Mock

import pytest

from app.core.embedding import EMBEDDING_DIMENSION, EMBEDDING_MODEL
from app.db.models.source_fragment import SourceFragment
from app.worker import embed


def test_embedding_dimension_comes_from_fastembed_model_metadata() -> None:
    assert EMBEDDING_MODEL == "BAAI/bge-small-en-v1.5"
    assert EMBEDDING_DIMENSION == 384
    assert SourceFragment.__table__.c.embedding.type.dim == EMBEDDING_DIMENSION


def test_embed_texts_uses_local_model_and_returns_vectors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vectors = [[float(index)] * EMBEDDING_DIMENSION for index in range(2)]
    model = Mock()
    model.embed.return_value = vectors
    monkeypatch.setattr(embed, "_local_embedding_model", lambda: model)

    result = embed.embed_texts(["first text", "second text"])

    assert result == vectors
    model.embed.assert_called_once_with(["first text", "second text"])


def test_build_embedding_returns_one_local_vector(monkeypatch: pytest.MonkeyPatch) -> None:
    model = Mock()
    model.embed.return_value = [[0.25] * EMBEDDING_DIMENSION]
    monkeypatch.setattr(embed, "_local_embedding_model", lambda: model)

    result = embed.build_embedding("Registration closes October 20.")

    assert result == [0.25] * EMBEDDING_DIMENSION


def test_embed_texts_does_not_require_openai_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    model = Mock()
    model.embed.return_value = [[0.25] * EMBEDDING_DIMENSION]
    monkeypatch.setattr(embed, "_local_embedding_model", lambda: model)

    assert len(embed.embed_texts(["text"])[0]) == EMBEDDING_DIMENSION


def test_embed_texts_rejects_non_pgvector_dimension() -> None:
    with pytest.raises(ValueError, match=f"Embedding dimension must be {EMBEDDING_DIMENSION}"):
        embed.embed_texts(["text"], dimension=EMBEDDING_DIMENSION * 2)


def test_embed_texts_rejects_unexpected_local_vector_dimension(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = Mock()
    model.embed.return_value = [[0.25] * (EMBEDDING_DIMENSION - 1)]
    monkeypatch.setattr(embed, "_local_embedding_model", lambda: model)

    message = f"FastEmbed returned an embedding that is not {EMBEDDING_DIMENSION}-dimensional"
    with pytest.raises(ValueError, match=message):
        embed.embed_texts(["text"])


def test_demo_pipeline_reports_extracted_and_persistable_row_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(
        embed,
        "embed_texts",
        lambda texts: [[0.25] * EMBEDDING_DIMENSION for _ in texts],
    )

    result = embed.demo_pipeline(
        "demo.html",
        "<html><body><p>Alpha</p><p>Beta</p></body></html>",
        media_type="text/html",
    )

    assert result["extracted_character_count"] == len("Alpha Beta")
    assert result["chunk_count"] == 1
    assert result["embedding_dimension"] == EMBEDDING_DIMENSION
    assert result["rows_written"] == 1
