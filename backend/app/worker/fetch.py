from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import httpx


@dataclass(frozen=True, slots=True)
class FetchedSource:
    url: str
    content: bytes
    content_type: str
    content_fingerprint: str
    protected_ref: str


def _normalize_content_type(value: str | None) -> str:
    if not value:
        return "application/octet-stream"
    return value.split(";", 1)[0].strip().lower() or "application/octet-stream"


def _default_storage_root() -> Path:
    return Path.cwd() / ".protected-content"


def _local_document_bytes(path_like: str) -> bytes:
    target = Path(path_like.replace("file://", ""))
    if not target.exists():
        raise FileNotFoundError(f"Document path not found: {path_like}")
    return target.read_bytes()


def protected_content_ref(
    *,
    source_id: UUID | str,
    content: bytes,
    version_id: UUID | str | None = None,
    storage_root: str | Path | None = None,
) -> str:
    """Persist content to a protected local location and return a stable reference."""
    source_key = str(source_id)
    file_hash = hashlib.sha256(content).hexdigest()
    destination_root = Path(storage_root) if storage_root is not None else _default_storage_root()

    if version_id is None:
        relative_path = Path(source_key) / f"{file_hash}.bin"
    else:
        relative_path = Path(source_key) / str(version_id) / f"{file_hash}.bin"

    target_file = destination_root / relative_path
    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_bytes(content)
    return f"protected://{relative_path.as_posix()}"


async def fetch_source(
    url: str,
    *,
    timeout: float = 15.0,
    client: httpx.AsyncClient | None = None,
    storage_root: str | Path | None = None,
) -> FetchedSource:
    """Fetch a source URL and return normalized content plus a protected content reference."""
    if not url or not url.strip():
        raise ValueError("A source URL is required.")

    if url.startswith("file://") or Path(url).exists():
        content = _local_document_bytes(url)
        header_type = _normalize_content_type(Path(url).suffix.lower() or None)
        fingerprint = hashlib.sha256(content).hexdigest()
        protected_ref = protected_content_ref(
            source_id=f"source-{fingerprint[:12]}",
            content=content,
            version_id=None,
            storage_root=storage_root,
        )
        return FetchedSource(
            url=url,
            content=content,
            content_type=header_type,
            content_fingerprint=f"sha256:{fingerprint}",
            protected_ref=protected_ref,
        )

    session = client or httpx.AsyncClient(follow_redirects=True)
    close_client = client is None
    try:
        response = await session.get(url, timeout=timeout)
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Failed to fetch source {url!r}: {exc}") from exc
    finally:
        if close_client:
            await session.aclose()

    if response.status_code >= 400:
        raise RuntimeError(f"Received HTTP {response.status_code} while fetching {url!r}.")

    content = response.content
    header_type = _normalize_content_type(response.headers.get("Content-Type"))
    fingerprint = hashlib.sha256(content).hexdigest()
    protected_ref = protected_content_ref(
        source_id=f"source-{fingerprint[:12]}",
        content=content,
        version_id=None,
        storage_root=storage_root,
    )
    return FetchedSource(
        url=url,
        content=content,
        content_type=header_type,
        content_fingerprint=f"sha256:{fingerprint}",
        protected_ref=protected_ref,
    )


async def fetch_text_source(
    url: str,
    *,
    timeout: float = 15.0,
    client: httpx.AsyncClient | None = None,
) -> str:
    """Fetch a text document and decode it into a Unicode string."""
    result = await fetch_source(url, timeout=timeout, client=client)
    try:
        return result.content.decode("utf-8")
    except UnicodeDecodeError:
        return result.content.decode("utf-8", errors="replace")


async def extract_protected_content(
    *,
    source_id: UUID | str,
    content: bytes,
    version_id: UUID | str | None = None,
    storage_root: str | Path | None = None,
) -> str:
    """Alias for protected-content storage used by the worker pipeline."""
    return protected_content_ref(
        source_id=source_id,
        content=content,
        version_id=version_id,
        storage_root=storage_root,
    )


__all__ = [
    "FetchedSource",
    "extract_protected_content",
    "fetch_source",
    "fetch_text_source",
    "protected_content_ref",
]
