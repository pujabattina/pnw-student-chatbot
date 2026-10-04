from __future__ import annotations

import argparse
import asyncio
import json
import os
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.embedding import EMBEDDING_DIMENSION
from app.db.models import Source, SourceApproval, SourceFragment, SourceVersion
from app.db.models.source_approval import ApprovalStatus
from app.db.models.source_version import ParseStatus
from app.worker.embed import build_fragment_embeddings, persist_fragment_embeddings
from app.worker.fetch import FetchedSource, extract_protected_content, fetch_source
from app.worker.parse import parse_document

DEFAULT_FIXTURE_PATH = (
    Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "approved_corpus.json"
)


@dataclass(frozen=True, slots=True)
class SeededDocument:
    document_name: str
    url: str
    extracted_character_count: int
    chunk_count: int
    embedding_dimension: int
    rows_written: int


@dataclass(frozen=True, slots=True)
class _PreparedDocument:
    entry: dict[str, Any]
    fetched: FetchedSource
    content_fingerprint: str
    payloads: list[dict[str, Any]]
    extracted_character_count: int
    source_id: UUID
    version_id: UUID
    approval_id: UUID


def load_approved_corpus(path: str | Path | None = None) -> list[dict[str, Any]]:
    fixture_path = Path(path) if path is not None else DEFAULT_FIXTURE_PATH
    with fixture_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    entries = payload.get("entries") if isinstance(payload, dict) else payload
    if not isinstance(entries, list):
        raise ValueError(
            "approved corpus fixture must be a list or an object with an entries list."
        )
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict) or not entry.get("url") or not entry.get("title"):
            raise ValueError(f"approved corpus entry {index + 1} must include title and url.")
    return entries


async def _prepare_document(entry: dict[str, Any]) -> _PreparedDocument:
    url = str(entry["url"])
    storage_root = Path(
        os.getenv("PROTECTED_CONTENT_DIR", str(Path.home() / ".protected-content"))
    )
    fetched = await fetch_source(url, storage_root=storage_root)
    extracted_content = fetched.content.decode("utf-8", errors="replace")
    parsed = parse_document(
        extracted_content,
        media_type=fetched.content_type,
        source_url=url,
    )
    extracted_character_count = sum(len(fragment.text) for fragment in parsed)
    payloads = build_fragment_embeddings(
        extracted_content,
        media_type=fetched.content_type,
        source_url=url,
    )
    if not payloads:
        raise ValueError(f"No interpretable text was extracted from {url}.")

    return _PreparedDocument(
        entry=entry,
        fetched=fetched,
        content_fingerprint=fetched.content_fingerprint,
        payloads=payloads,
        extracted_character_count=extracted_character_count,
        source_id=uuid4(),
        version_id=uuid4(),
        approval_id=uuid4(),
    )


