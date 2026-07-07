"""
OverCR Semantic Memory — Symbolic Memory Canvas v2.2.0

Mermaid-based symbolic memory for short-term context compression.

Inspired by TencentDB Agent Memory's symbolic memory pillar: verbose tool
logs are offloaded to disk, and a compact Mermaid graph replaces them in
the agent's context window. Each node carries a `node_id` that traces back
to the full raw text on disk.

Design principles (inherited from OverCR memory layer):
  1. Filesystem-first — all state on disk, no in-memory cache
  2. Advisory only — canvas is a context aid, not canonical truth
  3. Full traceability — every symbol drills back to raw evidence
  4. No lossy compression — raw logs are offloaded, never discarded
  5. Human-readable — Mermaid syntax, plain Markdown refs
  6. Stdlib only — no external dependencies

Storage layout (per session):
  <root>/canvas/
    <session_id>/
      graph.mmd          — Mermaid graph definition (the compact canvas)
      refs/
        <node_id>.md     — Full raw text for each node (drill-down target)
      index.jsonl        — Append-only audit log of canvas mutations
      state.json         — Current canvas state (nodes, edges, metadata)

Usage:
    from memory.memory_canvas import MemoryCanvas

    canvas = MemoryCanvas(root="/path/to/overcr", session_id="sess-001")

    # Agent runs a tool, gets verbose output
    node_id = canvas.add_node(
        label="search_api_docs",
        node_type="tool_call",
        detail="Searched API docs for 'rate limiting'",
        raw_text="<full 50KB tool output here>",
    )

    # Agent needs the compact representation
    mermaid = canvas.render()  # injects into context (~hundreds of tokens)

    # Agent needs to verify a detail
    raw = canvas.retrieve_raw(node_id)  # drills back to full text
"""

import json
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# Valid node types for the canvas
VALID_NODE_TYPES = {
    "task_start",
    "tool_call",
    "tool_result",
    "decision",
    "error",
    "milestone",
    "task_end",
}

# Valid edge types (state transitions)
VALID_EDGE_TYPES = {
    "next",        # sequential flow
    "retry",       # error recovery
    "branch",      # conditional split
    "merge",       # conditional rejoin
    "depends_on",  # dependency
}

# Node ID pattern: n- + 8 hex chars
NODE_ID_PATTERN = re.compile(r"^n-[a-z0-9]{8}$")


class CanvasNode:
    """
    A single node in the symbolic memory canvas.

    Each node is a compact symbol in the Mermaid graph. The full verbose
    content is offloaded to refs/<node_id>.md on disk.
    """

    def __init__(self, data: dict):
        self._data = data

    @classmethod
    def create(
        cls,
        label: str,
        node_type: str,
        detail: str,
        node_id: Optional[str] = None,
    ) -> "CanvasNode":
        """
        Create a new canvas node.

        Args:
            label: Short human-readable label (shown in Mermaid graph).
            node_type: One of VALID_NODE_TYPES.
            detail: One-line summary of what happened (shown in Mermaid tooltip).
            node_id: Optional explicit ID. Auto-generated if omitted.
        """
        if node_type not in VALID_NODE_TYPES:
            raise ValueError(f"Invalid node_type: {node_type}. Valid: {VALID_NODE_TYPES}")

        if not label or len(label) > 128:
            raise ValueError(f"Label must be 1-128 chars, got {len(label) if label else 0}")

        if not detail or len(detail) > 512:
            raise ValueError(f"Detail must be 1-512 chars, got {len(detail) if detail else 0}")

        nid = node_id or cls._generate_id()
        if not NODE_ID_PATTERN.match(nid):
            raise ValueError(f"Invalid node_id format: {nid}. Expected: n-xxxxxxxx")

        now = datetime.now(timezone.utc).isoformat()
        data = {
            "node_id": nid,
            "label": label,
            "node_type": node_type,
            "detail": detail,
            "created_at": now,
            "updated_at": now,
            "status": "active",  # active | offloaded | archived
        }
        return cls(data)

    @classmethod
    def from_dict(cls, data: dict) -> "CanvasNode":
        cls._validate(data)
        return cls(data)

    # ── Properties ──

    @property
    def node_id(self) -> str:
        return self._data["node_id"]

    @property
    def label(self) -> str:
        return self._data["label"]

    @property
    def node_type(self) -> str:
        return self._data["node_type"]

    @property
    def detail(self) -> str:
        return self._data["detail"]

    @property
    def created_at(self) -> str:
        return self._data["created_at"]

    @property
    def updated_at(self) -> str:
        return self._data["updated_at"]

    @property
    def status(self) -> str:
        return self._data["status"]

    @property
    def ref_path(self) -> str:
        """Relative path to the raw text file for this node."""
        return f"refs/{self.node_id}.md"

    # ── Mutations ──

    def offload(self) -> "CanvasNode":
        """Mark this node as offloaded (raw text is on disk, not in context)."""
        self._data["status"] = "offloaded"
        self._data["updated_at"] = datetime.now(timezone.utc).isoformat()
        return self

    def archive(self) -> "CanvasNode":
        """Mark this node as archived (no longer relevant to active context)."""
        self._data["status"] = "archived"
        self._data["updated_at"] = datetime.now(timezone.utc).isoformat()
        return self

    def reactivate(self) -> "CanvasNode":
        """Reactivate an archived node."""
        if self._data["status"] != "archived":
            raise ValueError(f"Can only reactivate archived nodes, got {self._data['status']}")
        self._data["status"] = "active"
        self._data["updated_at"] = datetime.now(timezone.utc).isoformat()
        return self

    # ── Serialization ──

    def to_dict(self) -> dict:
        return json.loads(json.dumps(self._data))

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self._data, indent=indent, ensure_ascii=False)

    # ── Internal ──

    @staticmethod
    def _generate_id() -> str:
        return f"n-{secrets.token_hex(4)}"

    @staticmethod
    def _validate(data: dict):
        required = ["node_id", "label", "node_type", "detail", "created_at", "updated_at", "status"]
        for field in required:
            if field not in data:
                raise ValueError(f"Missing required field: {field}")
        if not NODE_ID_PATTERN.match(data["node_id"]):
            raise ValueError(f"Invalid node_id format: {data['node_id']}")
        if data["node_type"] not in VALID_NODE_TYPES:
            raise ValueError(f"Invalid node_type: {data['node_type']}")
        if data["status"] not in ("active", "offloaded", "archived"):
            raise ValueError(f"Invalid status: {data['status']}")

    def __repr__(self):
        return f"CanvasNode(id={self.node_id}, type={self.node_type}, label={self.label[:40]}...)"


