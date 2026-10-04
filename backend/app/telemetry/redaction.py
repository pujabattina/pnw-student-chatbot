from __future__ import annotations

import re
from dataclasses import dataclass

from fastapi import Request

_PII_PATTERNS = (
    re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
    re.compile(
        r"\b(?:student\s*(?:id|number|#)|pnw\s*id)\s*[:#]?\s*[A-Z0-9-]{5,}\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    re.compile(r"(?<!\w)(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}(?!\w)"),
    re.compile(r"\b\d{8,10}\b"),
)
_REDACTION = "[REDACTED]"


@dataclass(frozen=True, slots=True)
class RedactedText:
    text: str
    redaction_count: int


def redact_text(value: str) -> RedactedText:
    redaction_count = 0
    redacted = value
    for pattern in _PII_PATTERNS:
        redacted, count = pattern.subn(_REDACTION, redacted)
        redaction_count += count
    return RedactedText(text=redacted, redaction_count=redaction_count)


def redact_for_telemetry(request: Request, value: str) -> str:
    result = redact_text(value)
    previous_count = getattr(request.state, "pii_redaction_count", 0)
    request.state.pii_redaction_count = previous_count + result.redaction_count
    return result.text
