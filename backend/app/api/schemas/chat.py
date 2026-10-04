from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from pydantic import AnyUrl, BaseModel, ConfigDict, Field, StringConstraints


class Schema(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class QuestionContext(Schema):
    campus: Literal["Hammond", "Westville"] | None = None
    college: Annotated[str, StringConstraints(max_length=120)] | None = None
    program: Annotated[str, StringConstraints(max_length=160)] | None = None
    course: Annotated[str, StringConstraints(max_length=40)] | None = None
    academic_term: Annotated[str, StringConstraints(max_length=40)] | None = Field(
        default=None,
        alias="academicTerm",
    )


class ChatRequest(Schema):
    question: Annotated[str, StringConstraints(min_length=1, max_length=4000)]
    context: QuestionContext | None = None


class Citation(Schema):
    source_id: UUID = Field(alias="sourceId")
    title: str
    url: AnyUrl
    locator: str | None = None


class Referral(Schema):
    name: str
    url: AnyUrl | None = None
    email: Annotated[str, StringConstraints(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")] | None = None
    phone: str | None = None


class SupportedAnswer(Schema):
    outcome: Literal["supported"]
    answer: str
    citations: Annotated[list[Citation], Field(min_length=1)]
    applied_context: QuestionContext = Field(alias="appliedContext")


class ClarificationNeeded(Schema):
    outcome: Literal["clarification_needed"]
    question: str
    missing_fields: list[Literal["campus", "program", "course", "academicTerm"]] = Field(
        alias="missingFields",
    )


class ReferralOutcome(Schema):
    outcome: Literal["referral"]
    limitation: str
    reason: Literal[
        "unsupported",
        "conflicting",
        "outdated",
        "account_specific",
        "uninterpretable",
        "timeout",
    ]
    referrals: list[Referral]


ChatOutcome = Annotated[
    SupportedAnswer | ClarificationNeeded | ReferralOutcome,
    Field(discriminator="outcome"),
]
