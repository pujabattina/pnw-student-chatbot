from __future__ import annotations

import ipaddress
from datetime import datetime
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID, uuid4

from sqlalchemy import DateTime, String, Uuid, event, func, inspect, text
from sqlalchemy.orm import Mapped, mapped_column, validates

from app.db.models.base import Base


def normalize_https_url(value: str) -> str:
    url = value.strip()
    if not url or any(character.isspace() for character in url):
        raise ValueError("canonical_url must be a valid HTTPS URL.")

    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("canonical_url must be a valid HTTPS URL.") from exc

    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError("canonical_url must be an HTTPS URL without credentials.")

    hostname = parsed.hostname
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        normalized_host = hostname.rstrip(".").encode("idna").decode("ascii").lower()
        if not normalized_host:
            raise ValueError("canonical_url must include a hostname.") from None
        if ":" in hostname:
            raise ValueError("canonical_url contains an invalid hostname.") from None
    else:
        normalized_host = address.compressed
        if address.version == 6:
            normalized_host = f"[{normalized_host}]"

    netloc = normalized_host
    if port is not None and port != 443:
        netloc = f"{netloc}:{port}"

    return urlunsplit(("https", netloc, parsed.path or "/", parsed.query, ""))


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    canonical_url: Mapped[str] = mapped_column(
        String(2048),
        nullable=False,
        unique=True,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    media_type: Mapped[str] = mapped_column(String(100), nullable=False)
    owner_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    owner_organization: Mapped[str] = mapped_column(String(255), nullable=False)
    current_version_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    @validates("canonical_url")
    def _normalize_canonical_url(self, _key: str, value: str) -> str:
        return normalize_https_url(value)


@event.listens_for(Source, "before_update")
def _prevent_created_at_update(_mapper: object, _connection: object, source: Source) -> None:
    if inspect(source).attrs.created_at.history.has_changes():
        raise ValueError("Source.created_at is immutable.")
