"""
OverCR TUI — Status Badge Widget v2.2.0

Renders colored status badges/badges for task states, validation levels,
approval states, health statuses, and memory statuses.
Deterministic: same status always renders the same badge.
"""

from rich.text import Text
from typing import Optional

from tui.theme import StatusColors, Icons


class StatusBadge:
    """
    Renders a colored status badge.

    Design:
      - Same status always produces the same badge
      - No terminal-size dependency
      - Rich markup for color, plain text for fallback
    """

    # Badge format templates
    BADGE_TEMPLATE = "{icon} {label}"
    COMPACT_TEMPLATE = "{icon}{label}"
    PLAIN_TEMPLATE = "[{label}]"

    def __init__(self, use_unicode: bool = True):
        self.use_unicode = use_unicode
        if use_unicode:
            Icons.use_unicode(True)
        else:
            Icons.use_unicode(False)

    def render(
        self,
        status: str,
        category: str = "task",
        compact: bool = False,
    ) -> str:
        """
        Render a status badge with rich color markup.

        Args:
            status: The status string (e.g. "in_progress", "approved", "L3").
            category: What kind of status — "task", "workflow", "node",
                      "validation", "approval", "health", "memory".
            compact: If True, use compact template (no space between icon and label).

        Returns:
            Rich markup string like "[bright_cyan]✓ in_progress[/bright_cyan]".
        """
        color = self._get_color(status, category)
        icon = self._get_icon(status, category)
        label = status

        if compact:
            content = self.COMPACT_TEMPLATE.format(icon=icon, label=label)
        else:
            content = self.BADGE_TEMPLATE.format(icon=icon, label=label)

        return f"[{color}]{content}[/{color}]"

    def render_plain(
        self,
        status: str,
        category: str = "task",
        compact: bool = False,
    ) -> str:
        """
        Render a plain-text badge (no rich markup).

        Deterministic fallback when rich rendering is unavailable.
        """
        icon = self._get_icon(status, category, fallback=True)
        label = status

        if compact:
            return self.COMPACT_TEMPLATE.format(icon=icon, label=label)
        else:
            return self.PLAIN_TEMPLATE.format(label=label)

    def render_all_task_states(self) -> str:
        """Render a reference strip of all task state badges."""
        from runtime.task_store import VALID_STATES
        badges = []
        for state in sorted(VALID_STATES):
            badges.append(self.render(state, "task"))
        return "  ".join(badges)

    @staticmethod
    def _get_color(status: str, category: str) -> str:
        """Map (status, category) to a rich color string."""
        if category == "task":
            return StatusColors.for_task_state(status)
        elif category == "workflow":
            return StatusColors.for_workflow_state(status)
        elif category == "node":
            return StatusColors.for_node_state(status)
        elif category == "validation":
            if status.startswith("L") and len(status) == 2 and status[1].isdigit():
                return StatusColors.for_validation_level(int(status[1]))
            return StatusColors.UNKNOWN
        elif category == "approval":
            approval_colors = {
                "required": StatusColors.APPROVAL_REQUIRED,
                "granted": StatusColors.APPROVAL_GRANTED,
                "blocked": StatusColors.APPROVAL_BLOCKED,
                "not_required": StatusColors.APPROVAL_NOT_REQUIRED,
            }
            return approval_colors.get(status, StatusColors.UNKNOWN)
        elif category == "health":
            health_colors = {
                "healthy": StatusColors.HEALTHY,
                "degraded": StatusColors.DEGRADED,
                "unhealthy": StatusColors.UNHEALTHY,
            }
            return health_colors.get(status, StatusColors.UNKNOWN)
        elif category == "memory":
            return StatusColors.for_memory_status(status)
        return StatusColors.UNKNOWN

    @staticmethod
    def _get_icon(status: str, category: str, fallback: bool = False) -> str:
        """Map status to an icon character."""
        # Task states
        if category == "task":
            icons = {
                "created": "○",
                "assigned": "◎",
                "in_progress": "●",
                "response_received": "◉",
                "validation_passed": "✓",
                "validation_failed": "✗",
                "routed": "→",
                "approval_pending": "⏳",
                "approved": "✓",
                "rejected": "✗",
                "completed": "★",
                "abandoned": "⊘",
            }
            if fallback:
                icons_fallback = {
                    "completed": "+", "validation_passed": "+",
                    "approved": "+", "validation_failed": "X",
                    "rejected": "X", "abandoned": "-",
                }
                return icons_fallback.get(status, icons.get(status, "?"))
            return icons.get(status, "?")

        # Validation levels
        if category == "validation":
            return status

        # Approval
        if category == "approval":
            icons = {"required": "⏳", "granted": "✓", "blocked": "✗", "not_required": "—"}
            if fallback:
                icons = {"required": "!", "granted": "+", "blocked": "X", "not_required": "-"}
            return icons.get(status, "?")

        # Health
        if category == "health":
            icons = {"healthy": "✓", "degraded": "!", "unhealthy": "✗"}
            if fallback:
                icons = {"healthy": "+", "degraded": "!", "unhealthy": "X"}
            return icons.get(status, "?")

        # Memory
        if category == "memory":
            icons = {"active": "●", "stale": "◐", "rejected": "✗", "superseded": "→"}
            if fallback:
                icons = {"active": "+", "stale": "~", "rejected": "X", "superseded": ">"}
            return icons.get(status, "?")

        return "?"