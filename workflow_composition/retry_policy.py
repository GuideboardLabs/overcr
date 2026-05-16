"""
OverCR v2.8.0 — Retry Policy

Bounded, auditable retry logic for composite workflows. Every retry
is recorded. Retries are capped at max_retries. After exhaustion,
escalation or deterministic fallback is triggered.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class RetryRecord:
    """A single retry attempt record."""
    node_id: str
    attempt_number: int
    max_retries: int
    reason: str = ""
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    exhausted: bool = False
    escalated: bool = False

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "attempt_number": self.attempt_number,
            "max_retries": self.max_retries,
            "reason": self.reason,
            "timestamp": self.timestamp,
            "exhausted": self.exhausted,
            "escalated": self.escalated,
        }


class RetryPolicy:
    """
    Governed retry policy for workflow nodes.

    Tracks retry counts per node. Enforces max_retries. Records
    every attempt. Triggers escalation or fallback on exhaustion.
    """

    def __init__(
        self,
        max_retries: int = 3,
        retry_delay_s: float = 0.0,
        retry_on: Optional[list[str]] = None,
        escalate_after_failure: bool = False,
        fallback_threshold: int = 3,
    ):
        self.max_retries = max(0, min(10, max_retries))
        self.retry_delay_s = max(0, retry_delay_s)
        self.retry_on = retry_on or ["validation_failed", "timeout", "execution_error"]
        self.escalate_after_failure = escalate_after_failure
        self.fallback_threshold = min(self.max_retries, fallback_threshold)
        self._attempts: dict[str, int] = {}
        self._records: list[RetryRecord] = []

    def record_attempt(self, node_id: str, reason: str = "") -> RetryRecord:
        """Record a retry attempt for a node."""
        attempt = self._attempts.get(node_id, 0) + 1
        self._attempts[node_id] = attempt
        exhausted = attempt >= self.max_retries
        escalated = self.escalate_after_failure and exhausted
        record = RetryRecord(
            node_id=node_id, attempt_number=attempt,
            max_retries=self.max_retries, reason=reason,
            exhausted=exhausted, escalated=escalated,
        )
        self._records.append(record)
        return record

    def should_retry(self, node_id: str, reason: str = "") -> bool:
        """Check if a retry is allowed."""
        if reason and self.retry_on:
            reason_lower = reason.lower()
            if not any(r in reason_lower for r in self.retry_on):
                return False
        return self._attempts.get(node_id, 0) < self.max_retries

    def should_fallback(self, node_id: str) -> bool:
        return self._attempts.get(node_id, 0) >= self.fallback_threshold

    def attempts(self, node_id: str) -> int:
        return self._attempts.get(node_id, 0)

    def is_exhausted(self, node_id: str) -> bool:
        return self._attempts.get(node_id, 0) >= self.max_retries

    def reset_node(self, node_id: str):
        self._attempts.pop(node_id, None)

    def get_records(self) -> list[RetryRecord]:
        return list(self._records)

    def export_records(self) -> list[dict]:
        return [r.to_dict() for r in self._records]

    def reset(self):
        self._attempts.clear()
        self._records.clear()

    def to_dict(self) -> dict:
        return {
            "max_retries": self.max_retries,
            "retry_delay_s": self.retry_delay_s,
            "retry_on": self.retry_on,
            "escalate_after_failure": self.escalate_after_failure,
            "fallback_threshold": self.fallback_threshold,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RetryPolicy":
        return cls(
            max_retries=data.get("max_retries", 3),
            retry_delay_s=data.get("retry_delay_s", 0.0),
            retry_on=data.get("retry_on"),
            escalate_after_failure=data.get("escalate_after_failure", False),
            fallback_threshold=data.get("fallback_threshold", 3),
        )

    @classmethod
    def strict(cls) -> "RetryPolicy":
        return cls(max_retries=0)
