"""
OverCR TUI — Log View Widget v2.2.0

Append-only log stream renderer for audit entries and event streams.
Rendered entries are never modified or deleted — append-only display
mirrors the append-only audit log on disk.
"""

from rich.console import Console
from rich.text import Text
from typing import List, Dict, Optional

from tui.theme import Theme, StatusColors, Icons


class LogViewWidget:
    """
    An append-only log stream renderer.

    Displays audit/event entries in chronological order.
    Supports filtering by task_id, entry_type, or subagent.
    Deterministic: same log entries always render same output.
    """

    def __init__(
        self,
        title: str = "Audit Stream",
        console: Optional[Console] = None,
        max_entries: int = 100,
    ):
        self.title = title
        self.console = console or Console()
        self.max_entries = max_entries

    def render(
        self,
        entries: List[Dict],
        filter_task: Optional[str] = None,
        filter_type: Optional[str] = None,
        filter_subagent: Optional[str] = None,
    ) -> str:
        """
        Render log entries as a formatted stream.

        Args:
            entries: List of audit entry dicts (from AuditWriter.read_log).
            filter_task: If given, only show entries for this task_id.
            filter_type: If given, only show entries of this entry_type.
            filter_subagent: If given, only show entries mentioning this subagent.

        Returns:
            Rich-formatted string.
        """
        # Apply filters
        filtered = entries
        if filter_task:
            filtered = [e for e in filtered if e.get("task_id") == filter_task]
        if filter_type:
            filtered = [e for e in filtered if e.get("entry_type") == filter_type]
        if filter_subagent:
            filtered = [
                e for e in filtered
                if filter_subagent in str(e.get("details", ""))
            ]

        # Limit to max_entries
        filtered = filtered[-self.max_entries:]

        if not filtered:
            return f"[dim]{Icons.bullet} No entries matching filters[/dim]"

        lines = []
        for entry in filtered:
            timestamp = entry.get("timestamp", "?")
            entry_type = entry.get("entry_type", "unknown")
            task_id = entry.get("task_id", "?")
            details = entry.get("details", {})

            # Choose color by entry type
            type_color = self._type_color(entry_type)

            # Format timestamp (truncate to just time)
            ts_short = timestamp[11:19] if len(timestamp) > 19 else timestamp

            line = (
                f"[{Theme.AUDIT_TIMESTAMP_STYLE}]{ts_short}[/{Theme.AUDIT_TIMESTAMP_STYLE}] "
                f"[{type_color}]{entry_type:<22}[/{type_color}] "
                f"[bold]{task_id}[/bold] "
            )

            # Add relevant detail fields
            detail_parts = []
            if "from_state" in details:
                detail_parts.append(f"{details['from_state']} → {details.get('to_state', '?')}")
            if "valid" in details:
                detail_parts.append(f"valid={'✓' if details['valid'] else '✗'}")
                if details.get("error_count"):
                    detail_parts.append(f"errors={details['error_count']}")
            if "decision" in details:
                detail_parts.append(f"decision={details['decision']}")
            if "subagent" in details:
                detail_parts.append(f"subagent={details['subagent']}")
            if "routing_target" in details:
                detail_parts.append(f"→ {details['routing_target']}")

            if detail_parts:
                line += " ".join(detail_parts)

            lines.append(line)

        return "\n".join(lines)

    def render_plain(
        self,
        entries: List[Dict],
        filter_task: Optional[str] = None,
        filter_type: Optional[str] = None,
    ) -> str:
        """
        Render a plain-text fallback (no rich markup).
        """
        filtered = entries
        if filter_task:
            filtered = [e for e in filtered if e.get("task_id") == filter_task]
        if filter_type:
            filtered = [e for e in filtered if e.get("entry_type") == filter_type]
        filtered = filtered[-self.max_entries:]

        if not filtered:
            return "No entries matching filters"

        lines = []
        for entry in filtered:
            ts = entry.get("timestamp", "?")
            etype = entry.get("entry_type", "?")
            tid = entry.get("task_id", "?")
            details = entry.get("details", {})
            detail_str = " ".join(f"{k}={v}" for k, v in details.items())
            lines.append(f"{ts} {etype:<22} {tid} {detail_str}")

        return "\n".join(lines)

    @staticmethod
    def _type_color(entry_type: str) -> str:
        """Map entry type to a display color."""
        color_map = {
            "task_created": "green",
            "state_transition": "bright_cyan",
            "validation_result": "yellow",
            "routing_decision": "blue",
            "approval_action": "bright_yellow",
            "operator_action": "bright_green",
            "revision_loop": "bright_red",
            "task_completed": "bright_green",
            "task_abandoned": "dim red",
            "runtime_start": "cyan",
            "runtime_stop": "dim",
            "error": "bright_red",
        }
        return color_map.get(entry_type, "white")