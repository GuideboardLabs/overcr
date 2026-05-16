"""
OverCR TUI — Task View v2.2.0

Renders task lifecycle state from canonical filesystem state.
Reads task records from orchestration/tasks/ — never mutates them.

Shows:
  - task lifecycle state
  - assigned subagent
  - approval state
  - packet history (request + response)
  - audit references
  - workflow membership
"""

import json
from pathlib import Path
from typing import Dict, List, Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from tui.theme import Theme, StatusColors, Icons
from tui.widgets.status_badge import StatusBadge
from tui.widgets.table import TableWidget


class TaskView:
    """
    Renders task lifecycle information from filesystem state.

    Governance: This view is read-only. It renders canonical state
    from disk. It never advances task state directly.
    """

    def __init__(self, root: str, console: Optional[Console] = None):
        """
        Args:
            root: Path to OverCR core directory.
            console: Rich console instance.
        """
        self.root = Path(root)
        self.console = console or Console()
        self.badge = StatusBadge(use_unicode=True)
        self._tasks_dir = self.root / "orchestration" / "tasks"

    def render_task_list(
        self,
        filter_state: Optional[str] = None,
        filter_subagent: Optional[str] = None,
    ) -> str:
        """
        Render a list of tasks with summary information.

        Args:
            filter_state: If given, only show tasks in this state.
            filter_subagent: If given, only show tasks for this subagent.

        Returns:
            Rich-formatted task list.
        """
        tasks = self._load_tasks()
        if filter_state:
            tasks = [t for t in tasks if t.get("state") == filter_state]
        if filter_subagent:
            tasks = [t for t in tasks if t.get("assigned_subagent") == filter_subagent]

        if not tasks:
            return f"[dim]{Icons.bullet} No tasks found[/dim]"

        table = TableWidget(
            title="Task List",
            columns=[
                {"key": "task_id", "header": "Task ID", "style": "bold", "width": 14},
                {"key": "state", "header": "State", "style": None, "width": 16},
                {"key": "assigned_subagent", "header": "Subagent", "style": "cyan", "width": 10},
                {"key": "domain", "header": "Domain", "style": None, "width": 18},
                {"key": "description", "header": "Description", "style": None, "width": 30},
            ],
            console=self.console,
        )
        return table.render(tasks)

    def render_task_detail(self, task_id: str) -> str:
        """
        Render detailed information for a single task.

        Args:
            task_id: The task ID to render (e.g. "task-0565").

        Returns:
            Rich-formatted task detail view.
        """
        task = self._load_task(task_id)
        if task is None:
            return f"[red]{Icons.cross} Task {task_id} not found[/red]"

        state = task.get("state", "?")
        state_badge = self.badge.render(state, "task")
        subagent = task.get("assigned_subagent", "?")
        domain = task.get("domain", "?")
        description = task.get("description", "")
        revision_count = task.get("revision_count", 0)

        lines = []
        lines.append(f"[bold]Task Detail: {task_id}[/bold]")
        lines.append(f"  State: {state_badge}")
        lines.append(f"  Subagent: [cyan]{subagent}[/cyan]")
        lines.append(f"  Domain: {domain}")
        lines.append(f"  Description: {description}")
        lines.append(f"  Revisions: {revision_count}")

        # ── State log ──
        state_log = task.get("state_log", [])
        if state_log:
            lines.append("")
            lines.append(f"[bold]State History ({len(state_log)} entries):[/bold]")
            for entry in state_log:
                ts = entry.get("timestamp", "?")[11:19] if entry.get("timestamp") else "?"
                s = entry.get("state", "?")
                note = entry.get("note", "")
                color = StatusColors.for_task_state(s)
                lines.append(f"  [{color}]{s}[/{color}] {ts} {note}")

        # ── Approval state ──
        approval = task.get("operator_approval")
        if approval:
            lines.append("")
            lines.append("[bold]Approval:[/bold]")
            decision = approval.get("decision", "?")
            color = "green" if decision == "approved" else "red"
            lines.append(f"  Decision: [{color}]{decision}[/{color}]")
            lines.append(f"  Operator: {approval.get('operator', '?')}")
            lines.append(f"  Reason: {approval.get('reason', '—')}")
            lines.append(f"  Timestamp: {approval.get('timestamp', '?')}")
        elif state == "approval_pending":
            lines.append("")
            lines.append("[bright_yellow]  ⏳ Awaiting operator approval[/bright_yellow]")

        # ── Validation result ──
        validation = task.get("validation_result")
        if validation is not None:
            lines.append("")
            lines.append("[bold]Validation:[/bold]")
            valid = validation.get("valid", False)
            v_icon = Icons.check if valid else Icons.cross
            v_color = "green" if valid else "red"
            lines.append(f"  [{v_color}]{v_icon} Valid={valid}[/{v_color}]")
            if validation.get("errors"):
                for err in validation["errors"][:5]:
                    lines.append(f"    [red]{Icons.cross} {err}[/red]")
            if validation.get("warnings"):
                for warn in validation["warnings"][:5]:
                    lines.append(f"    [yellow]{Icons.warn} {warn}[/yellow]")

        # ── Routing decision ──
        routing = task.get("routing_decision")
        if routing:
            lines.append("")
            lines.append("[bold]Routing:[/bold]")
            lines.append(f"  Target: [blue]{routing.get('routing_target', '?')}[/blue]")
            lines.append(f"  Reason: {routing.get('reason', '—')}")

        # ── Response packet ──
        response = task.get("response_packet")
        if response:
            lines.append("")
            lines.append("[bold]Response Packet:[/bold]")
            pkt_type = response.get("packet_type", "?")
            lines.append(f"  Type: {pkt_type}")
            lines.append(f"  Source: {response.get('source', '?')}")
            summary = response.get("summary", "")
            if summary:
                lines.append(f"  Summary: {summary[:100]}")

        # ── Upstream task ──
        upstream = task.get("upstream_task_id")
        if upstream:
            lines.append(f"\n[dim]Upstream: {upstream}[/dim]")

        return "\n".join(lines)

    def render_task_detail_plain(self, task_id: str) -> str:
        """
        Render task detail as plain text (deterministic fallback).
        """
        task = self._load_task(task_id)
        if task is None:
            return f"Task {task_id} not found"

        lines = []
        lines.append(f"Task: {task_id}")
        lines.append(f"  State: {task.get('state', '?')}")
        lines.append(f"  Subagent: {task.get('assigned_subagent', '?')}")
        lines.append(f"  Domain: {task.get('domain', '?')}")
        lines.append(f"  Description: {task.get('description', '')}")
        lines.append(f"  Revisions: {task.get('revision_count', 0)}")

        for entry in task.get("state_log", []):
            ts = entry.get("timestamp", "?")
            lines.append(f"  {entry.get('state', '?')} {ts} {entry.get('note', '')}")

        approval = task.get("operator_approval")
        if approval:
            lines.append(f"  Approval: {approval.get('decision', '?')} by {approval.get('operator', '?')}")

        return "\n".join(lines)

    def render_workflow_membership(self, task_id: str) -> str:
        """
        Show which workflows reference this task, if any.

        Checks orchestration/tasks/<task_id>.json for workflow references.
        """
        task = self._load_task(task_id)
        if task is None:
            return f"Task {task_id} not found"

        lines = [f"[bold]Workflow membership for {task_id}:[/bold]"]

        # Check upstream task reference
        upstream = task.get("upstream_task_id")
        if upstream:
            lines.append(f"  Upstream: {upstream}")

        # Check if this task appears in any workflow graph definitions
        # (search in orchestration/ for workflow references)
        orch_dir = self.root / "orchestration"
        if orch_dir.exists():
            found = False
            for wf_file in orch_dir.glob("task_*_flow.json"):
                try:
                    with open(wf_file) as f:
                        data = json.load(f)
                    # Search for this task_id in the workflow
                    data_str = json.dumps(data)
                    if task_id in data_str:
                        lines.append(f"  Workflow: {wf_file.name}")
                        found = True
                except (json.JSONDecodeError, OSError):
                    continue

            if not found:
                lines.append("  [dim]Not referenced in any workflow file[/dim]")
        else:
            lines.append("  [dim]No orchestration directory found[/dim]")

        return "\n".join(lines)

    def _load_tasks(self) -> List[Dict]:
        """Load all task records from filesystem."""
        tasks = []
        if not self._tasks_dir.exists():
            return tasks
        for task_file in sorted(self._tasks_dir.glob("task-*.json")):
            try:
                with open(task_file) as f:
                    tasks.append(json.load(f))
            except (json.JSONDecodeError, OSError):
                continue
        return tasks

    def _load_task(self, task_id: str) -> Optional[Dict]:
        """Load a single task record from filesystem."""
        path = self._tasks_dir / f"{task_id}.json"
        if not path.exists():
            return None
        try:
            with open(path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None