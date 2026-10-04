from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from threading import Lock

_OUTCOMES = frozenset({"supported", "clarification_needed", "referral", "unknown", "error"})
_LATENCY_BUCKETS: tuple[tuple[int, str], ...] = (
    (50, "le_50ms"),
    (100, "le_100ms"),
    (250, "le_250ms"),
    (500, "le_500ms"),
    (1000, "le_1000ms"),
    (3000, "le_3000ms"),
    (5000, "le_5000ms"),
)
_OVER_5000MS = "gt_5000ms"


@dataclass(frozen=True, slots=True)
class TelemetrySnapshot:
    outcome_counts: dict[str, int]
    latency_counts: dict[str, int]
    pii_redaction_count: int


class TelemetryAggregates:
    """Thread-safe, bounded, content-free request aggregates."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._outcome_counts: Counter[str] = Counter()
        self._latency_counts: Counter[str] = Counter()
        self._pii_redaction_count = 0

    def record_request(
        self,
        *,
        outcome: str,
        latency_ms: float,
        pii_redaction_count: int = 0,
    ) -> None:
        safe_outcome = outcome if outcome in _OUTCOMES else "unknown"
        safe_latency = max(0.0, latency_ms)
        latency_bucket = next(
            (bucket for bound, bucket in _LATENCY_BUCKETS if safe_latency <= bound),
            _OVER_5000MS,
        )
        safe_redaction_count = max(0, pii_redaction_count)

        with self._lock:
            self._outcome_counts[safe_outcome] += 1
            self._latency_counts[latency_bucket] += 1
            self._pii_redaction_count += safe_redaction_count

    def snapshot(self) -> TelemetrySnapshot:
        with self._lock:
            return TelemetrySnapshot(
                outcome_counts=dict(self._outcome_counts),
                latency_counts=dict(self._latency_counts),
                pii_redaction_count=self._pii_redaction_count,
            )
