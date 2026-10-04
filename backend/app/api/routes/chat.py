from __future__ import annotations

import asyncio
import hashlib
import hmac
import time
from collections import deque
from collections.abc import AsyncIterator
from typing import Annotated, Protocol

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.chat import ChatOutcome, ChatRequest
from app.chat.decision import GenerationProvider, decide_answer
from app.chat.provider import (
    GenerationProviderError,
    OpenAIResponsesProvider,
)
from app.chat.retrieval import retrieve_fragments
from app.core.config import AppSettings
from app.core.database import get_db_session
from app.telemetry.redaction import redact_for_telemetry

router = APIRouter()
_RATE_LIMIT = 30
_RATE_WINDOW_SECONDS = 60.0
_MAX_RATE_LIMIT_KEYS = 10_000
_RETRIEVAL_TIMEOUT_SECONDS = 0.5
_GENERATION_TIMEOUT_SECONDS = 3.0
_OPENAI_MODEL = "gpt-4.1-mini"


class RateLimiter(Protocol):
    async def allow(self, identity: str) -> bool: ...


class SlidingWindowRateLimiter:
    """Process-local limiter that retains only keyed hashes of client addresses."""

    def __init__(
        self,
        secret: str,
        *,
        limit: int = _RATE_LIMIT,
        window_seconds: float = _RATE_WINDOW_SECONDS,
    ) -> None:
        if not secret:
            raise ValueError("A secret is required for rate-limit key hashing.")
        if limit < 1 or window_seconds <= 0:
            raise ValueError("Rate-limit values must be positive.")
        self._secret = secret.encode()
        self._limit = limit
        self._window_seconds = window_seconds
        self._requests: dict[bytes, deque[float]] = {}
        self._lock = asyncio.Lock()

    async def allow(self, identity: str) -> bool:
        key = hmac.digest(self._secret, identity.encode(), hashlib.sha256)
        now = time.monotonic()
        cutoff = now - self._window_seconds
        async with self._lock:
            timestamps = self._requests.get(key)
            if timestamps is not None:
                while timestamps and timestamps[0] <= cutoff:
                    timestamps.popleft()
                if not timestamps:
                    del self._requests[key]
                    timestamps = None

            if timestamps is None:
                if len(self._requests) >= _MAX_RATE_LIMIT_KEYS:
                    for known_key, window_timestamps in tuple(self._requests.items()):
                        while window_timestamps and window_timestamps[0] <= cutoff:
                            window_timestamps.popleft()
                        if not window_timestamps:
                            del self._requests[known_key]
                    if len(self._requests) >= _MAX_RATE_LIMIT_KEYS:
                        return False
                timestamps = deque()
                self._requests[key] = timestamps
            if len(timestamps) >= self._limit:
                return False
            timestamps.append(now)
            return True


class _UnavailableProvider:
    async def generate(self, _prompt: str) -> str:
        raise GenerationProviderError("No approved generation provider is configured.")


async def get_generation_provider(request: Request) -> AsyncIterator[GenerationProvider]:
    """Yield the configured provider, allowing tests to inject an app-scoped provider."""
    injected = getattr(request.app.state, "chat_provider", None)
    if injected is not None:
        yield injected
        return

    settings: AppSettings = request.app.state.settings
    if settings.model_provider != "openai" or not settings.model_provider_api_key:
        yield _UnavailableProvider()
        return

    provider = OpenAIResponsesProvider(
        api_key=settings.model_provider_api_key,
        model=_OPENAI_MODEL,
        timeout_seconds=_GENERATION_TIMEOUT_SECONDS,
    )
    try:
        yield provider
    finally:
        await provider.aclose()


def _get_rate_limiter(request: Request) -> SlidingWindowRateLimiter:
    limiter = getattr(request.app.state, "chat_rate_limiter", None)
    if limiter is None:
        settings: AppSettings = request.app.state.settings
        limiter = SlidingWindowRateLimiter(settings.session_secret_key)
        request.app.state.chat_rate_limiter = limiter
    return limiter


@router.post("/chat/answers", response_model=ChatOutcome)
async def create_chat_answer(
    payload: ChatRequest,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    provider: Annotated[GenerationProvider, Depends(get_generation_provider)],
) -> ChatOutcome | Response:
    question = redact_for_telemetry(request, payload.question)
    client = request.client
    identity = client.host if client is not None else "unknown"
    limiter = _get_rate_limiter(request)
    if not await limiter.allow(identity):
        request.state.telemetry_outcome = "error"
        return JSONResponse(
            status_code=429,
            content={"detail": "Request rate limit exceeded.", "code": "rate_limited"},
            headers={"Retry-After": str(int(_RATE_WINDOW_SECONDS))},
        )

    try:
        async with asyncio.timeout(_RETRIEVAL_TIMEOUT_SECONDS):
            results = await retrieve_fragments(session, question, context=payload.context)
        async with asyncio.timeout(_GENERATION_TIMEOUT_SECONDS):
            outcome = await decide_answer(
                question,
                results,
                provider,
                context=payload.context,
            )
    except (TimeoutError, GenerationProviderError) as exc:
        request.state.telemetry_outcome = "error"
        raise HTTPException(status_code=503, detail="Service is temporarily unavailable.") from exc

    request.state.telemetry_outcome = outcome.outcome
    response.headers["X-Correlation-ID"] = request.state.correlation_id
    return outcome
