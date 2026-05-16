"""
OverCR TUI — Dashboard v2.2.0

Main operator dashboard that composes all views into a single
overview. Reads from filesystem state only. Never mutates state.

Shows:
  - Active tasks (summary table)
  - Workflow status (if any workflows defined)
  - Pending approvals (from approval queue)
  - Recent audit events (last N entries from audit stream)
  - Runtime health (worker availability)
  - Memory layer summary (active/stale/total)
  - Current runtime/provider routing (from config)
"""

import json
from pathlib import Path
from typing import Dict, Optional

from rich.console import Console
from rich.panel import Panel
from rich.columns import Columns
from rich.text import Text

from tui.theme import Theme, StatusColors, Icons
from tui.task_view import TaskView
from tui.workflow_view import WorkflowView
from tui.packet_inspector import PacketInspector
from tui.audit_view import AuditView
from tui.approval_queue import ApprovalQueue
from tui.status_bar import StatusBar


class Dashboard:
    """
    Main operator dashboard — composes all views.

    The dashboard is an observatory, not a cockpit:
      - It reads canonical filesystem state.
      - It renders formatted views.
      - It does NOT advance task state.
      - It does NOT bypass approval gates.
      - It does NOT create operational truth.
    """

    def __init__(self, root: str, console: Optional[Console] = None):
        """
        Args:
            root: Path to OverCR core directory.
            console: Rich console instance (creates new if None).
        """
        self.root = Path(root)
        self.console = console or Console()

        # Initialize all sub-views
        self.task_view = TaskView(root=str(self.root), console=self.console)
        self.workflow_view = WorkflowView(root=str(self.root), console=self.console)
        self.packet_inspector = PacketInspector(root=str(self.root), console=self.console)
        self.audit_view = AuditView(root=str(self.root), console=self.console)
        self.approval_queue = ApprovalQueue(root=str(self.root), console=self.console)
        self.status_bar = StatusBar(root=str(self.root), console=self.console)

    def render(self, recent_audit: int = 10) -> str:
        """
        Render the full dashboard view.

        Args:
            recent_audit: Number of recent audit entries to show.

        Returns:
            Rich-formatted dashboard string.
        """
        sections = []

        # ── Header ──
        sections.append(self._render_header())

        # ── Status bar ──
        sections.append("")
        sections.append(self.status_bar.render())
        sections.append("")

        # ── Pending approvals ──
        pending = self.approval_queue.get_pending_approvals()
        if pending:
            sections.append(self.approval_queue.render_queue())
            sections.append("")

        # ── Active tasks ──
        task_list = self.task_view.render_task_list()
        sections.append(task_list)

        # ── Recent audit ──
        if recent_audit > 0:
            sections.append("")
            sections.append(self.audit_view.render(limit=recent_audit))

        return "\n".join(sections)

    def render_plain(self) -> str:
        """
        Render a plain-text dashboard (no rich markup).

        Deterministic fallback when rich rendering is unavailable
        or when output must be machine-parseable.
        """
        lines = []
        lines.append("=" * 72)
        lines.append("OVERCR OPERATOR DASHBOARD")
        lines.append("=" * 72)
        lines.append("")

        # Status bar
        lines.append(self.status_bar.render_plain())
        lines.append("")

        # Pending approvals
        pending = self.approval_queue.get_pending_approvals()
        if pending:
            lines.append(f"Pending approvals: {len(pending)}")
            for task in pending:
                lines.append(
                    f"  {task.get('task_id', '?')} "
                    f"{task.get('domain', '?')} "
                    f"{task.get('assigned_subagent', '?')}"
                )
            lines.append("")

        # Task list
        tasks = self.task_view._load_tasks()
        active = [t for t in tasks if t.get("state") not in ("completed", "abandoned")]
        if active:
            lines.append(f"Active tasks ({len(active)}):")
            for t in active:
                lines.append(
                    f"  {t.get('task_id', '?')} "
                    f"[{t.get('state', '?')}] "
                    f"{t.get('assigned_subagent', '?')} "
                    f"{t.get('domain', '?')}"
                )
        else:
            lines.append("Tasks: none active")

        # Recent audit
        lines.append("")
        lines.append(self.audit_view.render_plain(limit=5))

        return "\n".join(lines)

    def render_section(self, section: str) -> str:
        """
        Render a single section of the dashboard.

        Args:
            section: One of "tasks", "approvals", "audit", "status", "memory".

        Returns:
            Rich-formatted section string.
        """
        if section == "tasks":
            return self.task_view.render_task_list()
        elif section == "approvals":
            return self.approval_queue.render_queue()
        elif section == "audit":
            return self.audit_view.render(limit=20)
        elif section == "status":
            return self.status_bar.render()
        elif section == "memory":
            return self._render_memory_summary()
        else:
            return f"[red]Unknown section: {section}[/red]"

    def _render_header(self) -> str:
        """Render the dashboard header."""
        lines = []
        lines.append(f"[bold bright_white]{'=' * 72}[/bold bright_white]")
        lines.append(f"[bold bright_cyan]  OVERCR OPERATOR DASHBOARD[/bold bright_cyan]")
        lines.append(f"[dim]  v2.2.0  |  Filesystem-first  |  Advisory memory  |  Governance enforced[/dim]")
        lines.append(f"[bold bright_white]{'=' * 72}[/bold bright_white]")
        return "\n".join(lines)

    def _render_memory_summary(self) -> str:
        """Render the memory layer summary."""
        mem_summary = self.status_bar._get_memory_summary()

        lines = []
        lines.append(f"[bold]Memory Layer:[/bold]")
        lines.append(f"  Total records: {mem_summary['total']}")
        lines.append(f"  Active: [green]{mem_summary['active']}[/green]")
        lines.append(f"  Stale: [yellow]{mem_summary['stale']}[/yellow]")
        lines.append(f"  Rejected: [red]{mem_summary['rejected']}[/red]")
        lines.append(f"  Superseded: [dim blue]{mem_summary['superseded']}[/dim blue]")

        return "\n".join(lines)