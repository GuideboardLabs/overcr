"""
OverCR TUI — Theme v2.2.0

Terminal theme and color constants for the operator interface.
Uses rich for rendering. All colors degrade gracefully on terminals
without true-color support.

Design:
  - Semantic status colors: consistent across all views
  - Panel styles: borders and padding for layout
  - Icon set: Unicode-first, ASCII fallback
  - Deterministic rendering: same state always renders same output
"""


class StatusColors:
    """Semantic status colors for task/workflow/node states."""

    # Task states (from task_store VALID_STATES)
    CREATED = "dim white"
    ASSIGNED = "cyan"
    IN_PROGRESS = "bright_cyan"
    RESPONSE_RECEIVED = "yellow"
    VALIDATION_PASSED = "bright_green"
    VALIDATION_FAILED = "bright_red"
    ROUTED = "blue"
    APPROVAL_PENDING = "bright_yellow"
    APPROVED = "green"
    REJECTED = "red"
    COMPLETED = "bright_green"
    ABANDONED = "dim red"

    # Workflow states
    PENDING = "dim white"
    RUNNING = "bright_cyan"
    PAUSED = "yellow"
    WORKFLOW_COMPLETED = "bright_green"
    FAILED = "bright_red"
    STOPPED = "dim red"

    # Node execution states
    NODE_PENDING = "dim white"
    NODE_RUNNING = "bright_cyan"
    NODE_COMPLETED = "green"
    NODE_FAILED = "red"
    NODE_SKIPPED = "dim"
    NODE_WAITING_APPROVAL = "bright_yellow"

    # Validation levels (L1-L6)
    L1 = "bright_red"
    L2 = "red"
    L3 = "yellow"
    L4 = "cyan"
    L5 = "bright_cyan"
    L6 = "bright_green"

    # Approval
    APPROVAL_REQUIRED = "bright_yellow"
    APPROVAL_GRANTED = "green"
    APPROVAL_BLOCKED = "red"
    APPROVAL_NOT_REQUIRED = "dim green"

    # Health
    HEALTHY = "bright_green"
    DEGRADED = "yellow"
    UNHEALTHY = "bright_red"
    UNKNOWN = "dim white"

    # Memory statuses
    MEMORY_ACTIVE = "green"
    MEMORY_STALE = "yellow"
    MEMORY_REJECTED = "red"
    MEMORY_SUPERSEDED = "dim blue"

    @classmethod
    def for_task_state(cls, state: str) -> str:
        """Map a task state to its color."""
        mapping = {
            "created": cls.CREATED,
            "assigned": cls.ASSIGNED,
            "in_progress": cls.IN_PROGRESS,
            "response_received": cls.RESPONSE_RECEIVED,
            "validation_passed": cls.VALIDATION_PASSED,
            "validation_failed": cls.VALIDATION_FAILED,
            "routed": cls.ROUTED,
            "approval_pending": cls.APPROVAL_PENDING,
            "approved": cls.APPROVED,
            "rejected": cls.REJECTED,
            "completed": cls.COMPLETED,
            "abandoned": cls.ABANDONED,
        }
        return mapping.get(state, cls.UNKNOWN)

    @classmethod
    def for_workflow_state(cls, state: str) -> str:
        """Map a workflow state to its color."""
        mapping = {
            "pending": cls.PENDING,
            "running": cls.RUNNING,
            "paused": cls.PAUSED,
            "completed": cls.WORKFLOW_COMPLETED,
            "failed": cls.FAILED,
            "stopped": cls.STOPPED,
        }
        return mapping.get(state, cls.UNKNOWN)

    @classmethod
    def for_node_state(cls, state: str) -> str:
        """Map a node execution state to its color."""
        mapping = {
            "pending": cls.NODE_PENDING,
            "running": cls.NODE_RUNNING,
            "completed": cls.NODE_COMPLETED,
            "failed": cls.NODE_FAILED,
            "skipped": cls.NODE_SKIPPED,
            "waiting_approval": cls.NODE_WAITING_APPROVAL,
        }
        return mapping.get(state, cls.UNKNOWN)

    @classmethod
    def for_validation_level(cls, level: int) -> str:
        """Map validation level (1-6) to its color."""
        mapping = {
            1: cls.L1,
            2: cls.L2,
            3: cls.L3,
            4: cls.L4,
            5: cls.L5,
            6: cls.L6,
        }
        return mapping.get(level, cls.UNKNOWN)

    @classmethod
    def for_memory_status(cls, status: str) -> str:
        """Map a memory status to its color."""
        mapping = {
            "active": cls.MEMORY_ACTIVE,
            "stale": cls.MEMORY_STALE,
            "rejected": cls.MEMORY_REJECTED,
            "superseded": cls.MEMORY_SUPERSEDED,
        }
        return mapping.get(status, cls.UNKNOWN)


