"""
OverCR TUI — Audit View v2.2.0

Renders the append-only audit stream from runtime/audit.jsonl.
Reads only — never modifies audit entries.

Supports:
  - Filtering by task_id, entry_type, subagent
  - Severity/status badges
  - Replay navigation hooks (timestamp-based)
  - Deterministic plain-text fallback
"""

import json
from pathlib import Path
from typing import Dict, List, Optional

from rich.console import Console

from tui.theme import Theme, StatusColors, Icons
from tui.widgets.log_view import LogViewWidget


class AuditView:
    """
    Renders the append-only audit stream.

    Governance: The audit log is immutable from the TUI perspective.
    This view reads audit.jsonl and renders it. It never creates,
    modifies, or deletes audit entries.
    """

    # Entry-type categories for filtering
    TASK_EVENTS = {"task_created", "state_transition", "task_completed", "task_abandoned"}
    VALIDATION_EVENTS = {"validation_result"}
    ROUTING_EVENTS = {"routing_decision"}
    APPROVAL_EVENTS = {"approval_action", "operator_action"}
    REVISION_EVENTS = {"revision_loop"}
    RUNTIME_EVENTS = {"runtime_start", "runtime_stop", "error"}

    ENTRY_CATEGORIES = {
        "task": TASK_EVENTS,
        "validation": VALIDATION_EVENTS,
        "routing": ROUTING_EVENTS,
        "approval": APPROVAL_EVENTS,
        "revision": REVISION_EVENTS,
        "runtime": RUNTIME_EVENTS,
    }

    def __init__(self, root: str, console: Optional[Console] = None):
        self.root = Path(root)
        self.console = console or Console()
        self.log_view = LogViewWidget(
            title="Audit Stream",
            console=console,
        )

    def render(
        self,
        filter_task: Optional[str] = None,
        filter_type: Optional[str] = None,
        filter_subagent: Optional[str] = None,
        filter_category: Optional[str] = None,
        limit: int = 50,
        after_timestamp: Optional[str] = None,
    ) -> str:
        """
        Render the audit stream.

        Args:
            filter_task: Only show entries for this task_id.
            filter_type: Only show entries of this entry_type.
            filter_subagent: Only show entries mentioning this subagent.
            filter_category: Filter by category ("task", "validation", etc.).
            limit: Maximum entries to show.
            after_timestamp: Only show entries after this ISO timestamp.

        Returns:
            Rich-formatted audit stream string.
        """
        entries = self._read_audit_log(limit=1000)

        # Apply timestamp filter first
        if after_timestamp:
            entries = [e for e in entries if e.get("timestamp", "") > after_timestamp]

        # Apply category filter
        if filter_category and filter_category in self.ENTRY_CATEGORIES:
            allowed = self.ENTRY_CATEGORIES[filter_category]
            entries = [e for e in entries if e.get("entry_type") in allowed]

        # Limit to requested count
        entries = entries[-limit:]

        return self.log_view.render(
            entries,
            filter_task=filter_task,
            filter_type=filter_type,
            filter_subagent=filter_subagent,
        )

    def render_plain(
        self,
        filter_task: Optional[str] = None,
        filter_type: Optional[str] = None,
        limit: int = 50,
    ) -> str:
        """Render plain-text audit stream (deterministic fallback)."""
        entries = self._read_audit_log(limit=limit)
        return self.log_view.render_plain(
            entries,
            filter_task=filter_task,
            filter_type=filter_type,
        )

    def render_entry_detail(self, entry: Dict) -> str:
        """
        Render detailed information for a single audit entry.

        Args:
            entry: An audit entry dict.

        Returns:
            Rich-formatted entry detail.
        """
        lines = []
        etype = entry.get("entry_type", "unknown")
        task_id = entry.get("task_id", "?")
        timestamp = entry.get("timestamp", "?")
        details = entry.get("details", {})

        type_color = LogViewWidget._type_color(etype)
        lines.append(f"[bold]Audit Entry — {etype}[/bold]")
        lines.append(f"  Timestamp: [{Theme.AUDIT_TIMESTAMP_STYLE}]{timestamp}[/{Theme.AUDIT_TIMESTAMP_STYLE}]")
        lines.append(f"  Task: [bold]{task_id}[/bold]")
        lines.append(f"  Type: [{type_color}]{etype}[/{type_color}]")

        # Type-specific detail rendering
        if etype == "state_transition":
            lines.append(f"  {details.get('from_state', '?')} → {details.get('to_state', '?')}")
            lines.append(f"  Note: {details.get('note', '')}")

        elif etype == "validation_result":
            valid = details.get("valid", False)
            icon = Icons.check if valid else Icons.cross
            color = "green" if valid else "red"
            lines.append(f"  [{color}]{icon} Valid: {valid}[/{color}]")
            lines.append(f"  Errors: {details.get('error_count', 0)}")
            lines.append(f"  Warnings: {details.get('warning_count', 0)}")

        elif etype == "approval_action":
            decision = details.get("decision", "?")
            color = "green" if decision == "approved" else "red"
            lines.append(f"  Decision: [{color}]{decision}[/{color}]")
            lines.append(f"  Operator: {details.get('operator', '?')}")
            if details.get("reason"):
                lines.append(f"  Reason: {details['reason']}")

        elif etype == "routing_decision":
            lines.append(f"  Target: [blue]{details.get('routing_target', '?')}[/blue]")
            lines.append(f"  Reason: {details.get('reason', '?')}")
            lines.append(f"  Creates downstream: {'Yes' if details.get('creates_downstream_task') else 'No'}")

        elif etype == "revision_loop":
            lines.append(f"  Revision count: {details.get('revision_count', '?')}")
            lines.append(f"  Reason: {details.get('reason', '')}")

        else:
            # Generic detail rendering
            for key, value in details.items():
                lines.append(f"  {key}: {value}")

        return "\n".join(lines)

    def get_available_categories(self) -> List[str]:
        """Return list of available filter categories."""
        return list(self.ENTRY_CATEGORIES.keys())

    def _read_audit_log(self, limit: int = 100) -> List[Dict]:
        """Read audit entries from audit.jsonl."""
        audit_path = self.root / "runtime" / "audit.jsonl"
        if not audit_path.exists():
            return []

        entries = []
        try:
            with open(audit_path) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        except OSError:
            return []

        return entries[-limit:]