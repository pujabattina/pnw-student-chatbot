from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class ErrorSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ApiError(ErrorSchema):
    detail: str
    code: str | None = None
    correlation_id: str | None = Field(default=None, alias="correlationId")


class ValidationIssue(ErrorSchema):
    loc: list[str | int]
    msg: str
    type: str


class ValidationError(ErrorSchema):
    detail: Annotated[list[ValidationIssue], Field(min_length=1)]
    code: str = "validation_error"
    correlation_id: str | None = Field(default=None, alias="correlationId")