class Icons:
    """Unicode icon set with ASCII fallbacks.

    Use these for consistent iconography across all views.
    The ASCII fallbacks are used when Unicode is unavailable.
    """

    # Status
    CHECK = "\u2713"     # ✓
    CROSS = "\u2717"     # ✗
    WARN = "\u26A0"      # ⚠
    ARROW = "\u2192"      # →
    BULLET = "\u2022"    # •
    DIAMOND = "\u25C6"   # ◆
    BLOCK = "\u2588"     # █

    # Arrows
    RIGHT = "\u2192"     # →
    LEFT = "\u2190"      # ←
    UP = "\u2191"        # ↑
    DOWN = "\u2193"      # ↓

    # Workflow
    PIPE = "\u2502"      # │
    ELBOW = "\u2514"     # └
    TEE = "\u251C"      # ├
    HLINE = "\u2500"     # ─
    VLINE = "\u2502"     # │
    TOP_LEFT = "\u250C"  # ┌
    TOP_RIGHT = "\u2510" # ┐
    BOT_LEFT = "\u2514"  # └
    BOT_RIGHT = "\u2518" # ┘

    # ASCII equivalents
    CHECK_ASCII = "+"
    CROSS_ASCII = "X"
    WARN_ASCII = "!"
    ARROW_ASCII = "->"
    BULLET_ASCII = "*"
    PIPE_ASCII = "|"
    HLINE_ASCII = "-"
    VLINE_ASCII = "|"

    @classmethod
    def use_unicode(cls, enabled: bool = True):
        """Toggle between Unicode and ASCII icon sets."""
        if enabled:
            cls.check = cls.CHECK
            cls.cross = cls.CROSS
            cls.warn = cls.WARN
            cls.arrow = cls.ARROW
            cls.bullet = cls.BULLET
            cls.pipe = cls.PIPE
            cls.hline = cls.HLINE
            cls.vline = cls.VLINE
        else:
            cls.check = cls.CHECK_ASCII
            cls.cross = cls.CROSS_ASCII
            cls.warn = cls.WARN_ASCII
            cls.arrow = cls.ARROW_ASCII
            cls.bullet = cls.BULLET_ASCII
            cls.pipe = cls.PIPE_ASCII
            cls.hline = cls.HLINE_ASCII
            cls.vline = cls.VLINE_ASCII


# Initialize with Unicode by default
Icons.use_unicode(True)


class Theme:
    """Terminal theme configuration for the OverCR TUI.

    Governs panel borders, padding, and overall layout style.
    All values are character-level — no pixel/terminal-size dependencies.
    """

    # Panel styles
    PANEL_BORDER_STYLE = "dim"
    PANEL_BORDER_CHAR = "\u2500"     # ─
    PANEL_CORNER_TL = "\u250C"       # ┌
    PANEL_CORNER_TR = "\u2510"       # ┐
    PANEL_CORNER_BL = "\u2514"       # └
    PANEL_CORNER_BR = "\u2518"       # ┘
    PANEL_SIDE = "\u2502"            # │
    PANEL_PADDING = 1                # Spaces inside panel border

    # Headers
    HEADER_STYLE = "bold bright_white"
    SUBHEADER_STYLE = "bold cyan"
    DIM_STYLE = "dim"
    HIGHLIGHT_STYLE = "bold yellow"

    # Table
    TABLE_HEADER_STYLE = "bold bright_white on blue"
    TABLE_ROW_EVEN = ""
    TABLE_ROW_ODD = "dim"
    TABLE_BORDER_STYLE = "blue"

    # Audit stream
    AUDIT_TIMESTAMP_STYLE = "dim cyan"
    AUDIT_ENTRY_TYPE_STYLE = "bold"
    AUDIT_DETAILS_STYLE = ""

    # Approval queue
    APPROVAL_PENDING_STYLE = "bold yellow"
    APPROVAL_APPROVED_STYLE = "green"
    APPROVAL_REJECTED_STYLE = "red"

    # Widths
    TASK_ID_WIDTH = 14
    STATE_WIDTH = 16
    SUBAGENT_WIDTH = 10
    DOMAIN_WIDTH = 18

    # Deterministic: same data always produces same output
    # No random colors, no terminal-size-dependent layout