"""
OverCR v2.8.0 — Escalation Policy

Controlled escalation of workflow nodes that exceed retry limits,
trigger governance violations, or encounter contradictions.

Escalation targets: approval_queue, operator_review,
contradiction_review, governance_review, sandbox_review.

Every escalation generates an audit artifact, pauses the workflow
state (if configured), and preserves replayability.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

VALID_ESCALATION_TARGETS = {
    "approval_queue", "operator_review", "contradiction_review",
    "governance_review", "sandbox_review",
}


@dataclass
class EscalationRecord:
    """A single escalation event."""
    escalation_id: str
    node_id: str
    target: str
    reason: str = ""
    severity: str = "medium"  # low | medium | high | critical
    pause_workflow: bool = True
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    resolved: bool = False
    resolution_note: str = ""

    def to_dict(self) -> dict:
        return {
            "escalation_id": self.escalation_id,
            "node_id": self.node_id,
            "target": self.target,
            "reason": self.reason,
            "severity": self.severity,
            "pause_workflow": self.pause_workflow,
            "timestamp": self.timestamp,
            "resolved": self.resolved,
            "resolution_note": self.resolution_note,
        }


class EscalationPolicy:
    """
    Governed escalation for workflow nodes.

    Escalates to operator review queues when retries are exhausted,
    contradictions are detected, or governance violations occur.
    """

    def __init__(
        self,
        escalation_points: Optional[list[str]] = None,
        targets: Optional[list[dict]] = None,
    ):
        self.escalation_points = escalation_points or []
        self.targets = targets or [
            {"target": "operator_review", "condition": "retry_exhausted",
             "pause_workflow": True},
        ]
        self._records: list[EscalationRecord] = []
        self._counter = 0

    def should_escalate(self, node_id: str, condition: str = "",
                        retries_exhausted: bool = False) -> bool:
        """Check if a node should be escalated."""
        if node_id in self.escalation_points:
            return True
        if retries_exhausted:
            return True
        return False

    def escalate(self, node_id: str, reason: str = "",
                 severity: str = "medium",
                 retries_exhausted: bool = False,
                 target: str = "") -> EscalationRecord:
        """Record an escalation event."""
        self._counter += 1
        eid = f"esc-{self._counter:04d}"

        if not target:
            target = self.targets[0]["target"] if self.targets else "operator_review"
        if target not in VALID_ESCALATION_TARGETS:
            target = "operator_review"

        pause = True
        for t in self.targets:
            if t.get("target") == target:
                pause = t.get("pause_workflow", True)
                break

        record = EscalationRecord(
            escalation_id=eid,
            node_id=node_id,
            target=target,
            reason=reason or f"Escalation triggered for {node_id}",
            severity=severity,
            pause_workflow=pause,
        )
        self._records.append(record)
        return record

    def resolve(self, escalation_id: str, note: str = "") -> bool:
        """Mark an escalation as resolved."""
        for r in self._records:
            if r.escalation_id == escalation_id:
                r.resolved = True
                r.resolution_note = note
                return True
        return False

    def get_records(self) -> list[EscalationRecord]:
        return list(self._records)

    def export_records(self) -> list[dict]:
        return [r.to_dict() for r in self._records]

    def to_dict(self) -> dict:
        return {
            "escalation_points": self.escalation_points,
            "targets": self.targets,
        }
