from __future__ import annotations

from fastembed import TextEmbedding

EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
EMBEDDING_DIMENSION = TextEmbedding.get_embedding_size(EMBEDDING_MODEL)
