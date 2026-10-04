from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.api.schemas.chat import QuestionContext, ReferralOutcome, SupportedAnswer
from app.chat.decision import decide_answer
from app.chat.retrieval import RetrievalResult


class _Provider:
    def __init__(self, answer: str = "Registration closes on October 20.") -> None:
        self.answer = answer
        self.prompt: str | None = None

    async def generate(self, prompt: str) -> str:
        self.prompt = prompt
        return self.answer


def _result(
    *,
    score: float = 0.8,
    coverage: float = 0.75,
    excerpt: str = "Fall registration closes on October 20.",
) -> RetrievalResult:
    source = SimpleNamespace(
        id=uuid4(),
        title="Registration Guide",
        canonical_url="https://www.pnw.edu/registration",
    )
    fragment = SimpleNamespace(
        excerpt=excerpt,
        extracted_text=excerpt,
    )
    return RetrievalResult(
        fragment=fragment,
        score=score,
        lexical_score=score,
        semantic_score=score,
        coverage=coverage,
        locator="section-4",
        source=source,
    )


@pytest.mark.asyncio
async def test_decision_refers_without_invoking_provider_when_evidence_is_missing() -> None:
    provider = _Provider()

    outcome = await decide_answer("When does registration close?", [], provider)

    assert isinstance(outcome, ReferralOutcome)
    assert outcome.reason == "unsupported"
    assert provider.prompt is None


@pytest.mark.asyncio
async def test_decision_refers_when_retrieved_coverage_is_below_threshold() -> None:
    provider = _Provider()

    outcome = await decide_answer(
        "When does registration close?",
        [_result(coverage=0.1)],
        provider,
    )

    assert isinstance(outcome, ReferralOutcome)
    assert outcome.reason == "unsupported"
    assert provider.prompt is None


@pytest.mark.asyncio
async def test_decision_generates_only_from_retrieved_excerpts_and_cites_them() -> None:
    provider = _Provider("  Registration closes October 20.  ")
    context = QuestionContext(academicTerm="Fall 2026")
    result = _result()

    outcome = await decide_answer(
        "When does registration close?",
        [result],
        provider,
        context=context,
    )

    assert isinstance(outcome, SupportedAnswer)
    assert outcome.answer == "Registration closes October 20."
    assert outcome.applied_context == context
    assert len(outcome.citations) == 1
    assert outcome.citations[0].title == "Registration Guide"
    assert outcome.citations[0].locator == "section-4"
    assert provider.prompt is not None
    assert "Fall registration closes on October 20." in provider.prompt
    assert "Do not add facts, policies, dates, or conclusions" in provider.prompt


@pytest.mark.asyncio
async def test_decision_refers_when_retrieved_evidence_has_no_text() -> None:
    provider = _Provider()

    outcome = await decide_answer(
        "When does registration close?",
        [_result(excerpt="")],
        provider,
    )

    assert isinstance(outcome, ReferralOutcome)
    assert outcome.reason == "unsupported"
    assert provider.prompt is None


@pytest.mark.asyncio
async def test_decision_refers_when_provider_reports_insufficient_evidence() -> None:
    provider = _Provider("INSUFFICIENT_EVIDENCE")

    outcome = await decide_answer(
        "When does registration close?",
        [_result()],
        provider,
    )

    assert isinstance(outcome, ReferralOutcome)
    assert outcome.reason == "unsupported"
