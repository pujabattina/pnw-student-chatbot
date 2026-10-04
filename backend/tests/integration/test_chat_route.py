from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.error_handlers import register_error_handlers
from app.api.routes import chat
from app.chat.retrieval import RetrievalResult
from app.core.config import AppSettings
from app.core.database import get_db_session
from app.telemetry.aggregates import TelemetryAggregates
from app.telemetry.middleware import PrivacyTelemetryMiddleware


class _Provider:
    def __init__(self, answer: str = "Registration closes October 20.") -> None:
        self.answer = answer
        self.prompt: str | None = None

    async def generate(self, prompt: str) -> str:
        self.prompt = prompt
        return self.answer


def _result() -> RetrievalResult:
    source = SimpleNamespace(
        id=uuid4(),
        title="Registration Guide",
        canonical_url="https://www.pnw.edu/registration",
    )
    excerpt = "Fall registration closes on October 20."
    fragment = SimpleNamespace(excerpt=excerpt, extracted_text=excerpt)
    return RetrievalResult(
        fragment=fragment,
        score=0.9,
        lexical_score=0.9,
        semantic_score=0.9,
        coverage=0.8,
        locator="section-4",
        source=source,
    )


@pytest_asyncio.fixture
async def chat_client(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[tuple[httpx.AsyncClient, _Provider, TelemetryAggregates]]:
    app = FastAPI()
    aggregates = TelemetryAggregates()
    app.add_middleware(PrivacyTelemetryMiddleware, aggregates=aggregates)
    register_error_handlers(app)
    app.include_router(chat.router, prefix="/api/v1")
    app.state.settings = AppSettings(
        database_url="sqlite+aiosqlite:///:memory:",
        session_secret_key="test-session-secret",
        worker_shared_secret="test-worker-secret",
    )
    provider = _Provider()
    app.state.chat_provider = provider

    async def override_db_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    async def fake_retrieve(
        _session: AsyncSession,
        question: str,
        *,
        context: object = None,
    ) -> list[RetrievalResult]:
        if "registration" in question.lower():
            return [_result()]
        return []

    app.dependency_overrides[get_db_session] = override_db_session
    monkeypatch.setattr(chat, "retrieve_fragments", fake_retrieve)

    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            yield client, provider, aggregates
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_chat_route_redacts_pii_and_returns_cited_answer_with_correlation_id(
    chat_client: tuple[httpx.AsyncClient, _Provider, TelemetryAggregates],
) -> None:
    client, provider, aggregates = chat_client
    response = await client.post(
        "/api/v1/chat/answers",
        json={"question": "When does registration close? student ID: ABC12345 me@example.edu"},
    )

    assert response.status_code == 200
    outcome = response.json()
    assert outcome["outcome"] == "supported"
    assert outcome["citations"][0]["title"] == "Registration Guide"
    assert outcome["citations"][0]["locator"] == "section-4"
    assert response.headers["X-Correlation-ID"]
    assert provider.prompt is not None
    assert "me@example.edu" not in provider.prompt
    assert "ABC12345" not in provider.prompt
    snapshot = aggregates.snapshot()
    assert snapshot.pii_redaction_count == 2
    assert snapshot.outcome_counts == {"supported": 1}


@pytest.mark.asyncio
async def test_chat_route_rejects_questions_over_4000_characters(
    chat_client: tuple[httpx.AsyncClient, _Provider, TelemetryAggregates],
) -> None:
    client, _provider, _aggregates = chat_client

    response = await client.post("/api/v1/chat/answers", json={"question": "q" * 4001})

    assert response.status_code == 400
    assert response.json()["code"] == "validation_error"
    assert "q" * 100 not in response.text


@pytest.mark.asyncio
async def test_chat_route_rate_limits_without_retaining_the_client_address(
    chat_client: tuple[httpx.AsyncClient, _Provider, TelemetryAggregates],
) -> None:
    client, _provider, _aggregates = chat_client
    app = client._transport.app
    app.state.chat_rate_limiter = chat.SlidingWindowRateLimiter(
        "test-rate-limit-secret",
        limit=1,
    )

    first = await client.post("/api/v1/chat/answers", json={"question": "Other topic"})
    second = await client.post("/api/v1/chat/answers", json={"question": "Other topic"})

    assert first.status_code == 200
    assert first.json()["reason"] == "unsupported"
    assert second.status_code == 429
    assert second.headers["Retry-After"] == "60"
    assert "testclient" not in repr(app.state.chat_rate_limiter._requests)


@pytest.mark.asyncio
async def test_chat_route_returns_safe_503_if_generation_fails(
    chat_client: tuple[httpx.AsyncClient, _Provider, TelemetryAggregates],
) -> None:
    client, _provider, _aggregates = chat_client

    class FailingProvider:
        async def generate(self, _prompt: str) -> str:
            raise chat.GenerationProviderError("private provider response")

    app = client._transport.app
    app.state.chat_provider = FailingProvider()
    response = await client.post(
        "/api/v1/chat/answers",
        json={"question": "When does registration close?"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Service is temporarily unavailable."
    assert "private provider response" not in response.text


@pytest.mark.asyncio
async def test_chat_route_bounds_retrieval_time(
    chat_client: tuple[httpx.AsyncClient, _Provider, TelemetryAggregates],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _provider, _aggregates = chat_client

    async def slow_retrieve(
        _session: AsyncSession,
        _question: str,
        *,
        context: object = None,
    ) -> Sequence[RetrievalResult]:
        import asyncio

        await asyncio.sleep(1)
        return []

    monkeypatch.setattr(chat, "retrieve_fragments", slow_retrieve)
    response = await client.post(
        "/api/v1/chat/answers",
        json={"question": "When does registration close?"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Service is temporarily unavailable."
