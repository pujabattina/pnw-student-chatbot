from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from app.api.schemas.chat import (
    ChatOutcome,
    QuestionContext,
    ReferralOutcome,
    SupportedAnswer,
)
from app.chat.citations import assemble_citations
from app.chat.retrieval import RetrievalResult

_MINIMUM_SCORE = 0.25
_MINIMUM_COVERAGE = 0.2
_UNSUPPORTED_RESPONSE = "INSUFFICIENT_EVIDENCE"


class GenerationProvider(Protocol):
    async def generate(self, prompt: str) -> str: ...


def _evidence_text(result: RetrievalResult) -> str:
    return " ".join(
        text for text in (result.fragment.excerpt, result.fragment.extracted_text) if text
    ).strip()


def _grounded_prompt(question: str, results: Sequence[RetrievalResult]) -> str:
    evidence = "\n\n".join(
        (
            f"Source: {result.source.title}\n"
            f"Locator: {result.locator}\n"
            f"Approved source excerpt:\n{_evidence_text(result)}"
        )
        for result in results
    )
    return (
        "Answer the student's question using only the approved source excerpts below. "
        "Do not add facts, policies, dates, or conclusions not stated in those excerpts. "
        f"If they do not directly answer the question, output exactly "
        f"{_UNSUPPORTED_RESPONSE} and nothing else.\n\n"
        f"Student question:\n{question}\n\n"
        f"Approved source excerpts:\n{evidence}"
    )


def _unsupported() -> ReferralOutcome:
    return ReferralOutcome(
        outcome="referral",
        limitation="I could not find enough approved information to provide a reliable answer.",
        reason="unsupported",
        referrals=[],
    )


async def decide_answer(
    question: str,
    results: Sequence[RetrievalResult],
    provider: GenerationProvider,
    *,
    context: QuestionContext | None = None,
) -> ChatOutcome:
    """Generate a response only when eligible retrieved excerpts cover the question."""
    evidence = [
        result
        for result in results
        if result.score >= _MINIMUM_SCORE
        and result.coverage >= _MINIMUM_COVERAGE
        and _evidence_text(result)
    ]
    citations = assemble_citations(evidence)
    if not evidence or not citations:
        return _unsupported()

    answer = await provider.generate(_grounded_prompt(question, evidence))
    if not answer.strip() or answer.strip() == _UNSUPPORTED_RESPONSE:
        return _unsupported()

    return SupportedAnswer.model_validate(
        {
            "outcome": "supported",
            "answer": answer.strip(),
            "citations": citations,
            "appliedContext": context or QuestionContext(),
        }
    )
