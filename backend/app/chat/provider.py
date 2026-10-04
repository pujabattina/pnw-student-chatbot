from __future__ import annotations

import asyncio
from collections.abc import Mapping

import httpx

_RESPONSES_URL = "https://api.openai.com/v1/responses"


class GenerationProviderError(RuntimeError):
    """The generation provider could not return a usable response."""


class GenerationProviderTimeout(GenerationProviderError):
    """The provider exceeded its configured invocation deadline."""


class OpenAIResponsesProvider:
    """Invoke the Responses API without retaining application state."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout_seconds: float = 3.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("A provider API key is required.")
        if not model.strip():
            raise ValueError("A provider model is required.")
        if timeout_seconds <= 0:
            raise ValueError("Provider timeout must be greater than zero.")

        self._api_key = api_key
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._client = client or httpx.AsyncClient()
        self._owns_client = client is None

    async def generate(self, prompt: str) -> str:
        if not prompt.strip():
            raise ValueError("Generation input must not be empty.")

        try:
            async with asyncio.timeout(self._timeout_seconds):
                response = await self._client.post(
                    _RESPONSES_URL,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json={
                        "model": self._model,
                        "input": prompt,
                        "store": False,
                    },
                    timeout=self._timeout_seconds,
                )
        except TimeoutError as exc:
            raise GenerationProviderTimeout(
                "The generation provider exceeded its invocation deadline."
            ) from exc
        except httpx.HTTPError as exc:
            raise GenerationProviderError("The generation provider request failed.") from exc

        if response.is_error:
            raise GenerationProviderError(
                f"The generation provider returned HTTP {response.status_code}."
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise GenerationProviderError(
                "The generation provider returned an invalid response."
            ) from exc
        if not isinstance(payload, Mapping):
            raise GenerationProviderError("The generation provider returned an invalid response.")

        output_text = payload.get("output_text")
        if not isinstance(output_text, str) or not output_text.strip():
            raise GenerationProviderError(
                "The generation provider response contained no answer text."
            )
        return output_text.strip()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