async def seed_approved_corpus(
    session: AsyncSession,
    corpus: list[dict[str, Any]] | None = None,
    *,
    reset: bool = False,
) -> list[SeededDocument]:
    entries = corpus if corpus is not None else load_approved_corpus()
    prepared = [await _prepare_document(entry) for entry in entries]
    written_by_version: dict[UUID, int] = {}
    documents_by_version: dict[UUID, _PreparedDocument] = {}
    reports_by_url: dict[str, SeededDocument] = {}

    async with session.begin():
        if reset:
            await session.execute(delete(SourceFragment))
            await session.execute(delete(SourceApproval))
            await session.execute(delete(SourceVersion))
            await session.execute(delete(Source))

        for document in prepared:
            canonical_url = str(document.entry["url"])
            existing = await session.scalar(
                select(Source).where(Source.canonical_url == canonical_url)
            )
            if existing is not None:
                if existing.current_version_id is None:
                    raise RuntimeError(f"Existing source has no current version: {canonical_url}")
                row_count = await session.scalar(
                    select(func.count(SourceFragment.id)).where(
                        SourceFragment.source_version_id == existing.current_version_id
                    )
                )
                character_count = await session.scalar(
                    select(
                        func.coalesce(
                            func.sum(func.length(SourceFragment.extracted_text)), 0
                        )
                    ).where(SourceFragment.source_version_id == existing.current_version_id)
                )
                reports_by_url[canonical_url] = SeededDocument(
                    document_name=existing.title,
                    url=canonical_url,
                    extracted_character_count=int(character_count or 0),
                    chunk_count=int(row_count or 0),
                    embedding_dimension=EMBEDDING_DIMENSION,
                    rows_written=0,
                )
                continue

            source = Source(
                id=document.source_id,
                canonical_url=canonical_url,
                title=str(document.entry["title"]),
                media_type=document.fetched.content_type,
                owner_subject=str(document.entry["owner_subject"]),
                owner_organization=str(document.entry.get("owner_organization", "PNW")),
            )
            session.add(source)
            await session.flush()

            protected_ref = await extract_protected_content(
                source_id=source.id,
                version_id=document.version_id,
                content=document.fetched.content,
                storage_root=Path(
                    os.getenv("PROTECTED_CONTENT_DIR", str(Path.home() / ".protected-content"))
                ),
            )
            version = SourceVersion(
                id=document.version_id,
                source_id=source.id,
                content_fingerprint=document.content_fingerprint,
                captured_at=datetime.now(UTC),
                extracted_content_ref=protected_ref,
                parse_status=ParseStatus.INTERPRETABLE,
            )
            session.add(version)
            await session.flush()
            source.current_version_id = version.id

            session.add(
                SourceApproval(
                    id=document.approval_id,
                    source_version_id=version.id,
                    status=ApprovalStatus.APPROVED,
                    approver_subject=str(
                        document.entry.get("approver_subject", document.entry["owner_subject"])
                    ),
                    approved_at=datetime.now(UTC),
                    effective_context=document.entry.get("effective_context", {}),
                )
            )
            written_by_version[version.id] = await persist_fragment_embeddings(
                session,
                source_version_id=version.id,
                fragment_payloads=document.payloads,
            )
            documents_by_version[version.id] = document
            reports_by_url[canonical_url] = SeededDocument(
                document_name=str(document.entry["title"]),
                url=canonical_url,
                extracted_character_count=document.extracted_character_count,
                chunk_count=len(document.payloads),
                embedding_dimension=EMBEDDING_DIMENSION,
                rows_written=written_by_version[version.id],
            )

    for version_id, document in documents_by_version.items():
        committed_rows = await session.scalar(
            select(func.count())
            .select_from(SourceFragment)
            .where(SourceFragment.source_version_id == version_id)
        )
        rows_written = written_by_version[version_id]
        if committed_rows != rows_written:
            raise RuntimeError(
                f"Committed fragment count for {document.entry['url']} does not match "
                f"the number written ({committed_rows} != {rows_written})."
            )

    return [reports_by_url[str(entry["url"])] for entry in entries]


async def _create_engine_and_seed(
    *,
    database_url: str | None,
    fixture_path: str | Path,
    reset: bool,
) -> list[SeededDocument]:
    resolved_database_url = database_url or os.getenv("DATABASE_URL")
    if not resolved_database_url:
        raise ValueError(
            "DATABASE_URL is required. Pass --database-url or configure DATABASE_URL."
        )
    engine = create_async_engine(resolved_database_url, future=True)
    async_session_factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    try:
        async with async_session_factory() as session:
            return await seed_approved_corpus(
                session,
                load_approved_corpus(fixture_path),
                reset=reset,
            )
    finally:
        await engine.dispose()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fetch, parse, chunk, embed, and seed the approved PNW corpus."
    )
    parser.add_argument(
        "--fixture",
        default=str(DEFAULT_FIXTURE_PATH),
        help="Path to the approved corpus JSON fixture.",
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="Optional database URL. Defaults to DATABASE_URL.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete all existing source rows before inserting the approved corpus.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate the fixture and report document URLs without writing to the database.",
    )
    return parser


async def _cli_main() -> int:
    args = _build_parser().parse_args()
    fixture_path = Path(args.fixture)
    if not fixture_path.exists():
        raise FileNotFoundError(f"approved corpus fixture not found: {fixture_path}")

    corpus = load_approved_corpus(fixture_path)
    if args.dry_run:
        print(
            json.dumps(
                [
                    {"document_name": entry["title"], "url": entry["url"]}
                    for entry in corpus
                ],
                indent=2,
            )
        )
        return 0

    reports = await _create_engine_and_seed(
        database_url=args.database_url,
        fixture_path=fixture_path,
        reset=args.reset,
    )
    print(json.dumps([asdict(report) for report in reports], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_cli_main()))
