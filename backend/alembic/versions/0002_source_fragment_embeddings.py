from __future__ import annotations

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

from alembic import op

revision = "0002_source_fragment_embeddings"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("source_fragments", sa.Column("embedding", Vector(1536), nullable=True))


def downgrade() -> None:
    op.drop_column("source_fragments", "embedding")
