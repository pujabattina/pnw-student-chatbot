from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.embedding import EMBEDDING_DIMENSION
from app.db.models.base import Base
from app.db.models.source import Source
from app.db.models.source_fragment import SourceFragment
from app.db.models.source_version import ParseStatus, SourceVersion
from app.worker import embed as embed_worker
from app.worker.embed import build_fragment_embeddings, persist_fragment_embeddings
from app.worker.parse import chunk_fragments, parse_document


@pytest.mark.asyncio
async def test_parse_document_extracts_html_and_keeps_section_locators() -> None:
    html = """
    <html><body>
      <h2>Section 1</h2>
      <p>Registration closes on October 20 for Fall 2026.</p>
      <h2>Table 7</h2>
      <table><tr><td>Deadline</td><td>October 20</td></tr></table>
    </body></html>
    """
    fragments = parse_document(
        html, media_type="text/html", source_url="https://example.com/registration.html"
    )

    assert fragments
    assert any("section" in fragment.locator.lower() for fragment in fragments)
    assert any("table" in fragment.locator.lower() for fragment in fragments)
    assert "Registration closes on October 20" in " ".join(fragment.text for fragment in fragments)


def test_parse_document_excludes_html_implementation_and_boilerplate() -> None:
    html = """
    <html><head>
      <script type="application/ld+json">
        {"@context":"https://schema.org","@type":"WebPage","name":"Internal metadata"}
      </script>
      <script>window.analyticsQueue.push("tracking payload");</script>
      <style>.page { display: none; }</style>
    </head><body>
      <nav>Home Admissions Programs</nav>
      <main><h1>PNW Registration</h1><p>Registration opens August 1.</p></main>
      <footer>Privacy policy Contact us</footer>
      <div class="analytics">tracking implementation payload</div>
      <noscript>Enable JavaScript to continue.</noscript>
      <template>Search schema implementation</template>
    </body></html>
    """
    fragments = parse_document(html, media_type="text/html")
    extracted = " ".join(fragment.text for fragment in fragments)

    assert "Internal metadata" not in extracted
    assert "tracking payload" not in extracted
    assert "tracking implementation payload" not in extracted
    assert "Home Admissions Programs" not in extracted
    assert "Privacy policy Contact us" not in extracted
    assert "Enable JavaScript to continue" not in extracted
    assert "Search schema implementation" not in extracted
    assert "PNW Registration" in extracted
    assert "Registration opens August 1." in extracted


def test_parse_document_preserves_visible_pnw_sections_lists_and_tables() -> None:
    html = """
    <html><body><main>
      <h1>Purdue University Northwest</h1>
      <h2>Section 1: Enrollment</h2>
      <p>Students should review the academic calendar before enrolling.</p>
      <ul><li>Check registration dates.</li><li>Contact your academic adviser.</li></ul>
      <h2>Table 7: Registration Dates</h2>
      <table><tr><th>Term</th><th>Deadline</th></tr>
      <tr><td>Fall 2026</td><td>October 20</td></tr></table>
    </main></body></html>
    """
    fragments = parse_document(html, media_type="text/html")
    extracted = " ".join(fragment.text for fragment in fragments)

    assert "Purdue University Northwest" in extracted
    assert "Students should review the academic calendar before enrolling." in extracted
    assert "Check registration dates." in extracted
    assert "Contact your academic adviser." in extracted
    assert "Fall 2026" in extracted
    assert "Deadline" in extracted
    assert "October 20" in extracted


@pytest.mark.asyncio
async def test_chunking_splits_long_extracted_text() -> None:
    long_text = "Registration closes on October 20. " * 350
    fragments = parse_document(long_text, media_type="text/plain")
    chunked = chunk_fragments(fragments)

    assert len(chunked) > 1
    assert max(len(fragment.text) for fragment in chunked) <= 1200
    assert all(fragment.text for fragment in chunked)


@pytest.mark.asyncio
async def test_persist_fragment_embeddings_writes_source_fragment_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        embed_worker,
        "embed_texts",
        lambda texts, *, dimension=EMBEDDING_DIMENSION: [[0.1] * dimension for _ in texts],
    )
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with AsyncSession(engine) as session:
        source = Source(
            id=uuid4(),
            canonical_url="https://pnw.edu/test/worker-pipeline",
            title="Worker pipeline demo",
            media_type="text/html",
            owner_subject="source-owner",
            owner_organization="PNW",
        )
        session.add(source)
        await session.flush()

        version = SourceVersion(
            id=uuid4(),
            source_id=source.id,
            content_fingerprint="sha256:demo-embedding",
            captured_at=datetime.now(UTC),
            extracted_content_ref="protected://demo/source-version",
            parse_status=ParseStatus.INTERPRETABLE,
        )
        session.add(version)
        await session.flush()

        source_text = (
            "Registration closes on October 20. Students should check the catalog before "
            "enrollment."
        )
        rows = build_fragment_embeddings(
            source_text,
            media_type="text/plain",
            source_url="https://example.com/registration.txt",
        )
        written = await persist_fragment_embeddings(
            session,
            source_version_id=version.id,
            fragment_payloads=rows,
        )
        await session.commit()

        assert written == len(rows)
        assert all(len(item["embedding"]) == EMBEDDING_DIMENSION for item in rows)

    async with AsyncSession(engine) as session:
        count = await session.scalar(select(func.count()).select_from(SourceFragment))
        assert count == len(
            build_fragment_embeddings(
                source_text,
                media_type="text/plain",
                source_url="https://example.com/registration.txt",
            )
        )
