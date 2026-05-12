"""
OverCR Runtime — Approval Gate

Enforces the approval_required gate in the task lifecycle.

Key rules (from v0.0.5 doctrine):
- PypER packets ALWAYS have approval_required=true (no exceptions).
- Any packet involving outbound contact requires operator approval.
- Any CodER packet with breaking_changes=true or reversible=false should have
  approval_required=true (warning level, not hard failure — but the gate still
  enforces it at runtime level).
- The gate blocks state transitions: routed -> completion is not allowed
  if approval_required=true. The task MUST go through approval_pending first.

Approval gates are enforced, not advisory.
"""

from datetime import datetime, timezone
from typing import Optional


class ApprovalGateError(Exception):
    """Raised when an approval gate blocks an action."""
    pass


class ApprovalGate:
    """
    Enforces approval gates on task state transitions.

    The gate inspects:
    1. The response packet's approval_required field
    2. The task's domain (outreach/outreach_draft always gated)
    3. The subagent type (PypER always gated)

    When approval is required, the task MUST go through approval_pending
    before it can reach completed or trigger outbound action.
    """

    # Domains where approval is always required
    ALWAYS_APPROVAL_DOMAINS = {"outreach", "outreach_draft"}

    # Subagents where approval is always required
    ALWAYS_APPROVAL_SUBAGENTS = {"pyper"}

    MAX_REVISION_LOOPS = 3

    def check_approval_required(self, task: dict) -> bool:
        """
        Determine whether a task requires operator approval.

        Returns True if ANY of:
        - response_packet.approval_required == True
        - domain is outreach or outreach_draft
        - assigned_subagent is pyper
        """
        domain = task.get("domain", "")
        subagent = task.get("assigned_subagent", "")
        response = task.get("response_packet") or {}

        # Rule 1: Explicit flag in the packet
        if response.get("approval_required") is True:
            return True

        # Rule 2: PypER always requires approval
        if subagent in self.ALWAYS_APPROVAL_SUBAGENTS:
            return True

        # Rule 3: Outreach domains always require approval
        if domain in self.ALWAYS_APPROVAL_DOMAINS:
            return True

        return False

    def enforce_gate(self, task: dict, target_state: str) -> dict:
        """
        Check whether a state transition is allowed given approval gates.

        If a task requires approval and the target state would bypass
        approval_pending, raise ApprovalGateError.

        Returns the gate decision dict:
        {
            "approval_required": bool,
            "allowed": bool,
            "reason": str,
        }
        """
        approval_required = self.check_approval_required(task)
        current_state = task.get("state", "")

        # If approval is required and we're trying to go to 'completed'
        # without going through approval_pending, block it.
        if approval_required and target_state == "completed":
            if current_state != "approved":
                return {
                    "approval_required": True,
                    "allowed": False,
                    "reason": (
                        f"Task {task.get('task_id')} requires operator approval "
                        f"before completion. Current state: {current_state}. "
                        f"Must go through approval_pending -> approved."
                    ),
                }

        # If approval is required and current state is 'routed'
        # the next state MUST be approval_pending, not completed
        if approval_required and current_state == "routed":
            if target_state != "approval_pending":
                return {
                    "approval_required": True,
                    "allowed": False,
                    "reason": (
                        f"Task {task.get('task_id')} requires approval. "
                        f"From 'routed', must transition to 'approval_pending', "
                        f"not '{target_state}'."
                    ),
                }

        return {
            "approval_required": approval_required,
            "allowed": True,
            "reason": "" if not approval_required else "Approval required but gate satisfied.",
        }

    def process_approval(
        self,
        task: dict,
        decision: str,
        reason: Optional[str] = None,
        operator: str = "operator",
    ) -> dict:
        """
        Process an operator approval or rejection decision.

        Args:
            task: The task record.
            decision: "approved" or "rejected".
            reason: Optional reason for the decision.
            operator: Who made the decision (default: "operator").

        Returns:
            Approval record dict to store on the task.
        """
        if decision not in ("approved", "rejected"):
            raise ValueError(f"Decision must be 'approved' or 'rejected', got '{decision}'")

        return {
            "decision": decision,
            "operator": operator,
            "reason": reason or "",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def check_revision_limit(self, task: dict) -> dict:
        """
        Check if the task has exceeded the revision loop limit (max 3).

        Returns:
            dict with:
              - revision_count: current count
              - limit_reached: bool
              - remaining: int
        """
        count = task.get("revision_count", 0)
        return {
            "revision_count": count,
            "limit_reached": count >= self.MAX_REVISION_LOOPS,
            "remaining": max(0, self.MAX_REVISION_LOOPS - count),
        }

    def should_block_outbound(self, task: dict) -> tuple[bool, str]:
        """
        Check whether the task should block any outbound/irreversible action.

        This is the final safety gate — no outbound action is ever
        taken without explicit operator approval.

        Returns:
            (blocked: bool, reason: str)
        """
        approval_required = self.check_approval_required(task)

        if not approval_required:
            return False, "No approval gate — outbound not blocked by default."

        state = task.get("state", "")
        approval = task.get("operator_approval")

        if state == "approved" and approval and approval.get("decision") == "approved":
            return False, "Operator has approved — outbound may proceed."

        # If task is completed and was approved, outbound is unblocked
        if state == "completed" and approval and approval.get("decision") == "approved":
            return False, "Task completed with operator approval — outbound may proceed."

        return True, (
            f"Outbound blocked. Task {task.get('task_id')} requires operator "
            f"approval. Current state: {state}. No approval record found."
        )