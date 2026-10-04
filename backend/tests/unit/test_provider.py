from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
import pytest

from app.chat.provider import (
    GenerationProviderError,
    GenerationProviderTimeout,
    OpenAIResponsesProvider,
)


@pytest.mark.asyncio
async def test_provider_disables_response_storage_and_returns_output_text() -> None:
    request_data: dict[str, Any] = {}

    async def handle_request(request: httpx.Request) -> httpx.Response:
        request_data["authorization"] = request.headers["Authorization"]
        request_data["payload"] = json.loads(request.content)
        return httpx.Response(200, json={"output_text": "  Grounded response.  "})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle_request)) as client:
        provider = OpenAIResponsesProvider(
            api_key="test-api-key",
            model="approved-model",
            client=client,
        )

        answer = await provider.generate("Question and approved source context")

    assert answer == "Grounded response."
    assert request_data == {
        "authorization": "Bearer test-api-key",
        "payload": {
            "model": "approved-model",
            "input": "Question and approved source context",
            "store": False,
        },
    }


@pytest.mark.asyncio
async def test_provider_raises_a_safe_error_for_http_failures() -> None:
    async def handle_request(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="provider error containing private request details")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle_request)) as client:
        provider = OpenAIResponsesProvider(
            api_key="test-api-key",
            model="approved-model",
            client=client,
        )

        with pytest.raises(GenerationProviderError, match="HTTP 503") as error:
            await provider.generate("Question")

    assert "private request details" not in str(error.value)


@pytest.mark.asyncio
async def test_provider_enforces_total_invocation_timeout() -> None:
    async def handle_request(_request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(1)
        return httpx.Response(200, json={"output_text": "too late"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle_request)) as client:
        provider = OpenAIResponsesProvider(
            api_key="test-api-key",
            model="approved-model",
            timeout_seconds=0.01,
            client=client,
        )

        with pytest.raises(GenerationProviderTimeout):
            await provider.generate("Question")
