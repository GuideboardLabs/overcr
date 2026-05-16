"""
OverCR Operator Interface Layer (v2.2.0)

Terminal-first operator observatory for the OverCR orchestration substrate.
Reads canonical filesystem state. Renders formatted views. Never mutates state.

Governance constraints:
  - TUI cannot directly bypass runtime policy
  - TUI actions must still route through OverCR governance
  - TUI reflects operational truth; it does not create truth
  - All operator actions must remain auditable
"""

from tui.theme import Theme, StatusColors, Icons
from tui.keybindings import KeyBindings, BindingScope
from tui.dashboard import Dashboard
from tui.task_view import TaskView
from tui.workflow_view import WorkflowView
from tui.packet_inspector import PacketInspector
from tui.audit_view import AuditView
from tui.approval_queue import ApprovalQueue
from tui.status_bar import StatusBar

__version__ = "2.2.0"

__all__ = [
    "Theme",
    "StatusColors",
    "Icons",
    "KeyBindings",
    "BindingScope",
    "Dashboard",
    "TaskView",
    "WorkflowView",
    "PacketInspector",
    "AuditView",
    "ApprovalQueue",
    "StatusBar",
]