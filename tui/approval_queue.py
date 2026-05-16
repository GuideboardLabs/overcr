"""
OverCR TUI — Approval Queue v2.2.0

Renders the approval queue — tasks in approval_pending state that
require explicit operator action.

Governance:
  - The TUI shows pending approvals and their rationale.
  - The TUI provides approve/reject paths that route through OverCR runtime.
  - The TUI never auto-approves or bypasses approval gates.
  - All operator actions must remain auditable.
  - Approval actions are explicit — no implicit confirmation.

Reads from filesystem state only (TaskStore).
Approval actions are returned as commands, not executed directly.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from rich.console import Console

from tui.theme import Theme, StatusColors, Icons
from tui.widgets.status_badge import StatusBadge
from tui.widgets.table import TableWidget


class ApprovalAction:
    """Represents a pending approval action that an operator may take.

    These are NOT executed by the TUI — they are returned as data
    for the operator to review and explicitly confirm through the
    OverCR runtime.
    """

    def __init__(
        self,
        task_id: str,
        action: str,  # "approve" or "reject"
        rationale: str = "",
        operator: str = "operator",
    ):
        if action not in ("approve", "reject"):
            raise ValueError(f"Action must be 'approve' or 'reject', got '{action}'")
        self.task_id = task_id
        self.action = action
        self.rationale = rationale
        self.operator = operator

    def to_dict(self) -> Dict:
        return {
            "task_id": self.task_id,
            "action": self.action,
            "rationale": self.rationale,
            "operator": self.operator,
        }

    def __repr__(self):
        return f"ApprovalAction(task_id={self.task_id!r}, action={self.action!r})"


class ApprovalQueue:
    """
    Renders the approval queue from filesystem state.

    This is a read-only observatory. Approval actions are returned
    as ApprovalAction objects that the caller routes through
    OverCR runtime governance — never executed directly here.
    """

    def __init__(self, root: str, console: Optional[Console] = None):
        self.root = Path(root)
        self.console = console or Console()
        self.badge = StatusBadge(use_unicode=True)
        self._tasks_dir = self.root / "orchestration" / "tasks"

    def get_pending_approvals(self) -> List[Dict]:
        """
        Get all tasks currently in approval_pending state.

        Returns:
            List of task dicts that need operator approval.
        """
        pending = []
        if not self._tasks_dir.exists():
            return pending

        for task_file in sorted(self._tasks_dir.glob("task-*.json")):
            try:
                with open(task_file) as f:
                    task = json.load(f)
                if task.get("state") == "approval_pending":
                    pending.append(task)
            except (json.JSONDecodeError, OSError):
                continue

        return pending

    def render_queue(self) -> str:
        """
        Render the approval queue as a formatted view.

        Returns:
            Rich-formatted approval queue.
        """
        pending = self.get_pending_approvals()

        if not pending:
            return f"[green]{Icons.check} No pending approvals[/green]"

        lines = []
        lines.append(f"[bold bright_yellow]Approvals Pending: {len(pending)}[/bold bright_yellow]")
        lines.append("")

        for task in pending:
            task_id = task.get("task_id", "?")
            domain = task.get("domain", "?")
            subagent = task.get("assigned_subagent", "?")
            description = task.get("description", "")

            # Build rationale from the response packet
            response = task.get("response_packet") or {}
            rationale = self._build_rationale(task)

            lines.append(f"  [{Theme.APPROVAL_PENDING_STYLE}]{Icons.warn} {task_id}[/{Theme.APPROVAL_PENDING_STYLE}]")
            lines.append(f"    Domain: {domain}  |  Subagent: [cyan]{subagent}[/cyan]")
            lines.append(f"    Description: {description[:80]}")

            if rationale:
                lines.append(f"    Rationale: {rationale[:120]}")

            # Show what action is required
            lines.append(f"    [bold]Action required:[/bold] approve or reject")
            lines.append("")

        return "\n".join(lines)

    def render_queue_plain(self) -> str:
        """Render the approval queue as plain text (deterministic fallback)."""
        pending = self.get_pending_approvals()

        if not pending:
            return "No pending approvals"

        lines = [f"Approvals Pending: {len(pending)}", ""]

        for task in pending:
            task_id = task.get("task_id", "?")
            domain = task.get("domain", "?")
            subagent = task.get("assigned_subagent", "?")
            description = task.get("description", "")
            rationale = self._build_rationale(task)

            lines.append(f"  {task_id}")
            lines.append(f"    Domain: {domain}  |  Subagent: {subagent}")
            lines.append(f"    Description: {description[:80]}")
            if rationale:
                lines.append(f"    Rationale: {rationale[:120]}")
            lines.append(f"    Action required: approve or reject")
            lines.append("")

        return "\n".join(lines)

    def render_detail(self, task_id: str) -> str:
        """
        Render detailed information for a pending approval.

        Args:
            task_id: The task ID with pending approval.

        Returns:
            Rich-formatted detail view.
        """
        task = self._load_task(task_id)
        if task is None:
            return f"[red]{Icons.cross} Task {task_id} not found[/red]"

        if task.get("state") != "approval_pending":
            return f"[dim]Task {task_id} is not pending approval (state: {task.get('state')})[/dim]"

        lines = []
        lines.append(f"[bold]Approval Detail — {task_id}[/bold]")
        lines.append("")

        # Task basics
        lines.append(f"  Task ID:       {task_id}")
        lines.append(f"  State:         [bright_yellow]approval_pending[/bright_yellow]")
        lines.append(f"  Subagent:      [cyan]{task.get('assigned_subagent', '?')}[/cyan]")
        lines.append(f"  Domain:        {task.get('domain', '?')}")
        lines.append(f"  Description:   {task.get('description', '')}")

        # Approval rationale
        rationale = self._build_rationale(task)
        lines.append("")
        lines.append(f"  [bold]Rationale:[/bold]")
        for reason in rationale.split("; "):
            if reason:
                lines.append(f"    {Icons.bullet} {reason}")

        # Response packet highlights
        response = task.get("response_packet") or {}
        if response:
            lines.append("")
            lines.append(f"  [bold]Response Packet:[/bold]")
            lines.append(f"    Type: {response.get('packet_type', '?')}")
            lines.append(f"    Summary: {str(response.get('summary', ''))[:120]}")
            if response.get("approval_required"):
                lines.append(f"    [bright_yellow]approval_required=True[/bright_yellow]")
            if response.get("outbound_contact"):
                lines.append(f"    [red]outbound_contact=True[/red]")

        # State log
        state_log = task.get("state_log", [])
        if state_log:
            lines.append("")
            lines.append(f"  [bold]State History ({len(state_log)} entries):[/bold]")
            for entry in state_log[-5:]:  # Last 5 entries
                ts = entry.get("timestamp", "?")[11:19]
                s = entry.get("state", "?")
                note = entry.get("note", "")
                color = StatusColors.for_task_state(s)
                lines.append(f"    [{color}]{s}[/{color}] {ts} {note}")

        # Possible actions
        lines.append("")
        lines.append("  [bold]Possible actions:[/bold]")
        lines.append(f"    [green]approve[/green] — approve the task (routes to 'approved' state)")
        lines.append(f"    [red]reject[/red]  — reject the task (may route to 'assigned' for revision)")

        return "\n".join(lines)

    def propose_approval(self, task_id: str, reason: str = "", operator: str = "operator") -> ApprovalAction:
        """
        Create an approval action for a task.

        IMPORTANT: This does NOT execute the approval. It returns
        an ApprovalAction that the caller must route through OverCR
        runtime governance (OverCRRuntime + ApprovalGate).

        Args:
            task_id: The task to approve.
            reason: Optional reason for approval.
            operator: Who is approving (default: "operator").

        Returns:
            ApprovalAction representing the proposed approval.
        """
        return ApprovalAction(
            task_id=task_id,
            action="approve",
            rationale=reason,
            operator=operator,
        )

    def propose_rejection(self, task_id: str, reason: str = "", operator: str = "operator") -> ApprovalAction:
        """
        Create a rejection action for a task.

        IMPORTANT: This does NOT execute the rejection. It returns
        an ApprovalAction that the caller must route through OverCR
        runtime governance.

        Args:
            task_id: The task to reject.
            reason: Reason for rejection.
            operator: Who is rejecting (default: "operator").

        Returns:
            ApprovalAction representing the proposed rejection.
        """
        return ApprovalAction(
            task_id=task_id,
            action="reject",
            rationale=reason,
            operator=operator,
        )

    @staticmethod
    def _build_rationale(task: Dict) -> str:
        """
        Build a rationale string for why this task needs approval.

        This is derived from filesystem state — the TUI does not
        invent reasons; it surfaces what the governance system requires.
        """
        reasons = []
        subagent = task.get("assigned_subagent", "")
        domain = task.get("domain", "")

        # Check approval requirements (mirrors ApprovalGate logic)
        if subagent == "pyper":
            reasons.append("PypER (outreach) subagent always requires approval")

        if domain in ("outreach", "outreach_draft"):
            reasons.append(f"Domain '{domain}' always requires approval")

        response = task.get("response_packet") or {}
        if response.get("approval_required"):
            reasons.append("Response packet flagged approval_required=True")

        if response.get("outbound_contact"):
            reasons.append("Response packet contains outbound_contact")

        if not reasons:
            reasons.append("Approval gate triggered by runtime policy")

        return "; ".join(reasons)

    def _load_task(self, task_id: str) -> Optional[Dict]:
        """Load a task record from filesystem."""
        path = self._tasks_dir / f"{task_id}.json"
        if not path.exists():
            return None
        try:
            with open(path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None