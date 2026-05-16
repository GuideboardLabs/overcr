"""
OverCR TUI — Widgets Package

Reusable terminal UI widgets built on rich.
Each widget is a deterministic renderer — same input always produces same output.
"""

from tui.widgets.table import TableWidget
from tui.widgets.panel import PanelWidget
from tui.widgets.log_view import LogViewWidget
from tui.widgets.status_badge import StatusBadge

__all__ = ["TableWidget", "PanelWidget", "LogViewWidget", "StatusBadge"]