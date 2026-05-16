"""
OverCR v2.3.0 — Workflow Context

A self-contained execution context that every workflow instance
carries. This is NOT a global singleton — each execution gets its
own isolated context. All context mutations must go through
approved transitions only.

Design constraints:
  - No mutable global state
  - Context is JSON-serializable for audit traces
  - Context carries operator identity for every approval
  - Context enforces workflow-level timeouts
  - Context prevents workflow self-spawning
"""

import uuid
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


WORKFLOW_CONTEXT_STATES = {"initialized", "running", "paused", "completed", "failed", "stopped"}


@dataclass
class WorkflowContext:
    """
    Isolated execution context for a single workflow run.

    Every field here is recorded in the audit trace. Nothing is
    ephemeral. This context is intentionally bounded — it cannot
    spawn sub-workflows, call external services, or mutate the
    filesystem without approval.
    """

    workflow_id: str
    workflow_name: str
    workflow_version: str

    # Execution identity
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    operator: str = "operator"
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # State
    state: str = "initialized"
    node_states: dict = field(default_factory=dict)
    approvals: dict = field(default_factory=dict)  # node_id|edge_id -> approval record
    audit_entries: list = field(default_factory=list)

    # Timing
    elapsed_seconds: float = 0.0
    timeout_seconds: float = 300.0  # 5 min default; workflows must be bounded
    node_timings: dict = field(default_factory=dict)

    # Governance flags
    deterministic_fallback_activated: bool = False
    rollback_occurred: bool = False
    approval_pauses: int = 0
    replay_mode: bool = False

    # Input / Output
    initial_input: Optional[dict] = None
    final_output: Optional[dict] = None
    error_message: Optional[str] = None

    # --- State transitions ---

    def transition_to(self, new_state: str, reason: str = ""):
        """Transition the workflow state with audit."""
        if new_state not in WORKFLOW_CONTEXT_STATES:
            raise ValueError(f"Invalid workflow state: {new_state}")
        old_state = self.state
        self.state = new_state
        self._record_audit(
            "state_transition",
            {"from": old_state, "to": new_state, "reason": reason},
        )

    def record_node_state(self, node_id: str, new_state: str, output_packet: Optional[dict] = None):
        """Record a node's execution state."""
        self.node_states[node_id] = {
            "state": new_state,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        entry = {"node_id": node_id, "state": new_state}
        if output_packet:
            entry["output_summary"] = output_packet.get("summary", "")
        self._record_audit("node_state", entry)

    def record_approval(self, target_id: str, decision: str, reason: str, operator: str = ""):
        """Record an approval decision."""
        approval = {
            "target_id": target_id,
            "decision": decision,
            "reason": reason,
            "operator": operator or self.operator,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.approvals[target_id] = approval
        self.approval_pauses += 1
        self._record_audit("approval", approval)

    def record_rollback(self, node_id: str, reason: str):
        """Record a rollback event."""
        self.rollback_occurred = True
        self._record_audit("rollback", {"node_id": node_id, "reason": reason})

    def record_fallback(self, node_id: str, reason: str):
        """Record a deterministic fallback activation."""
        self.deterministic_fallback_activated = True
        self._record_audit("deterministic_fallback", {"node_id": node_id, "reason": reason})

    def record_validation(self, node_id: str, valid: bool, errors: list, warnings: list):
        """Record a validation result."""
        self._record_audit("validation", {
            "node_id": node_id,
            "valid": valid,
            "errors": errors,
            "warnings": warnings,
        })

    def record_completion(self):
        """Record workflow completion."""
        self.state = "completed"
        self.elapsed_seconds = time.time() - self._start_wall
        self._record_audit("workflow_completed", {"elapsed_s": self.elapsed_seconds})

    def record_failure(self, error: str):
        """Record workflow failure."""
        self.state = "failed"
        self.error_message = error
        self.elapsed_seconds = time.time() - self._start_wall
        self._record_audit("workflow_failed", {"error": error, "elapsed_s": self.elapsed_seconds})

    # --- Audit ---

    def _record_audit(self, entry_type: str, details: dict):
        """Append an audit entry. Immutable — never removes entries."""
        entry = {
            "run_id": self.run_id,
            "workflow_id": self.workflow_id,
            "workflow_version": self.workflow_version,
            "entry_type": entry_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "details": details,
        }
        self.audit_entries.append(entry)

    def __post_init__(self):
        self._start_wall = time.time()
        self._record_audit("context_initialized", {
            "workflow_name": self.workflow_name,
            "workflow_version": self.workflow_version,
        })

    # --- Serialization ---

    def to_dict(self) -> dict:
        return {
            "workflow_id": self.workflow_id,
            "workflow_name": self.workflow_name,
            "workflow_version": self.workflow_version,
            "run_id": self.run_id,
            "operator": self.operator,
            "started_at": self.started_at,
            "state": self.state,
            "node_states": self.node_states,
            "approvals": self.approvals,
            "audit_entries": self.audit_entries,
            "elapsed_seconds": self.elapsed_seconds,
            "timeout_seconds": self.timeout_seconds,
            "node_timings": self.node_timings,
            "deterministic_fallback_activated": self.deterministic_fallback_activated,
            "rollback_occurred": self.rollback_occurred,
            "approval_pauses": self.approval_pauses,
            "replay_mode": self.replay_mode,
            "initial_input": self.initial_input,
            "final_output": self.final_output,
            "error_message": self.error_message,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "WorkflowContext":
        ctx = cls(
            workflow_id=data["workflow_id"],
            workflow_name=data["workflow_name"],
            workflow_version=data["workflow_version"],
        )
        ctx.run_id = data.get("run_id", ctx.run_id)
        ctx.operator = data.get("operator", "operator")
        ctx.started_at = data.get("started_at", ctx.started_at)
        ctx.state = data.get("state", "initialized")
        ctx.node_states = data.get("node_states", {})
        ctx.approvals = data.get("approvals", {})
        ctx.audit_entries = data.get("audit_entries", [])
        ctx.elapsed_seconds = data.get("elapsed_seconds", 0.0)
        ctx.timeout_seconds = data.get("timeout_seconds", 300.0)
        ctx.node_timings = data.get("node_timings", {})
        ctx.deterministic_fallback_activated = data.get("deterministic_fallback_activated", False)
        ctx.rollback_occurred = data.get("rollback_occurred", False)
        ctx.approval_pauses = data.get("approval_pauses", 0)
        ctx.replay_mode = data.get("replay_mode", False)
        ctx.initial_input = data.get("initial_input")
        ctx.final_output = data.get("final_output")
        ctx.error_message = data.get("error_message")
        return ctx
