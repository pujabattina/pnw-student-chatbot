from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision = "0003_local_embedding_dimension"
down_revision = "0002_source_fragment_embeddings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("source_fragments", "embedding")
    op.add_column("source_fragments", sa.Column("embedding", Vector(384), nullable=True))


def downgrade() -> None:
    op.drop_column("source_fragments", "embedding")
    op.add_column("source_fragments", sa.Column("embedding", Vector(1536), nullable=True))
