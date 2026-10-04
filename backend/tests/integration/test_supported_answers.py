from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import date, timedelta
from types import SimpleNamespace

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes import chat as chat_routes
from app.chat.retrieval import RetrievalResult
from app.core.config import AppSettings
from app.core.database import get_db_session
from app.db.models.source_approval import ApprovalStatus
from app.main import app


@pytest_asyncio.fixture
async def chat_client(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[httpx.AsyncClient]:
    original_settings = getattr(app.state, "settings", None)
    original_provider = getattr(app.state, "chat_provider", None)
    app.state.settings = AppSettings(
        database_url="sqlite+aiosqlite:///:memory:",
        session_secret_key="integration-test-session-secret",
        worker_shared_secret="integration-test-worker-secret",
    )
    app.state.test_retrieval_results = []

    class TestProvider:
        async def generate(self, _prompt: str) -> str:
            return "Fall registration closes on October 20."

    app.state.chat_provider = TestProvider()

    async def fake_retrieve(
        _session: AsyncSession,
        _question: str,
        *,
        context: object = None,
    ) -> list[RetrievalResult]:
        return app.state.test_retrieval_results

    async def override_db_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    monkeypatch.setattr(chat_routes, "retrieve_fragments", fake_retrieve)
    app.dependency_overrides[get_db_session] = override_db_session
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        if original_settings is None:
            del app.state.settings
        else:
            app.state.settings = original_settings
        if original_provider is None:
            del app.state.chat_provider
        else:
            app.state.chat_provider = original_provider
        del app.state.test_retrieval_results


def _retrieval_result(source: object) -> RetrievalResult:
    excerpt = "Fall registration closes on October 20."
    fragment = SimpleNamespace(
        locator="registration-deadline",
        excerpt=excerpt,
        extracted_text=excerpt,
    )
    return RetrievalResult(
        fragment=fragment,
        score=0.9,
        lexical_score=0.9,
        semantic_score=0.9,
        coverage=1.0,
        locator="registration-deadline",
        source=source,
    )


@pytest.mark.asyncio
async def test_supported_answer_cites_an_eligible_source(
    chat_client: httpx.AsyncClient,
    source_factory,
) -> None:
    source = await source_factory(
        title="Fall Registration Guide",
        approval_status=ApprovalStatus.APPROVED,
        effective_context={"academic_term": ["Fall 2026"]},
    )
    source.fragments[0].excerpt = "Fall registration closes on October 20."
    source.fragments[0].extracted_text = source.fragments[0].excerpt
    app.state.test_retrieval_results = [_retrieval_result(source.source)]

    response = await chat_client.post(
        "/api/v1/chat/answers",
        json={
            "question": "When does Fall 2026 registration close?",
            "context": {"academicTerm": "Fall 2026"},
        },
    )

    assert response.status_code == 200
    outcome = response.json()
    assert outcome["outcome"] == "supported"
    assert outcome["citations"]
    assert any(citation["sourceId"] == str(source.source.id) for citation in outcome["citations"])


@pytest.mark.asyncio
async def test_supported_answer_excludes_expired_term_specific_source(
    chat_client: httpx.AsyncClient,
    source_factory,
) -> None:
    expired_source = await source_factory(
        title="Expired Fall Registration Guide",
        approval_status=ApprovalStatus.APPROVED,
        effective_context={"academic_term": ["Fall 2026"]},
        effective_date_end=date.today() - timedelta(days=1),
    )
    expired_source.fragments[0].excerpt = "Fall registration closes on October 20."
    expired_source.fragments[0].extracted_text = expired_source.fragments[0].excerpt
    assert expired_source.approval.effective_date_end < date.today()

    response = await chat_client.post(
        "/api/v1/chat/answers",
        json={
            "question": "When does Fall 2026 registration close?",
            "context": {"academicTerm": "Fall 2026"},
        },
    )

    assert response.status_code == 200
    outcome = response.json()
    assert outcome["outcome"] != "supported" or all(
        citation["sourceId"] != str(expired_source.source.id) for citation in outcome["citations"]
    )
