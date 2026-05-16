"""
OverCR TUI — Packet Inspector v2.2.0

Inspects packets from task records, showing:
  - packet contents (request + response)
  - validation status
  - L1-L6 outcomes
  - provenance metadata
  - routing metadata
  - rejection reasons if applicable

Reads from filesystem state only. Never modifies packets.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional

from rich.console import Console

from tui.theme import Theme, StatusColors, Icons
from tui.widgets.status_badge import StatusBadge


# Validation level descriptions (from validate_packet.py spec)
VALIDATION_LEVELS = {
    1: "Structural Integrity — valid JSON, required top-level keys",
    2: "Schema Compliance — correct value types and formats",
    3: "Subagent Consistency — source packet_type matches assigned subagent",
    4: "Operational Policy — outbound contact, PII, constraints",
    5: "Governance Boundary — approval_required, direct routing, forbidden actions",
    6: "Audit Completeness — full audit trail, provenance, traceability",
}


class PacketInspector:
    """
    Inspects and renders packet information from task records.

    Governance: Read-only observatory. Never modifies packets or task state.
    """

    def __init__(self, root: str, console: Optional[Console] = None):
        self.root = Path(root)
        self.console = console or Console()
        self.badge = StatusBadge(use_unicode=True)
        self._tasks_dir = self.root / "orchestration" / "tasks"

    def render_request_packet(self, task_id: str) -> str:
        """
        Render the request packet for a task.

        Args:
            task_id: The task ID to inspect.

        Returns:
            Rich-formatted packet view.
        """
        task = self._load_task(task_id)
        if task is None:
            return f"[red]{Icons.cross} Task {task_id} not found[/red]"

        request = task.get("request_packet")
        if request is None:
            return f"[dim]{Icons.bullet} No request packet for {task_id}[/dim]"

        lines = []
        lines.append(f"[bold]Request Packet — {task_id}[/bold]")
        lines.append("")

        # Core fields
        lines.append(f"  Task ID:       [bold]{request.get('task_id', '?')}[/bold]")
        lines.append(f"  Subagent:      [cyan]{request.get('assigned_subagent', '?')}[/cyan]")
        lines.append(f"  Domain:        {request.get('domain', '?')}")
        lines.append(f"  Packet Type:   {request.get('required_packet_type', '?')}")
        lines.append(f"  Created:       {request.get('created_at', '?')}")

        # Instruction (truncated)
        instruction = request.get("instruction", "")
        if instruction:
            display = instruction[:200] + ("..." if len(instruction) > 200 else "")
            lines.append(f"  Instruction:   {display}")

        # Constraints
        constraints = request.get("constraints", [])
        if constraints:
            lines.append(f"  Constraints:")
            for c in constraints[:5]:
                lines.append(f"    • {c}")

        # Input context
        input_ctx = request.get("input_context", {})
        if input_ctx:
            lines.append(f"  Input Context: {len(input_ctx)} key(s)")
            for key in list(input_ctx.keys())[:8]:
                val = input_ctx[key]
                if isinstance(val, str) and len(val) > 80:
                    val = val[:80] + "..."
                elif isinstance(val, (dict, list)):
                    val = f"<{type(val).__name__} with {len(val)} entries>"
                lines.append(f"    {key}: {val}")

        # Provenance
        lines.append("")
        lines.append(f"[dim]Provenance: OverCR runtime → {request.get('assigned_subagent', '?')}[/dim]")

        return "\n".join(lines)

    def render_response_packet(self, task_id: str) -> str:
        """
        Render the response packet for a task.

        Args:
            task_id: The task ID to inspect.

        Returns:
            Rich-formatted response packet view.
        """
        task = self._load_task(task_id)
        if task is None:
            return f"[red]{Icons.cross} Task {task_id} not found[/red]"

        response = task.get("response_packet")
        if response is None:
            return f"[dim]{Icons.bullet} No response packet for {task_id}[/dim]"

        lines = []
        lines.append(f"[bold]Response Packet — {task_id}[/bold]")
        lines.append("")

        # Core fields
        pkt_type = response.get("packet_type", "?")
        source = response.get("source", "?")
        target = response.get("target", "?")
        version = response.get("version", "?")
        summary = response.get("summary", "")

        lines.append(f"  Packet Type:  {pkt_type}")
        lines.append(f"  Source:        [cyan]{source}[/cyan]")
        lines.append(f"  Target:        {target}")
        lines.append(f"  Version:       {version}")
        lines.append(f"  Summary:       {summary[:200]}")

        # Timestamp
        timestamp = response.get("timestamp", "?")
        lines.append(f"  Timestamp:     {timestamp}")

        # Approval required flag (key governance field)
        approval_req = response.get("approval_required")
        if approval_req is not None:
            color = "bright_yellow" if approval_req else "dim green"
            lines.append(f"  Approval Required: [{color}]{approval_req}[/{color}]")

        # Task ID from packet (provenance check)
        pkt_task_id = response.get("task_id", "?")
        lines.append(f"  Task ID:       {pkt_task_id}")

        # Next steps
        next_steps = response.get("next_steps_recommendation", "")
        if next_steps:
            lines.append(f"  Next Steps:   {next_steps[:200]}")

        return "\n".join(lines)

    def render_validation_status(self, task_id: str) -> str:
        """
        Render the L1-L6 validation outcome for a task.

        Args:
            task_id: The task ID to inspect.

        Returns:
            Rich-formatted validation status view.
        """
        task = self._load_task(task_id)
        if task is None:
            return f"[red]{Icons.cross} Task {task_id} not found[/red]"

        validation = task.get("validation_result")
        if validation is None:
            return f"[dim]{Icons.bullet} No validation result for {task_id}[/dim]"

        lines = []
        lines.append(f"[bold]Validation Status — {task_id}[/bold]")
        lines.append("")

        valid = validation.get("valid", False)
        v_icon = Icons.check if valid else Icons.cross
        v_color = "bright_green" if valid else "bright_red"
        lines.append(f"  {v_icon} Overall: [{v_color}]{'PASS' if valid else 'FAIL'}[/{v_color}]")

        # Errors
        errors = validation.get("errors", [])
        if errors:
            lines.append("")
            lines.append(f"  [bold bright_red]Errors ({len(errors)}):[/bold bright_red]")
            for err in errors:
                lines.append(f"    [bright_red]{Icons.cross} {err}[/bright_red]")

        # Warnings
        warnings = validation.get("warnings", [])
        if warnings:
            lines.append("")
            lines.append(f"  [yellow]Warnings ({len(warnings)}):[/yellow]")
            for warn in warnings:
                lines.append(f"    [yellow]{Icons.warn} {warn}[/yellow]")

        # L1-L6 detail
        level_results = validation.get("levels", {})
        if level_results:
            lines.append("")
            lines.append("[bold]Level-by-Level:[/bold]")
            for level in range(1, 7):
                level_key = f"L{level}"
                level_data = level_results.get(level_key, {})
                passed = level_data.get("valid", None)
                desc = VALIDATION_LEVELS.get(level, "")
                if passed is True:
                    lines.append(f"  [{StatusColors.for_validation_level(level)}]L{level} PASS[/{StatusColors.for_validation_level(level)}] {desc}")
                elif passed is False:
                    level_errors = level_data.get("errors", [])
                    err_count = len(level_errors) if level_errors else "?"
                    lines.append(f"  [bright_red]L{level} FAIL ({err_count} errors)[/bright_red] {desc}")
                else:
                    lines.append(f"  [dim]L{level} N/A[/dim] {desc}")

        return "\n".join(lines)

    def render_routing_metadata(self, task_id: str) -> str:
        """Render routing decision metadata for a task."""
        task = self._load_task(task_id)
        if task is None:
            return f"[red]{Icons.cross} Task {task_id} not found[/red]"

        routing = task.get("routing_decision")
        if routing is None:
            return f"[dim]{Icons.bullet} No routing decision for {task_id}[/dim]"

        lines = []
        lines.append(f"[bold]Routing Decision — {task_id}[/bold]")
        lines.append(f"  Target: [blue]{routing.get('routing_target', '?')}[/blue]")
        lines.append(f"  Reason: {routing.get('reason', '?')}")
        downstream = routing.get("creates_downstream_task", False)
        lines.append(f"  Creates downstream: {'Yes' if downstream else 'No'}")

        return "\n".join(lines)

    def render_rejection_reason(self, task_id: str) -> str:
        """Render rejection reason for a rejected task."""
        task = self._load_task(task_id)
        if task is None:
            return f"[red]{Icons.cross} Task {task_id} not found[/red]"

        approval = task.get("operator_approval")
        state = task.get("state", "")

        if state != "rejected" and (approval is None or approval.get("decision") != "rejected"):
            return f"[dim]{Icons.bullet} Task {task_id} is not rejected[/dim]"

        lines = []
        lines.append(f"[bold]Rejection — {task_id}[/bold]")

        if approval:
            lines.append(f"  Decision: [red]rejected[/red]")
            lines.append(f"  Operator: {approval.get('operator', '?')}")
            lines.append(f"  Reason: {approval.get('reason', 'No reason given')}")
            lines.append(f"  Timestamp: {approval.get('timestamp', '?')}")

        # Also show validation errors if any
        validation = task.get("validation_result")
        if validation and not validation.get("valid", True):
            lines.append("")
            lines.append("  [bold]Validation errors at time of rejection:[/bold]")
            for err in validation.get("errors", []):
                lines.append(f"    [red]{Icons.cross} {err}[/red]")

        return "\n".join(lines)

    def render_plain(self, task_id: str) -> str:
        """Render full packet info as plain text (deterministic fallback)."""
        task = self._load_task(task_id)
        if task is None:
            return f"Task {task_id} not found"

        lines = [f"=== Packet Inspector: {task_id} ==="]
        lines.append(f"State: {task.get('state', '?')}")
        lines.append(f"Subagent: {task.get('assigned_subagent', '?')}")

        request = task.get("request_packet", {})
        if request:
            lines.append(f"\n--- Request ---")
            lines.append(f"  packet_type: {request.get('required_packet_type', '?')}")
            lines.append(f"  domain: {request.get('domain', '?')}")
            lines.append(f"  instruction: {str(request.get('instruction', ''))[:100]}")

        response = task.get("response_packet")
        if response:
            lines.append(f"\n--- Response ---")
            lines.append(f"  packet_type: {response.get('packet_type', '?')}")
            lines.append(f"  source: {response.get('source', '?')}")
            lines.append(f"  summary: {str(response.get('summary', ''))[:100]}")

        validation = task.get("validation_result")
        if validation:
            lines.append(f"\n--- Validation ---")
            lines.append(f"  valid: {validation.get('valid', '?')}")
            lines.append(f"  errors: {len(validation.get('errors', []))}")
            lines.append(f"  warnings: {len(validation.get('warnings', []))}")

        return "\n".join(lines)

    def _load_task(self, task_id: str) -> Optional[Dict]:
        """Load a task record from filesystem."""
        path = self._tasks_dir / f"{task_id}.json"
        if not path.exists():
            return None
        try:
            with open(path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None