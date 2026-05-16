"""
OverCR TUI — Status Bar v2.2.0

Renders a runtime health summary bar at the bottom of the dashboard.
Reads from filesystem state only — never invents data.

Shows:
  - Runtime health (worker availability from registry)
  - Active task count
  - Pending approvals count
  - Memory layer summary (active/stale/total)
  - Current provider routing (from config)
"""

import json
from pathlib import Path
from typing import Dict, Optional

from rich.console import Console
from rich.text import Text

from tui.theme import Theme, StatusColors, Icons
from tui.widgets.status_badge import StatusBadge


class StatusBar:
    """
    A runtime health summary bar.

    Reads canonical filesystem state to build its summary.
    Handles missing/unavailable components gracefully — partial
    failure produces a degraded status, not a crash.
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

    def render(self) -> str:
        """
        Render the status bar.

        Gathers data from:
          - orchestration/tasks/ (task counts)
          - runtime/audit.jsonl (recent audit entries)
          - memory/ (memory summary)
          - config/ (provider routing)
          - worker_registry (if available)

        Returns:
            Rich-formatted status bar string.
        """
        segments = []

        # ── Task summary ──
        task_summary = self._get_task_summary()
        if task_summary["total"] > 0:
            segments.append(
                f"Tasks: {task_summary['total']} "
                f"[bright_cyan]{task_summary['active']}[/bright_cyan] active "
                f"[bright_yellow]{task_summary['pending_approval']}[/bright_yellow] pending"
            )
        else:
            segments.append("Tasks: [dim]none[/dim]")

        # ── Approval pending ──
        approval_count = self._count_pending_approvals()
        if approval_count > 0:
            segments.append(
                f"[bright_yellow]Approvals: {approval_count} pending[/bright_yellow]"
            )
        else:
            segments.append("Approvals: [green]0[/green]")

        # ── Memory summary ──
        mem_summary = self._get_memory_summary()
        segments.append(
            f"Memory: {mem_summary['total']} "
            f"[green]{mem_summary['active']}[/green] active "
            f"[yellow]{mem_summary['stale']}[/yellow] stale"
        )

        # ── Worker availability ──
        worker_info = self._get_worker_info()
        segments.append(
            f"Workers: {worker_info['available']}/{worker_info['total']}"
        )

        # ── Runtime health ──
        health = self._assess_health(task_summary, approval_count, mem_summary, worker_info)
        health_badge = self.badge.render(health, "health", compact=True)
        segments.append(f"Health: {health_badge}")

        return "  " + Icons.BULLET + "  ".join(segments)

    def render_plain(self) -> str:
        """Render a plain-text status bar (no rich markup)."""
        task_summary = self._get_task_summary()
        approval_count = self._count_pending_approvals()
        mem_summary = self._get_memory_summary()
        worker_info = self._get_worker_info()
        health = self._assess_health(task_summary, approval_count, mem_summary, worker_info)

        parts = [
            f"Tasks: {task_summary['total']} active={task_summary['active']} pending={task_summary['pending_approval']}",
            f"Approvals: {approval_count} pending",
            f"Memory: {mem_summary['total']} active={mem_summary['active']} stale={mem_summary['stale']}",
            f"Workers: {worker_info['available']}/{worker_info['total']}",
            f"Health: {health}",
        ]
        return " | ".join(parts)

    # ── Private data-gathering methods ───────────────────────

    def _get_task_summary(self) -> Dict:
        """Count tasks by state from filesystem."""
        tasks_dir = self.root / "orchestration" / "tasks"
        total = 0
        active = 0
        pending_approval = 0
        completed = 0
        abandoned = 0

        if tasks_dir.exists():
            for task_file in tasks_dir.glob("task-*.json"):
                try:
                    with open(task_file) as f:
                        task = json.load(f)
                    total += 1
                    state = task.get("state", "")
                    if state in ("created", "assigned", "in_progress", "response_received",
                                 "routed", "approval_pending"):
                        active += 1
                    if state == "approval_pending":
                        pending_approval += 1
                    if state == "completed":
                        completed += 1
                    if state == "abandoned":
                        abandoned += 1
                except (json.JSONDecodeError, OSError):
                    continue

        return {
            "total": total,
            "active": active,
            "pending_approval": pending_approval,
            "completed": completed,
            "abandoned": abandoned,
        }

    def _count_pending_approvals(self) -> int:
        """Count tasks in approval_pending state."""
        tasks_dir = self.root / "orchestration" / "tasks"
        count = 0
        if tasks_dir.exists():
            for task_file in tasks_dir.glob("task-*.json"):
                try:
                    with open(task_file) as f:
                        task = json.load(f)
                    if task.get("state") == "approval_pending":
                        count += 1
                except (json.JSONDecodeError, OSError):
                    continue
        return count

    def _get_memory_summary(self) -> Dict:
        """Get memory layer summary from index.jsonl."""
        index_path = self.root / "memory" / "index.jsonl"
        total = 0
        active = 0
        stale = 0
        rejected = 0
        superseded = 0

        if index_path.exists():
            try:
                with open(index_path) as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            entry = json.loads(line)
                            total += 1
                            status = entry.get("status", "")
                            if status == "active":
                                active += 1
                            elif status == "stale":
                                stale += 1
                            elif status == "rejected":
                                rejected += 1
                            elif status == "superseded":
                                superseded += 1
                        except json.JSONDecodeError:
                            continue
            except OSError:
                pass

        return {
            "total": total,
            "active": active,
            "stale": stale,
            "rejected": rejected,
            "superseded": superseded,
        }

    def _get_worker_info(self) -> Dict:
        """Get worker registry information (if available)."""
        # Workers are registered in-memory via WorkerRegistry
        # In filesystem mode, we can check subagent directories
        subagent_dir = self.root / "subagents"
        available = 0
        total = 4  # cryer, pyper, coder, knower

        if subagent_dir.exists():
            for name in ("cryer", "pyper", "coder", "knower"):
                if (subagent_dir / name).exists():
                    available += 1

        return {"available": available, "total": total}

    @staticmethod
    def _assess_health(task_summary, approval_count, mem_summary, worker_info) -> str:
        """Assess overall runtime health from gathered data."""
        # Degraded if any workers unavailable
        if worker_info["available"] < worker_info["total"]:
            return "degraded"

        # Degraded if pending approvals are stuck
        if approval_count > 0 and task_summary["active"] == approval_count:
            # All active tasks are stuck on approval
            return "degraded"

        # Unhealthy if no workers
        if worker_info["available"] == 0:
            return "unhealthy"

        # Healthy
        if task_summary["active"] > 0:
            return "healthy"

        # Idle but operational
        return "healthy"