class CanvasEdge:
    """
    A directed edge between two canvas nodes, representing a state transition.
    """

    def __init__(self, data: dict):
        self._data = data

    @classmethod
    def create(
        cls,
        from_id: str,
        to_id: str,
        edge_type: str = "next",
        label: Optional[str] = None,
    ) -> "CanvasEdge":
        if not NODE_ID_PATTERN.match(from_id):
            raise ValueError(f"Invalid from_id: {from_id}")
        if not NODE_ID_PATTERN.match(to_id):
            raise ValueError(f"Invalid to_id: {to_id}")
        if edge_type not in VALID_EDGE_TYPES:
            raise ValueError(f"Invalid edge_type: {edge_type}. Valid: {VALID_EDGE_TYPES}")

        data = {
            "from": from_id,
            "to": to_id,
            "edge_type": edge_type,
            "label": label,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        return cls(data)

    @classmethod
    def from_dict(cls, data: dict) -> "CanvasEdge":
        cls._validate(data)
        return cls(data)

    @property
    def from_id(self) -> str:
        return self._data["from"]

    @property
    def to_id(self) -> str:
        return self._data["to"]

    @property
    def edge_type(self) -> str:
        return self._data["edge_type"]

    @property
    def label(self) -> Optional[str]:
        return self._data.get("label")

    def to_dict(self) -> dict:
        return json.loads(json.dumps(self._data))

    @staticmethod
    def _validate(data: dict):
        required = ["from", "to", "edge_type"]
        for field in required:
            if field not in data:
                raise ValueError(f"Missing required field: {field}")
        if not NODE_ID_PATTERN.match(data["from"]):
            raise ValueError(f"Invalid from_id: {data['from']}")
        if not NODE_ID_PATTERN.match(data["to"]):
            raise ValueError(f"Invalid to_id: {data['to']}")
        if data["edge_type"] not in VALID_EDGE_TYPES:
            raise ValueError(f"Invalid edge_type: {data['edge_type']}")

    def __repr__(self):
        return f"CanvasEdge({self.from_id} --{self.edge_type}--> {self.to_id})"


class MemoryCanvas:
    """
    Symbolic memory canvas for a single session.

    Manages a Mermaid graph of task state transitions, offloading verbose
    tool output to disk refs and keeping only the compact graph in context.

    The canvas is advisory — it's a context aid for the agent, not
    canonical truth. The raw refs on disk are the evidence layer.
    """

    def __init__(self, root: str, session_id: str):
        """
        Args:
            root: Path to the OverCR core directory (contains canvas/).
            session_id: Unique session identifier. Each session gets its
                        own canvas directory.
        """
        if not session_id or len(session_id) > 128:
            raise ValueError("session_id must be 1-128 chars")

        self.root = Path(root)
        self.session_id = session_id
        self.canvas_dir = self.root / "canvas" / session_id
        self.refs_dir = self.canvas_dir / "refs"
        self.graph_path = self.canvas_dir / "graph.mmd"
        self.state_path = self.canvas_dir / "state.json"
        self.index_path = self.canvas_dir / "index.jsonl"
        self._ensure_dirs()

    def _ensure_dirs(self):
        self.canvas_dir.mkdir(parents=True, exist_ok=True)
        self.refs_dir.mkdir(parents=True, exist_ok=True)

    # ── Node Operations ──────────────────────────────────────

    def add_node(
        self,
        label: str,
        node_type: str,
        detail: str,
        raw_text: Optional[str] = None,
        node_id: Optional[str] = None,
    ) -> CanvasNode:
        """
        Add a node to the canvas and optionally offload raw text to disk.

        If raw_text is provided, it's written to refs/<node_id>.md and the
        node is marked as 'offloaded'. If no raw_text, the node stays 'active'
        (the detail string is all that exists — no drill-down target).

        Args:
            label: Short label for the Mermaid graph.
            node_type: One of VALID_NODE_TYPES.
            detail: One-line summary (Mermaid tooltip).
            raw_text: Full verbose text to offload (optional).
            node_id: Explicit ID (auto-generated if omitted).

        Returns:
            The created CanvasNode.
        """
        node = CanvasNode.create(label=label, node_type=node_type, detail=detail, node_id=node_id)

        if raw_text:
            self._write_ref(node.node_id, raw_text)
            node.offload()

        self._save_node(node)
        self._append_index("node_added", node_id=node.node_id, node_type=node_type)
        self._regenerate_graph()
        return node

    def get_node(self, node_id: str) -> Optional[CanvasNode]:
        """Retrieve a node by ID. Returns None if not found."""
        if not NODE_ID_PATTERN.match(node_id):
            return None
        state = self._load_state()
        nodes = state.get("nodes", {})
        if node_id not in nodes:
            return None
        return CanvasNode.from_dict(nodes[node_id])

    def retrieve_raw(self, node_id: str) -> Optional[str]:
        """
        Drill down: retrieve the full raw text for a node.

        This is the core traceability mechanism. The agent sees the compact
        Mermaid graph in context, and uses node_id to retrieve the full
        verbose text when it needs to verify a detail.

        Args:
            node_id: The node ID from the Mermaid graph.

        Returns:
            The full raw text, or None if no ref exists.
        """
        if not NODE_ID_PATTERN.match(node_id):
            return None
        ref_path = self.refs_dir / f"{node_id}.md"
        if not ref_path.exists():
            return None
        with open(ref_path, "r", encoding="utf-8") as f:
            return f.read()

    def list_nodes(self, status_filter: Optional[str] = None) -> list[CanvasNode]:
        """List all nodes, optionally filtered by status."""
        state = self._load_state()
        nodes = []
        for nid, data in state.get("nodes", {}).items():
            node = CanvasNode.from_dict(data)
            if status_filter and node.status != status_filter:
                continue
            nodes.append(node)
        nodes.sort(key=lambda n: n.created_at)
        return nodes

    def archive_node(self, node_id: str) -> Optional[CanvasNode]:
        """Archive a node (no longer relevant to active context)."""
        node = self.get_node(node_id)
        if not node:
            return None
        node.archive()
        self._save_node(node)
        self._append_index("node_archived", node_id=node_id)
        self._regenerate_graph()
        return node

    def reactivate_node(self, node_id: str) -> Optional[CanvasNode]:
        """Reactivate an archived node."""
        node = self.get_node(node_id)
        if not node:
            return None
        node.reactivate()
        self._save_node(node)
        self._append_index("node_reactivated", node_id=node_id)
        self._regenerate_graph()
        return node

    # ── Edge Operations ──────────────────────────────────────

    def add_edge(
        self,
        from_id: str,
        to_id: str,
        edge_type: str = "next",
        label: Optional[str] = None,
    ) -> CanvasEdge:
        """
        Add a directed edge between two nodes (a state transition).

        Both nodes must exist. Self-loops are rejected.

        Args:
            from_id: Source node ID.
            to_id: Target node ID.
            edge_type: One of VALID_EDGE_TYPES.
            label: Optional edge label (shown in Mermaid).

        Returns:
            The created CanvasEdge.
        """
        if from_id == to_id:
            raise ValueError("Self-loops not allowed")

        # Both nodes must exist
        if not self.get_node(from_id):
            raise ValueError(f"Source node not found: {from_id}")
        if not self.get_node(to_id):
            raise ValueError(f"Target node not found: {to_id}")

        edge = CanvasEdge.create(from_id, to_id, edge_type, label)
        self._save_edge(edge)
        self._append_index("edge_added", from_id=from_id, to_id=to_id, edge_type=edge_type)
        self._regenerate_graph()
        return edge

    def list_edges(self) -> list[CanvasEdge]:
        """List all edges in the canvas."""
        state = self._load_state()
        edges = []
        for edge_data in state.get("edges", []):
            edges.append(CanvasEdge.from_dict(edge_data))
        return edges

    def remove_edge(self, from_id: str, to_id: str) -> bool:
        """Remove an edge. Returns True if removed, False if not found."""
        state = self._load_state()
        edges = state.get("edges", [])
        original_len = len(edges)
        state["edges"] = [
            e for e in edges
            if not (e["from"] == from_id and e["to"] == to_id)
        ]
        if len(state["edges"]) < original_len:
            self._write_state(state)
            self._append_index("edge_removed", from_id=from_id, to_id=to_id)
            self._regenerate_graph()
            return True
        return False

    # ── Rendering ────────────────────────────────────────────

    def render(self, include_archived: bool = False) -> str:
        """
        Render the canvas as a Mermaid graph definition.

        This is the compact representation that goes into the agent's context.
        Typically a few hundred tokens for a session with dozens of nodes.

        Args:
            include_archived: If True, include archived nodes (dimmed).

        Returns:
            Mermaid graph definition string.
        """
        nodes = self.list_nodes()
        edges = self.list_edges()

        lines = ["graph LR"]

        # Node definitions
        for node in nodes:
            if not include_archived and node.status == "archived":
                continue

            # Mermaid node syntax: node_id["label<br/>detail"]
            # Escape quotes in label/detail
            label = _escape_mermaid(node.label)
            detail = _escape_mermaid(node.detail)
            mermaid_id = node.node_id.replace("-", "_")

            if node.status == "offloaded":
                lines.append(
                    f'    {mermaid_id}["{label}<br/><small>{detail}</small><br/><i>ref: {node.node_id}</i>"]'
                )
            elif node.status == "archived":
                lines.append(
                    f'    {mermaid_id}["{label}<br/><small>{detail}</small>"]:::archived'
                )
            else:
                lines.append(
                    f'    {mermaid_id}["{label}<br/><small>{detail}</small>"]'
                )

        # Edge definitions
        for edge in edges:
            from_node = self.get_node(edge.from_id)
            to_node = self.get_node(edge.to_id)
            if not include_archived:
                if (from_node and from_node.status == "archived") or \
                   (to_node and to_node.status == "archived"):
                    continue

            from_mid = edge.from_id.replace("-", "_")
            to_mid = edge.to_id.replace("-", "_")

            if edge.label:
                label = _escape_mermaid(edge.label)
                if edge.edge_type == "retry":
                    lines.append(f'    {from_mid} -. "{label}" .-> {to_mid}')
                elif edge.edge_type == "branch":
                    lines.append(f'    {from_mid} -->|"{label}"| {to_mid}')
                else:
                    lines.append(f'    {from_mid} -->|{edge.edge_type}| {to_mid}')
            else:
                if edge.edge_type == "retry":
                    lines.append(f'    {from_mid} -. .-> {to_mid}')
                elif edge.edge_type == "branch":
                    lines.append(f'    {from_mid} --> {to_mid}')
                else:
                    lines.append(f'    {from_mid} --> {to_mid}')

        # Styling
        lines.append("")
        lines.append("    classDef archived fill:#444,stroke:#666,color:#888,stroke-dasharray: 5 5")

        return "\n".join(lines)

    def render_compact(self) -> str:
        """
        Render an ultra-compact summary for tight context budgets.

        Returns just node IDs and their labels, one per line.
        No Mermaid syntax — just a flat list with edge annotations.

        Returns:
            Compact text summary string.
        """
        nodes = self.list_nodes()
        edges = self.list_edges()

        lines = []
        for node in nodes:
            if node.status == "archived":
                continue
            marker = " [offloaded]" if node.status == "offloaded" else ""
            lines.append(f"{node.node_id}: {node.label}{marker}")

        if edges:
            lines.append("")
            for edge in edges:
                from_node = self.get_node(edge.from_id)
                to_node = self.get_node(edge.to_id)
                if from_node and to_node:
                    if from_node.status == "archived" or to_node.status == "archived":
                        continue
                    l = f" ({edge.label})" if edge.label else ""
                    lines.append(f"  {edge.from_id} --{edge.edge_type}{l}--> {edge.to_id}")

        return "\n".join(lines)

    def context_size_estimate(self) -> dict:
        """
        Estimate token savings from using the canvas vs. raw text.

        Returns:
            Dict with: full_raw_chars, canvas_chars, estimated_savings_pct,
            node_count, offloaded_count
        """
        nodes = self.list_nodes()
        full_raw_chars = 0
        canvas_chars = len(self.render())
        offloaded_count = 0

        for node in nodes:
            if node.status == "offloaded":
                raw = self.retrieve_raw(node.node_id) or ""
                full_raw_chars += len(raw)
                offloaded_count += 1
            # The detail string is always in the canvas
            full_raw_chars += len(node.detail)

        if full_raw_chars > 0:
            savings = round((1 - canvas_chars / full_raw_chars) * 100, 1)
        else:
            savings = 0.0

        return {
            "full_raw_chars": full_raw_chars,
            "canvas_chars": canvas_chars,
            "estimated_savings_pct": savings,
            "node_count": len(nodes),
            "offloaded_count": offloaded_count,
        }

    # ── Session Management ──────────────────────────────────

    def clear(self, keep_archived: bool = False):
        """
        Clear the canvas. Archived nodes are kept by default.

        Args:
            keep_archived: If True, keep archived nodes and their refs.
                          If False, wipe everything.
        """
        if not keep_archived:
            # Nuke everything
            import shutil
            shutil.rmtree(self.canvas_dir, ignore_errors=True)
            self._ensure_dirs()
            self._append_index("canvas_cleared")
            return

        # Keep archived, remove active/offloaded
        state = self._load_state()
        new_nodes = {}
        for nid, data in state.get("nodes", {}).items():
            if data.get("status") == "archived":
                new_nodes[nid] = data
        state["nodes"] = new_nodes
        state["edges"] = []  # Clear edges (archived nodes don't need them)
        self._write_state(state)
        self._regenerate_graph()
        self._append_index("canvas_cleared_keep_archived")

    # ── Internal Persistence ─────────────────────────────────

    def _save_node(self, node: CanvasNode):
        state = self._load_state()
        state.setdefault("nodes", {})[node.node_id] = node.to_dict()
        self._write_state(state)

    def _save_edge(self, edge: CanvasEdge):
        state = self._load_state()
        edges = state.setdefault("edges", [])
        # Avoid duplicate edges (same from+to+type)
        for existing in edges:
            if (existing["from"] == edge.from_id and
                existing["to"] == edge.to_id and
                existing["edge_type"] == edge.edge_type):
                return
        edges.append(edge.to_dict())
        self._write_state(state)

    def _write_ref(self, node_id: str, raw_text: str):
        """Write raw text to the ref file for a node."""
        ref_path = self.refs_dir / f"{node_id}.md"
        with open(ref_path, "w", encoding="utf-8") as f:
            f.write(raw_text)

    def _load_state(self) -> dict:
        """Load canvas state from disk. Returns empty state if not found."""
        if not self.state_path.exists():
            return {"nodes": {}, "edges": []}
        with open(self.state_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        data.setdefault("nodes", {})
        data.setdefault("edges", [])
        return data

    def _write_state(self, state: dict):
        """Write canvas state to disk."""
        with open(self.state_path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)

    def _regenerate_graph(self):
        """Regenerate the Mermaid graph file from current state."""
        mermaid = self.render(include_archived=True)
        with open(self.graph_path, "w", encoding="utf-8") as f:
            f.write(mermaid)

    def _append_index(self, action: str, **kwargs):
        """Append an entry to the audit index."""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            **kwargs,
        }
        with open(self.index_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _escape_mermaid(text: str) -> str:
    """Escape characters that break Mermaid syntax."""
    # Replace double quotes with single quotes
    text = text.replace('"', "'")
    # Remove newlines (Mermaid nodes are single-line)
    text = text.replace("\n", " ")
    # Escape pipe characters (used in edge labels)
    text = text.replace("|", "/")
    # Escape brackets that could confuse Mermaid parsing
    text = text.replace("[", "(").replace("]", ")")
    return text