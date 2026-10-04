from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import AnyUrl, BaseModel, ConfigDict, field_validator


def _to_camel(value: str) -> str:
    first, *rest = value.split("_")
    return first + "".join(part.capitalize() for part in rest)


class ReviewSchema(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        extra="forbid",
        populate_by_name=True,
    )


class SourceInput(ReviewSchema):
    canonical_url: AnyUrl
    title: str
    owner_subject: str
    effective_context: dict[str, Any]

    @field_validator("canonical_url")
    @classmethod
    def _require_https(cls, value: AnyUrl) -> AnyUrl:
        if value.scheme != "https":
            raise ValueError("canonicalUrl must use HTTPS.")
        return value


class ChangeEventType(StrEnum):
    CHANGED = "changed"
    WITHDRAWN = "withdrawn"


class ChangeEvent(ReviewSchema):
    observed_at: datetime
    content_fingerprint: str
    event: ChangeEventType
