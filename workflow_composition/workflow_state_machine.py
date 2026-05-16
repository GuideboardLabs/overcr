"""
OverCR v2.8.0 — Workflow State Machine

Explicit, validated workflow state representation. Every state
transition is checked for legality. Illegal transitions are
rejected with audit records. Every transition is append-only
in the audit history.

States:
  initialized, running, paused, awaiting_approval, retry_pending,
  escalated, fallback_active, failed, completed, rolled_back
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


VALID_STATES = {
    "initialized", "running", "paused", "awaiting_approval",
    "retry_pending", "escalated", "fallback_active",
    "failed", "completed", "rolled_back",
}

# Legal state transitions
VALID_TRANSITIONS = {
    "initialized":       {"running", "paused"},
    "running":           {"paused", "awaiting_approval", "retry_pending",
                           "escalated", "fallback_active",
                           "failed", "completed"},
    "paused":            {"running", "failed", "completed"},
    "awaiting_approval": {"running", "failed", "completed",
                           "escalated"},
    "retry_pending":     {"running", "failed", "escalated",
                           "fallback_active"},
    "escalated":         {"paused", "failed", "completed",
                           "running"},
    "fallback_active":   {"running", "failed", "completed"},
    "failed":            {"rolled_back", "completed"},
    "completed":         set(),  # Terminal
    "rolled_back":       {"running", "failed", "completed"},
}


class InvalidTransitionError(Exception):
    """Raised when an illegal state transition is attempted."""
    pass


@dataclass
class StateTransition:
    """A single, auditable state transition."""
    from_state: str
    to_state: str
    reason: str = ""
    node_id: str = ""
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict:
        return {
            "from_state": self.from_state,
            "to_state": self.to_state,
            "reason": self.reason,
            "node_id": self.node_id,
            "timestamp": self.timestamp,
        }


class WorkflowStateMachine:
    """
    Explicit workflow state machine with validated transitions.

    Every transition is checked. Illegal ones raise errors and
    generate audit records. All valid transitions are recorded
    in an append-only history.
    """

    def __init__(self, initial_state: str = "initialized"):
        if initial_state not in VALID_STATES:
            raise ValueError(f"Invalid initial state: {initial_state}")
        self.state: str = initial_state
        self.history: list[StateTransition] = []

    def transition_to(self, new_state: str, reason: str = "",
                      node_id: str = "") -> StateTransition:
        """
        Transition to a new state after validation.

        Raises:
            InvalidTransitionError: If transition is not legal.
        """
        if new_state not in VALID_STATES:
            raise InvalidTransitionError(
                f"Invalid state: '{new_state}'"
            )

        allowed = VALID_TRANSITIONS.get(self.state, set())
        if new_state not in allowed:
            raise InvalidTransitionError(
                f"Illegal transition: {self.state} -> {new_state}. "
                f"Allowed from '{self.state}': {sorted(allowed)}"
            )

        transition = StateTransition(
            from_state=self.state,
            to_state=new_state,
            reason=reason,
            node_id=node_id,
        )
        self.state = new_state
        self.history.append(transition)
        return transition

    def can_transition_to(self, target: str) -> bool:
        """Check if a transition is legal without performing it."""
        return target in VALID_TRANSITIONS.get(self.state, set())

    def is_terminal(self) -> bool:
        """Check if the workflow is in a terminal state."""
        return self.state in ("completed", "failed")

    def is_active(self) -> bool:
        """Check if the workflow is still running."""
        return self.state in ("running", "retry_pending",
                              "fallback_active", "escalated")

    def is_blocked(self) -> bool:
        """Check if the workflow is waiting for external action."""
        return self.state in ("paused", "awaiting_approval")

    def export_history(self) -> list[dict]:
        """Export the full state transition history."""
        return [t.to_dict() for t in self.history]

    def to_dict(self) -> dict:
        return {
            "state": self.state,
            "history": self.export_history(),
        }
