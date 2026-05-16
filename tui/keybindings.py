"""
OverCR TUI — Keybindings v2.2.0

Keyboard binding definitions for the operator interface.
These are declarative specifications — the actual key handling
depends on the frontend (rich console, textual app, or plain stdin).

Design:
  - Bindings are grouped by scope (navigation, task, workflow, etc.)
  - Multiple keys can map to the same action
  - Bindings are data, not logic — no side effects
  - Deterministic: same binding config always produces same behavior
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Binding:
    """A single key binding."""
    keys: List[str]           # e.g. ["q", "ctrl+c"]
    action: str               # e.g. "quit"
    description: str          # Human-readable description
    scope: str = "global"     # Which scope this binding belongs to


class BindingScope:
    """Predefined binding scopes."""
    GLOBAL = "global"
    DASHBOARD = "dashboard"
    TASK_VIEW = "task_view"
    WORKFLOW_VIEW = "workflow_view"
    PACKET_INSPECTOR = "packet_inspector"
    AUDIT_VIEW = "audit_view"
    APPROVAL_QUEUE = "approval_queue"


class KeyBindings:
    """
    Declarative key binding registry.

    Bindings are organized by scope. The registry can produce
    help text, conflict detection, and scope-filtered lookups.

    This is a data structure, not an event handler.
    It does not capture input or dispatch actions.
    """

    # ── Global bindings ──────────────────────────────────────

    GLOBAL_BINDINGS = [
        Binding(keys=["q", "ctrl+c"], action="quit",
                description="Quit the operator interface", scope=BindingScope.GLOBAL),
        Binding(keys=["?"], action="help",
                description="Show keybinding help", scope=BindingScope.GLOBAL),
        Binding(keys=["h"], action="home",
                description="Go to dashboard home view", scope=BindingScope.GLOBAL),
        Binding(keys=["r"], action="refresh",
                description="Refresh current view from filesystem", scope=BindingScope.GLOBAL),
        Binding(keys=["t"], action="tasks",
                description="Switch to task list view", scope=BindingScope.GLOBAL),
        Binding(keys=["w"], action="workflows",
                description="Switch to workflow view", scope=BindingScope.GLOBAL),
        Binding(keys=["p"], action="packets",
                description="Switch to packet inspector", scope=BindingScope.GLOBAL),
        Binding(keys=["a"], action="audit",
                description="Switch to audit stream view", scope=BindingScope.GLOBAL),
        Binding(keys=["o"], action="approvals",
                description="Switch to approval queue", scope=BindingScope.GLOBAL),
        Binding(keys=["m"], action="memory",
                description="Switch to memory layer summary", scope=BindingScope.GLOBAL),
        Binding(keys=["b"], action="status_bar",
                description="Toggle status bar visibility", scope=BindingScope.GLOBAL),
    ]

    # ── Task view bindings ──────────────────────────────────

    TASK_VIEW_BINDINGS = [
        Binding(keys=["enter"], action="task_detail",
                description="View task detail", scope=BindingScope.TASK_VIEW),
        Binding(keys=["f"], action="filter_state",
                description="Filter tasks by state", scope=BindingScope.TASK_VIEW),
        Binding(keys=["n"], action="next_page",
                description="Next page of tasks", scope=BindingScope.TASK_VIEW),
        Binding(keys=["p"], action="prev_page",
                description="Previous page of tasks", scope=BindingScope.TASK_VIEW),
        Binding(keys=["s"], action="sort",
                description="Change sort order", scope=BindingScope.TASK_VIEW),
        Binding(keys=["u"], action="task_audit",
                description="Show audit trail for task", scope=BindingScope.TASK_VIEW),
    ]

    # ── Workflow view bindings ──────────────────────────────

    WORKFLOW_VIEW_BINDINGS = [
        Binding(keys=["enter"], action="node_detail",
                description="View node detail", scope=BindingScope.WORKFLOW_VIEW),
        Binding(keys=["e"], action="edge_detail",
                description="View edge/handoff detail", scope=BindingScope.WORKFLOW_VIEW),
        Binding(keys=["x"], action="expand_collapse",
                description="Expand/collapse node subtree", scope=BindingScope.WORKFLOW_VIEW),
        Binding(keys=["g"], action="approval_gates",
                description="Highlight approval-gated nodes", scope=BindingScope.WORKFLOW_VIEW),
        Binding(keys=["d"], action="deterministic_fallback",
                description="Show deterministic fallback markers", scope=BindingScope.WORKFLOW_VIEW),
    ]

    # ── Packet inspector bindings ───────────────────────────

    PACKET_INSPECTOR_BINDINGS = [
        Binding(keys=["v"], action="validation_detail",
                description="Show L1-L6 validation results", scope=BindingScope.PACKET_INSPECTOR),
        Binding(keys=["r"], action="provenance",
                description="Show provenance metadata", scope=BindingScope.PACKET_INSPECTOR),
        Binding(keys=["o"], action="routing",
                description="Show routing metadata", scope=BindingScope.PACKET_INSPECTOR),
    ]

    # ── Audit view bindings ──────────────────────────────────

    AUDIT_VIEW_BINDINGS = [
        Binding(keys=["f"], action="filter",
                description="Filter audit stream", scope=BindingScope.AUDIT_VIEW),
        Binding(keys=["t"], action="filter_task",
                description="Filter by task_id", scope=BindingScope.AUDIT_VIEW),
        Binding(keys=["e"], action="filter_entry_type",
                description="Filter by entry_type", scope=BindingScope.AUDIT_VIEW),
        Binding(keys=["u"], action="replay_nav",
                description="Navigate replay markers", scope=BindingScope.AUDIT_VIEW),
        Binding(keys=["j", "down"], action="scroll_down",
                description="Scroll audit stream down", scope=BindingScope.AUDIT_VIEW),
        Binding(keys=["k", "up"], action="scroll_up",
                description="Scroll audit stream up", scope=BindingScope.AUDIT_VIEW),
    ]

    # ── Approval queue bindings ──────────────────────────────

    APPROVAL_QUEUE_BINDINGS = [
        Binding(keys=["y", "a"], action="approve",
                description="Approve selected task", scope=BindingScope.APPROVAL_QUEUE),
        Binding(keys=["n", "r"], action="reject",
                description="Reject selected task", scope=BindingScope.APPROVAL_QUEUE),
        Binding(keys=["enter"], action="detail",
                description="View approval rationale", scope=BindingScope.APPROVAL_QUEUE),
        Binding(keys=["d"], action="rationale",
                description="Show full rationale for pending approval", scope=BindingScope.APPROVAL_QUEUE),
    ]

    def __init__(self):
        self._bindings: List[Binding] = []
        self._by_action: Dict[str, Binding] = {}
        self._load_defaults()

    def _load_defaults(self):
        """Load all predefined bindings."""
        all_bindings = (
            self.GLOBAL_BINDINGS
            + self.TASK_VIEW_BINDINGS
            + self.WORKFLOW_VIEW_BINDINGS
            + self.PACKET_INSPECTOR_BINDINGS
            + self.AUDIT_VIEW_BINDINGS
            + self.APPROVAL_QUEUE_BINDINGS
        )
        for binding in all_bindings:
            self._bindings.append(binding)
            # Last binding wins for an action (allows overrides)
            self._by_action[binding.action] = binding

    def get_binding(self, action: str) -> Optional[Binding]:
        """Look up a binding by action name."""
        return self._by_action.get(action)

    def get_bindings_for_scope(self, scope: str) -> List[Binding]:
        """Get all bindings for a given scope, plus global."""
        result = [b for b in self._bindings if b.scope == BindingScope.GLOBAL]
        result.extend(b for b in self._bindings if b.scope == scope)
        return result

    def get_all_bindings(self) -> List[Binding]:
        """Get all registered bindings."""
        return list(self._bindings)

    def format_help(self, scope: Optional[str] = None) -> str:
        """
        Format a help text showing keybindings.

        Args:
            scope: If given, show only bindings for this scope + global.
                   If None, show all bindings.

        Returns:
            Formatted help string.
        """
        if scope:
            bindings = self.get_bindings_for_scope(scope)
        else:
            bindings = self.get_all_bindings()

        lines = []
        lines.append("OverCR Operator Interface — Keybindings")
        lines.append("=" * 50)

        current_scope = None
        for binding in sorted(bindings, key=lambda b: (b.scope, b.action)):
            if binding.scope != current_scope:
                current_scope = binding.scope
                lines.append(f"\n[{current_scope}]")
            keys_str = ", ".join(binding.keys)
            lines.append(f"  {keys_str:<15} {binding.action:<20} {binding.description}")

        return "\n".join(lines)