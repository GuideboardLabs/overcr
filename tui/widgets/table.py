"""
OverCR TUI — Table Widget v2.2.0

Deterministic table rendering using rich.table.Table.
Reads data from filesystem state or provided dicts — never mutates.
Produces consistent output for the same input regardless of terminal width.
"""

from rich.console import Console
from rich.table import Table
from typing import List, Dict, Optional

from tui.theme import Theme, StatusColors


class TableWidget:
    """
    A deterministic table renderer.

    Given column definitions and row data, produces a rich Table
    or plain-text fallback. Does not depend on terminal width —
    uses fixed column widths from Theme for determinism.
    """

    def __init__(
        self,
        title: str = "",
        columns: Optional[List[Dict]] = None,
        console: Optional[Console] = None,
        unicode: bool = True,
    ):
        """
        Args:
            title: Table title.
            columns: List of column dicts with 'key', 'header', 'style', 'width'.
            console: Rich console instance (creates new if None).
            unicode: Whether to use Unicode box-drawing characters.
        """
        self.title = title
        self.columns = columns or []
        self.console = console or Console()
        self.unicode = unicode

    @staticmethod
    def from_tasks(
        tasks: List[Dict],
        title: str = "Active Tasks",
        console: Optional[Console] = None,
    ) -> "TableWidget":
        """Create a table widget from task records."""
        columns = [
            {"key": "task_id", "header": "Task ID", "style": "bold", "width": 14},
            {"key": "state", "header": "State", "style": None, "width": 16},
            {"key": "assigned_subagent", "header": "Subagent", "style": "cyan", "width": 10},
            {"key": "domain", "header": "Domain", "style": None, "width": 18},
            {"key": "description", "header": "Description", "style": None, "width": 30},
        ]
        widget = TableWidget(title=title, columns=columns, console=console)
        widget.rows = tasks
        return widget

    @staticmethod
    def from_approvals(
        tasks: List[Dict],
        title: str = "Pending Approvals",
        console: Optional[Console] = None,
    ) -> "TableWidget":
        """Create a table widget from approval-pending tasks."""
        columns = [
            {"key": "task_id", "header": "Task ID", "style": "bold", "width": 14},
            {"key": "domain", "header": "Domain", "style": None, "width": 18},
            {"key": "assigned_subagent", "header": "Subagent", "style": "cyan", "width": 10},
            {"key": "rationale", "header": "Rationale", "style": None, "width": 40},
        ]
        widget = TableWidget(title=title, columns=columns, console=console)
        widget.rows = tasks
        return widget

    def render(self, rows: Optional[List[Dict]] = None) -> str:
        """
        Render the table to a string.

        Args:
            rows: Row data (uses self.rows if not provided).

        Returns:
            Rich-formatted string representation.
        """
        if rows is None:
            rows = getattr(self, "rows", [])

        table = Table(
            title=self.title,
            show_header=True,
            show_lines=False,
            border_style=Theme.TABLE_BORDER_STYLE,
            header_style=Theme.TABLE_HEADER_STYLE,
            title_style=Theme.HEADER_STYLE,
            expand=False,
        )

        for col in self.columns:
            table.add_column(
                col["header"],
                style=col.get("style"),
                width=col.get("width"),
                no_wrap=True,
            )

        for row in rows:
            row_values = []
            for col in self.columns:
                key = col["key"]
                value = row.get(key, "")
                # Special styling for state column
                if key == "state" and value:
                    color = StatusColors.for_task_state(str(value))
                    row_values.append(f"[{color}]{value}[/{color}]")
                elif key == "description" and len(str(value)) > col.get("width", 30):
                    row_values.append(str(value)[:col.get("width", 30) - 3] + "...")
                else:
                    row_values.append(str(value))

            table.add_row(*row_values)

        # Capture to string
        with self.console.capture() as capture:
            self.console.print(table)
        return capture.get()

    def render_plain(self, rows: Optional[List[Dict]] = None) -> str:
        """
        Render a plain-text fallback (no rich markup).

        Used as deterministic fallback when rich rendering fails.
        """
        if rows is None:
            rows = getattr(self, "rows", [])

        col_widths = [col.get("width", 20) for col in self.columns]
        headers = [col["header"] for col in self.columns]

        lines = []
        # Title
        if self.title:
            lines.append(self.title)
            lines.append("=" * sum(col_widths))

        # Header
        header_line = "  ".join(
            h.ljust(w) for h, w in zip(headers, col_widths)
        )
        lines.append(header_line)
        lines.append("-" * len(header_line))

        # Rows
        for row in rows:
            values = []
            for col in self.columns:
                key = col["key"]
                value = str(row.get(key, ""))
                width = col.get("width", 20)
                values.append(value.ljust(width)[:width])
            lines.append("  ".join(values))

        return "\n".join(lines)