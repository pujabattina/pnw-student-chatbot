from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, String, Text, Uuid, text
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.embedding import EMBEDDING_DIMENSION
from app.db.models.base import Base


@compiles(Vector, "sqlite")
def _compile_vector_for_sqlite(_type: Vector, _compiler: object, **_kwargs: object) -> str:
    return "TEXT"


if TYPE_CHECKING:
    from app.db.models.source_version import SourceVersion


class SourceFragment(Base):
    __tablename__ = "source_fragments"

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    source_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("source_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    locator: Mapped[str] = mapped_column(String(512), nullable=False)
    extracted_text: Mapped[str] = mapped_column(Text, nullable=False)
    excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    extraction_status: Mapped[str] = mapped_column(String(32), nullable=False)
    lexical_search_vector: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(EMBEDDING_DIMENSION), nullable=True
    )
    display_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)

    source_version: Mapped[SourceVersion] = relationship(
        "SourceVersion",
        back_populates="fragments",
    )
