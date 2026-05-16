"""
OverCR TUI — Workflow View v2.2.0

Renders workflow DAG visualization using ASCII/text characters.
Reads WorkflowGraph from filesystem or directly from runtime data.
Never modifies workflow state — render-only observatory.

Shows:
  - DAG visualization (ASCII/text)
  - Node states (mapped from task states)
  - Blocked nodes (approval_pending)
  - Approval-gated nodes
  - Deterministic fallback markers
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from rich.console import Console
from rich.text import Text

from tui.theme import Theme, StatusColors, Icons
from tui.widgets.status_badge import StatusBadge


class WorkflowView:
    """
    Renders workflow DAG visualization from filesystem state.

    Governance: Read-only. Never modifies workflow or task state.
    Renders what exists on disk — the canonical truth.
    """

    def __init__(self, root: str, console: Optional[Console] = None):
        self.root = Path(root)
        self.console = console or Console()
        self.badge = StatusBadge(use_unicode=True)

    def render_dag(
        self,
        graph_data: Dict,
        node_states: Optional[Dict[str, str]] = None,
        show_approval_gates: bool = True,
        show_fallback_markers: bool = True,
    ) -> str:
        """
        Render a workflow DAG as ASCII/text tree.

        Args:
            graph_data: Serialized WorkflowGraph (from graph.to_dict()).
            node_states: Optional mapping of node_id -> execution state.
            show_approval_gates: Whether to highlight approval-gated nodes.
            show_fallback_markers: Whether to show deterministic fallback markers.

        Returns:
            Rich-formatted DAG visualization string.
        """
        nodes = graph_data.get("nodes", {})
        edges = graph_data.get("edges", {})
        name = graph_data.get("name", "unnamed")

        if not nodes:
            return f"[dim]{Icons.bullet} No workflow nodes found[/dim]"

        lines = []
        lines.append(f"[bold]Workflow: {name}[/bold]")
        lines.append("")

        # Build adjacency list (parent -> children)
        children: Dict[str, List[str]] = {}
        for edge_data in edges.values():
            src = edge_data.get("source_node_id", "")
            tgt = edge_data.get("target_node_id", "")
            if src not in children:
                children[src] = []
            children[src].append(tgt)

        # Find root nodes (no incoming edges)
        all_targets = set()
        for edge_data in edges.values():
            all_targets.add(edge_data.get("target_node_id", ""))
        roots = [nid for nid in nodes if nid not in all_targets]

        # Topological order for display
        visited: Set[str] = set()
        order = []
        stack = list(roots)
        while stack:
            nid = stack.pop(0)
            if nid in visited:
                continue
            visited.add(nid)
            order.append(nid)
            for child in children.get(nid, []):
                if child not in visited:
                    stack.append(child)
        # Add any remaining nodes not reached from roots
        for nid in nodes:
            if nid not in visited:
                order.append(nid)

        # Render tree
        node_info = {}
        for nid, ndata in nodes.items():
            subagent = ndata.get("subagent", "?")
            pkt_type = ndata.get("packet_type", "?")
            approval = ndata.get("approval_policy", "never")
            desc = ndata.get("description", "")
            state = (node_states or {}).get(nid, "pending")
            node_info[nid] = {
                "subagent": subagent,
                "packet_type": pkt_type,
                "approval": approval,
                "description": desc,
                "state": state,
            }

        for nid in order:
            info = node_info.get(nid, {})
            subagent = info.get("subagent", "?")
            pkt_type = info.get("packet_type", "?")
            approval = info.get("approval", "never")
            state = info.get("state", "pending")
            desc = info.get("description", "")

            # State badge
            state_badge = self.badge.render(state, "node", compact=True)

            # Approval gate marker
            gate_marker = ""
            if show_approval_gates and approval in ("always", "on_failure"):
                gate_marker = f" [bright_yellow]⏳ approval:{approval}[/bright_yellow]"

            # Fallback marker
            fallback_marker = ""
            if show_fallback_markers and approval == "never":
                fallback_marker = " [dim]↻ deterministic[/dim]"

            # Has children?
            child_count = len(children.get(nid, []))
            child_indicator = f" → {child_count} downstream" if child_count > 0 else " (leaf)"

            lines.append(
                f"  {state_badge} [cyan]{subagent}[/cyan] "
                f"{nid} ({pkt_type}){gate_marker}{fallback_marker}{child_indicator}"
            )
            if desc:
                lines.append(f"      [dim]{desc}[/dim]")

        # ── Edge summary ──
        if edges:
            lines.append("")
            lines.append("[bold]Edges:[/bold]")
            for eid, edata in edges.items():
                src = edata.get("source_node_id", "?")
                tgt = edata.get("target_node_id", "?")
                pkt_types = edata.get("accepted_packet_types", [])
                gate = edata.get("approval_gate", "none")
                gate_str = f" [bright_yellow]gate:{gate}[/bright_yellow]" if gate and gate != "none" else ""
                pkt_str = ", ".join(pkt_types[:3])
                lines.append(
                    f"  {src} → {tgt} [{pkt_str}]{gate_str}"
                )

        # ── Blocked nodes ──
        if node_states:
            blocked = [
                nid for nid, st in node_states.items()
                if st == "waiting_approval" or st == "approval_pending"
            ]
            if blocked:
                lines.append("")
                lines.append("[bold bright_yellow]Blocked nodes (awaiting approval):[/bold bright_yellow]")
                for nid in blocked:
                    info = node_info.get(nid, {})
                    lines.append(f"  {Icons.warn} {nid} ({info.get('subagent', '?')})")

        return "\n".join(lines)

    def render_dag_plain(
        self,
        graph_data: Dict,
        node_states: Optional[Dict[str, str]] = None,
    ) -> str:
        """Render DAG as plain text (deterministic fallback)."""
        nodes = graph_data.get("nodes", {})
        edges = graph_data.get("edges", {})
        name = graph_data.get("name", "unnamed")

        if not nodes:
            return "No workflow nodes found"

        lines = [f"Workflow: {name}", ""]

        # Build children
        children: Dict[str, List[str]] = {}
        for edata in edges.values():
            src = edata.get("source_node_id", "")
            tgt = edata.get("target_node_id", "")
            if src not in children:
                children[src] = []
            children[src].append(tgt)

        for nid, ndata in nodes.items():
            subagent = ndata.get("subagent", "?")
            pkt_type = ndata.get("packet_type", "?")
            approval = ndata.get("approval_policy", "never")
            state = (node_states or {}).get(nid, "pending")
            lines.append(f"  [{state}] {subagent}/{nid} ({pkt_type}) gate={approval}")

        if edges:
            lines.append("")
            lines.append("Edges:")
            for eid, edata in edges.items():
                src = edata.get("source_node_id", "?")
                tgt = edata.get("target_node_id", "?")
                lines.append(f"  {src} -> {tgt}")

        return "\n".join(lines)

    def render_node_states_table(self, graph_data: Dict, node_states: Dict[str, str]) -> str:
        """
        Render a summary table of node execution states.

        Args:
            graph_data: Serialized WorkflowGraph.
            node_states: Mapping of node_id -> state.

        Returns:
            Rich-formatted table string.
        """
        nodes = graph_data.get("nodes", {})
        if not nodes:
            return "[dim]No nodes[/dim]"

        lines = []
        lines.append("[bold]Node States:[/bold]")
        lines.append(f"  {'Node':<20} {'Subagent':<10} {'State':<18} {'Approval':<12}")
        lines.append(f"  {'-'*20} {'-'*10} {'-'*18} {'-'*12}")

        for nid, ndata in nodes.items():
            subagent = ndata.get("subagent", "?")
            approval = ndata.get("approval_policy", "?")
            state = node_states.get(nid, "pending")
            state_badge = self.badge.render(state, "node", compact=True)
            lines.append(f"  {nid:<20} {subagent:<10} {state_badge:<30} {approval:<12}")

        return "\n".join(lines)