from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml


@pytest.fixture(scope="module")
def openapi_contract() -> dict[str, Any]:
    contract_path = (
        Path(__file__).resolve().parents[3]
        / "specs"
        / "002-pnw-student-chatbot"
        / "contracts"
        / "openapi.yaml"
    )
    with contract_path.open(encoding="utf-8") as contract_file:
        contract = yaml.safe_load(contract_file)
    assert isinstance(contract, dict)
    return contract


def test_chat_answers_is_anonymous_and_uses_the_chat_contract(
    openapi_contract: dict[str, Any],
) -> None:
    operation = openapi_contract["paths"]["/chat/answers"]["post"]

    assert {"url": "/api/v1"} in openapi_contract["servers"]
    assert operation["security"] == []
    assert operation["requestBody"]["required"] is True
    assert (
        operation["requestBody"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/ChatRequest"
    )
    assert (
        operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/ChatOutcome"
    )


def test_chat_answers_documents_bad_request_throttled_and_unavailable_responses(
    openapi_contract: dict[str, Any],
) -> None:
    responses = openapi_contract["paths"]["/chat/answers"]["post"]["responses"]
    expected_components = {
        "400": "BadRequest",
        "429": "Throttled",
        "503": "Unavailable",
    }

    for status_code, component in expected_components.items():
        assert responses[status_code]["$ref"] == f"#/components/responses/{component}"

    contract_responses = openapi_contract["components"]["responses"]
    assert "no request body is retained" in contract_responses["BadRequest"]["description"]
    assert "rate limit" in contract_responses["Throttled"]["description"]
    assert "cannot safely complete" in contract_responses["Unavailable"]["description"]
