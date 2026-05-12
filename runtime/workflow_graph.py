"""
OverCR Runtime — Workflow Graph (v0.8.0)

Defines the DAG model for governed cross-worker choreography.

A WorkflowGraph is an explicit directed acyclic graph where:
  - Every node is a task assigned to one subagent
  - Every edge is a typed packet handoff routed through OverCR
  - The graph is serializable as JSON
  - The graph is validated on construction (cycles, orphan nodes, invalid handoffs)

Design constraints:
  - OverCR is the only router — no direct subagent-to-subagent authority
  - Graph must be a valid DAG (no cycles)
  - All packet handoffs must be between valid subagents via OverCR routing
  - Every node declares its subagent, packet_type, I/O requirements, approval policy,
    max_retries, and timeout
  - Every edge declares source/target nodes, accepted packet types, optional
    transformation rule, and optional approval gate
"""

import json
import uuid
from collections import deque
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional

# ──────────────────────────────────────────────
# Valid subagents and packet types (from validate_packet.py)
# ──────────────────────────────────────────────

VALID_SUBAGENTS = {"cryer", "pyper", "coder", "knower"}

PACKET_TYPES_BY_SUBAGENT = {
    "cryer": {"cryer_recon", "cryer_update", "cryer_alert",
              "cryer_reputation_signal", "cryer_engagement_signal",
              "cryer_booking_friction", "cryer_directory_completeness",
              "cryer_hiring_growth"},
    "pyper": {"pyper_approval", "pyper_revision", "pyper_objection_response",
              "pyper_execution_plan", "pyper_execution_receipt",
              "pyper_execution_refusal"},
    "coder": {"coder_completion", "coder_blocked", "coder_diagnostic",
              "coder_patch_plan"},
    "knower": {"knower_research", "knower_assessment",
               "knower_myth_separation", "knower_claim_review",
               "knower_myth_fact"},
}

ALL_PACKET_TYPES = set()
for _types in PACKET_TYPES_BY_SUBAGENT.values():
    ALL_PACKET_TYPES.update(_types)


# ──────────────────────────────────────────────
# Valid v0.8.0 handoff paths (source_subagent -> target_subagent)
# ──────────────────────────────────────────────

VALID_HANDOFF_PATHS = {
    ("knower", "cryer"),
    ("cryer", "pyper"),
    ("coder", "pyper"),
    ("knower", "pyper"),
    ("knower", "coder"),
    ("coder", "knower"),
    ("cryer", "knower"),
}


# ──────────────────────────────────────────────
# Approval policies
# ──────────────────────────────────────────────

VALID_APPROVAL_POLICIES = {"always", "on_failure", "never"}


# ──────────────────────────────────────────────
# Node and Edge definitions
# ──────────────────────────────────────────────

@dataclass
class WorkflowNode:
    """
    A single node in the workflow DAG — one task assigned to one subagent.

    Required fields:
      - node_id: unique identifier within the graph
      - subagent: which subagent executes this node
      - packet_type: what packet type this node produces
      - input_requirements: list of required input packet types
      - output_requirements: list of expected output packet types
      - approval_policy: "always" | "on_failure" | "never"
      - max_retries: maximum retry attempts (0 = no retry)
      - timeout_s: maximum seconds for this node's execution
    """
    node_id: str
    subagent: str
    packet_type: str
    input_requirements: list = field(default_factory=list)
    output_requirements: list = field(default_factory=list)
    approval_policy: str = "always"
    max_retries: int = 0
    timeout_s: float = 30.0
    description: str = ""

    def validate(self) -> tuple[bool, list[str]]:
        """Validate this node's fields. Returns (valid, errors)."""
        errors = []
        if not self.node_id or not self.node_id.strip():
            errors.append(f"Node has empty node_id")
        if self.subagent not in VALID_SUBAGENTS:
            errors.append(f"Node '{self.node_id}': invalid subagent '{self.subagent}'")
        if self.packet_type not in ALL_PACKET_TYPES:
            errors.append(f"Node '{self.node_id}': invalid packet_type '{self.packet_type}'")
        if self.packet_type not in PACKET_TYPES_BY_SUBAGENT.get(self.subagent, set()):
            errors.append(
                f"Node '{self.node_id}': subagent '{self.subagent}' cannot "
                f"produce packet_type '{self.packet_type}'"
            )
        if self.approval_policy not in VALID_APPROVAL_POLICIES:
            errors.append(
                f"Node '{self.node_id}': invalid approval_policy '{self.approval_policy}'"
            )
        if self.max_retries < 0:
            errors.append(f"Node '{self.node_id}': max_retries must be >= 0")
        if self.timeout_s <= 0:
            errors.append(f"Node '{self.node_id}': timeout_s must be > 0")
        return len(errors) == 0, errors


@dataclass
class WorkflowEdge:
    """
    A directed edge between two nodes — a typed packet handoff routed through OverCR.

    Required fields:
      - edge_id: unique identifier within the graph
      - source_node_id: the node that produces the packet
      - target_node_id: the node that receives the packet
      - accepted_packet_types: packet types valid on this edge

    Optional fields:
      - transformation_rule: how to transform the packet for the target (or None)
      - approval_gate: whether this handoff requires approval (or None)
    """
    edge_id: str
    source_node_id: str
    target_node_id: str
    accepted_packet_types: list = field(default_factory=list)
    transformation_rule: Optional[str] = None
    approval_gate: Optional[str] = None

    def validate(self, node_ids: set) -> tuple[bool, list[str]]:
        """Validate this edge's fields. Returns (valid, errors)."""
        errors = []
        if not self.edge_id or not self.edge_id.strip():
            errors.append("Edge has empty edge_id")
        if self.source_node_id not in node_ids:
            errors.append(
                f"Edge '{self.edge_id}': source_node_id '{self.source_node_id}' "
                f"not found in graph nodes"
            )
        if self.target_node_id not in node_ids:
            errors.append(
                f"Edge '{self.edge_id}': target_node_id '{self.target_node_id}' "
                f"not found in graph nodes"
            )
        if self.source_node_id == self.target_node_id:
            errors.append(
                f"Edge '{self.edge_id}': self-loop detected "
                f"(source == target == '{self.source_node_id}')"
            )
        if not self.accepted_packet_types:
            errors.append(f"Edge '{self.edge_id}': must declare at least one accepted_packet_type")
        for pt in self.accepted_packet_types:
            if pt not in ALL_PACKET_TYPES:
                errors.append(
                    f"Edge '{self.edge_id}': invalid accepted_packet_type '{pt}'"
                )
        if self.approval_gate is not None and self.approval_gate not in VALID_APPROVAL_POLICIES:
            errors.append(
                f"Edge '{self.edge_id}': invalid approval_gate '{self.approval_gate}'"
            )
        return len(errors) == 0, errors


# ──────────────────────────────────────────────
# Workflow Graph
# ──────────────────────────────────────────────

class WorkflowGraph:
    """
    An explicit DAG for governed cross-worker choreography.

    Every node is a task assigned to one subagent.
    Every edge is a typed packet handoff routed through OverCR.
    OverCR is the only router — no direct subagent-to-subagent routing.
    """

    def __init__(
        self,
        workflow_id: Optional[str] = None,
        name: str = "",
        version: str = "0.8.0",
        description: str = "",
    ):
        self.workflow_id = workflow_id or str(uuid.uuid4())
        self.name = name
        self.version = version
        self.description = description
        self.nodes: dict[str, WorkflowNode] = {}
        self.edges: dict[str, WorkflowEdge] = {}
        self._built = False
        self._build_errors: list[str] = []

    # ── Construction ─────────────────────────────────────

    def add_node(self, node: WorkflowNode) -> 'WorkflowGraph':
        """Add a node to the graph. Returns self for chaining."""
        if node.node_id in self.nodes:
            raise ValueError(f"Duplicate node_id: '{node.node_id}'")
        valid, errors = node.validate()
        if not valid:
            raise ValueError(f"Invalid node: {errors}")
        self.nodes[node.node_id] = node
        self._built = False
        return self

    def add_edge(self, edge: WorkflowEdge) -> 'WorkflowGraph':
        """Add an edge to the graph. Returns self for chaining."""
        if edge.edge_id in self.edges:
            raise ValueError(f"Duplicate edge_id: '{edge.edge_id}'")
        node_ids = set(self.nodes.keys())
        valid, errors = edge.validate(node_ids)
        if not valid:
            raise ValueError(f"Invalid edge: {errors}")
        self.edges[edge.edge_id] = edge
        self._built = False
        return self

    # ── Build & Validate ─────────────────────────────────

    def build(self) -> tuple[bool, list[str]]:
        """
        Validate and finalize the graph.

        Checks:
          1. At least one node exists
          2. All node IDs referenced by edges exist
          3. No cycles (DAG invariant)
          4. No direct subagent-to-subagent routing (sovereignty)
          5. Packet type compatibility on edges
          6. No orphan nodes (every node reachable from a root)

        Returns: (valid, errors)
        """
        errors = []
        self._build_errors = []

        # 1. Must have nodes
        if not self.nodes:
            errors.append("Graph has no nodes")

        # 2. Edge references checked during add_edge, but double-check
        node_ids = set(self.nodes.keys())
        for edge in self.edges.values():
            if edge.source_node_id not in node_ids:
                errors.append(
                    f"Edge '{edge.edge_id}' references missing source node "
                    f"'{edge.source_node_id}'"
                )
            if edge.target_node_id not in node_ids:
                errors.append(
                    f"Edge '{edge.edge_id}' references missing target node "
                    f"'{edge.target_node_id}'"
                )

        # 3. Cycle detection (Kahn's algorithm / topological sort)
        has_cycle = self._detect_cycle()
        if has_cycle:
            errors.append("Graph contains a cycle — DAG invariant violated")

        # 4. Sovereignty: no direct subagent-to-subagent routing
        for edge in self.edges.values():
            src_node = self.nodes.get(edge.source_node_id)
            tgt_node = self.nodes.get(edge.target_node_id)
            if src_node and tgt_node:
                # Check that handoff path is valid through OverCR
                path = (src_node.subagent, tgt_node.subagent)
                if path not in VALID_HANDOFF_PATHS and src_node.subagent != tgt_node.subagent:
                    errors.append(
                        f"Edge '{edge.edge_id}': invalid handoff path "
                        f"{src_node.subagent} -> {tgt_node.subagent}. "
                        f"Only OverCR-routed paths are allowed."
                    )

        # 5. Packet type compatibility on edges
        for edge in self.edges.values():
            src_node = self.nodes.get(edge.source_node_id)
            if src_node:
                # Source node must produce a packet type accepted by the edge
                if src_node.packet_type not in edge.accepted_packet_types:
                    errors.append(
                        f"Edge '{edge.edge_id}': source node '{src_node.node_id}' "
                        f"produces '{src_node.packet_type}' but edge accepts "
                        f"{edge.accepted_packet_types}"
                    )
            # All accepted packet types must be valid
            for pt in edge.accepted_packet_types:
                if pt not in ALL_PACKET_TYPES:
                    errors.append(
                        f"Edge '{edge.edge_id}': invalid packet type '{pt}'"
                    )

        # 6. No orphan nodes — every node must be reachable from a root
        if self.nodes:
            roots = self._find_roots()
            reachable = set()
            for root_id in roots:
                reachable.update(self._bfs_reachable(root_id))
            # Also traverse backwards from leaves to catch nodes only reachable
            # going forward
            for node_id in node_ids:
                if node_id not in reachable:
                    # Check if it's a root (no incoming edges)
                    incoming = [e for e in self.edges.values()
                                if e.target_node_id == node_id]
                    if incoming:
                        errors.append(
                            f"Node '{node_id}' is unreachable from any root"
                        )
                    # Pure root nodes with no incoming edges are fine

        self._build_errors = errors
        self._built = len(errors) == 0
        return self._built, errors

    def _detect_cycle(self) -> bool:
        """Detect cycles using topological sort (Kahn's algorithm)."""
        # Build adjacency lists
        in_degree = {nid: 0 for nid in self.nodes}
        adj = {nid: [] for nid in self.nodes}

        for edge in self.edges.values():
            if edge.source_node_id in in_degree and edge.target_node_id in in_degree:
                adj[edge.source_node_id].append(edge.target_node_id)
                in_degree[edge.target_node_id] += 1

        # Kahn's algorithm
        queue = deque(nid for nid, deg in in_degree.items() if deg == 0)
        visited = 0

        while queue:
            node_id = queue.popleft()
            visited += 1
            for neighbor in adj[node_id]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        return visited != len(self.nodes)

    def _find_roots(self) -> list[str]:
        """Find root nodes (nodes with no incoming edges)."""
        targets = {e.target_node_id for e in self.edges.values()}
        return [nid for nid in self.nodes if nid not in targets]

    def _find_leaves(self) -> list[str]:
        """Find leaf nodes (nodes with no outgoing edges)."""
        sources = {e.source_node_id for e in self.edges.values()}
        return [nid for nid in self.nodes if nid not in sources]

    def _bfs_reachable(self, start_id: str) -> set[str]:
        """BFS to find all nodes reachable from start_id."""
        visited = set()
        queue = deque([start_id])
        while queue:
            nid = queue.popleft()
            if nid in visited:
                continue
            visited.add(nid)
            for edge in self.edges.values():
                if edge.source_node_id == nid and edge.target_node_id not in visited:
                    queue.append(edge.target_node_id)
        return visited

    # ── Topological ordering ─────────────────────────────

    def topological_order(self) -> list[str]:
        """Return node IDs in topological order. Raises if graph has cycles."""
        in_degree = {nid: 0 for nid in self.nodes}
        adj = {nid: [] for nid in self.nodes}

        for edge in self.edges.values():
            if edge.source_node_id in adj and edge.target_node_id in in_degree:
                adj[edge.source_node_id].append(edge.target_node_id)
                in_degree[edge.target_node_id] += 1

        queue = deque(sorted(nid for nid, deg in in_degree.items() if deg == 0))
        order = []

        while queue:
            node_id = queue.popleft()
            order.append(node_id)
            for neighbor in sorted(adj[node_id]):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(order) != len(self.nodes):
            raise ValueError("Cannot compute topological order — graph has cycles")

        return order

    # ── Edge queries ─────────────────────────────────────

    def edges_from(self, node_id: str) -> list[WorkflowEdge]:
        """Get all outgoing edges from a node."""
        return [e for e in self.edges.values() if e.source_node_id == node_id]

    def edges_to(self, node_id: str) -> list[WorkflowEdge]:
        """Get all incoming edges to a node."""
        return [e for e in self.edges.values() if e.target_node_id == node_id]

    def predecessor_nodes(self, node_id: str) -> list[str]:
        """Get all predecessor node IDs."""
        return [e.source_node_id for e in self.edges.values()
                if e.target_node_id == node_id]

    def successor_nodes(self, node_id: str) -> list[str]:
        """Get all successor node IDs."""
        return [e.target_node_id for e in self.edges.values()
                if e.source_node_id == node_id]

    # ── Serialization ────────────────────────────────────

    def to_dict(self) -> dict:
        """Serialize the graph to a JSON-compatible dict."""
        return {
            "workflow_id": self.workflow_id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "nodes": {
                nid: asdict(node) for nid, node in self.nodes.items()
            },
            "edges": {
                eid: asdict(edge) for eid, edge in self.edges.items()
            },
            "built": self._built,
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialize the graph to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_dict(cls, data: dict) -> 'WorkflowGraph':
        """Deserialize a graph from a dict."""
        graph = cls(
            workflow_id=data.get("workflow_id", ""),
            name=data.get("name", ""),
            version=data.get("version", "0.8.0"),
            description=data.get("description", ""),
        )
        for nid, ndata in data.get("nodes", {}).items():
            node = WorkflowNode(
                node_id=ndata["node_id"],
                subagent=ndata["subagent"],
                packet_type=ndata["packet_type"],
                input_requirements=ndata.get("input_requirements", []),
                output_requirements=ndata.get("output_requirements", []),
                approval_policy=ndata.get("approval_policy", "always"),
                max_retries=ndata.get("max_retries", 0),
                timeout_s=ndata.get("timeout_s", 30.0),
                description=ndata.get("description", ""),
            )
            graph.nodes[nid] = node

        for eid, edata in data.get("edges", {}).items():
            edge = WorkflowEdge(
                edge_id=edata["edge_id"],
                source_node_id=edata["source_node_id"],
                target_node_id=edata["target_node_id"],
                accepted_packet_types=edata.get("accepted_packet_types", []),
                transformation_rule=edata.get("transformation_rule"),
                approval_gate=edata.get("approval_gate"),
            )
            graph.edges[eid] = edge

        graph._built = data.get("built", False)
        return graph

    @classmethod
    def from_json(cls, json_str: str) -> 'WorkflowGraph':
        """Deserialize a graph from a JSON string."""
        return cls.from_dict(json.loads(json_str))

    # ── Factory helpers ─────────────────────────────────

    @staticmethod
    def knower_to_cryer_workflow(
        workflow_id: Optional[str] = None,
        name: str = "knower_to_cryer",
    ) -> 'WorkflowGraph':
        """
        Build the KnowER → CryER v0.8.0 demo workflow.

        KnowER classifies claims/snippets.
        CryER produces governed recon packet using validated public-signal context.
        """
        graph = WorkflowGraph(
            workflow_id=workflow_id,
            name=name,
            version="0.8.0",
            description="KnowER classifies claims, CryER produces recon from public signals",
        )

        graph.add_node(WorkflowNode(
            node_id="knower_classify",
            subagent="knower",
            packet_type="knower_claim_review",
            input_requirements=["raw_claims"],
            output_requirements=["classified_claims"],
            approval_policy="on_failure",
            max_retries=1,
            timeout_s=60.0,
            description="Classify provided claims/snippets",
        ))

        graph.add_node(WorkflowNode(
            node_id="cryer_recon",
            subagent="cryer",
            packet_type="cryer_recon",
            input_requirements=["classified_claims"],
            output_requirements=["recon_packet"],
            approval_policy="always",
            max_retries=1,
            timeout_s=60.0,
            description="Produce governed recon packet from validated public-signal context",
        ))

        graph.add_edge(WorkflowEdge(
            edge_id="knower_to_cryer",
            source_node_id="knower_classify",
            target_node_id="cryer_recon",
            accepted_packet_types=["knower_claim_review", "knower_assessment"],
            transformation_rule="extract_public_signal_context",
            approval_gate="never",
        ))

        return graph

    @staticmethod
    def cryer_to_pyper_workflow(
        workflow_id: Optional[str] = None,
        name: str = "cryer_to_pyper",
    ) -> 'WorkflowGraph':
        """
        Build the CryER → PypER v0.8.0 demo workflow.

        CryER produces public signal packet.
        PypER produces execution/outreach planning packet.
        Output remains approval_required=true.
        No outbound action.
        """
        graph = WorkflowGraph(
            workflow_id=workflow_id,
            name=name,
            version="0.8.0",
            description="CryER signals → PypER planning (approval_required, no outbound)",
        )

        graph.add_node(WorkflowNode(
            node_id="cryer_signal",
            subagent="cryer",
            packet_type="cryer_engagement_signal",
            input_requirements=["entity_context"],
            output_requirements=["signal_packet"],
            approval_policy="on_failure",
            max_retries=1,
            timeout_s=60.0,
            description="Produce public engagement signal packet",
        ))

        graph.add_node(WorkflowNode(
            node_id="pyper_plan",
            subagent="pyper",
            packet_type="pyper_execution_plan",
            input_requirements=["signal_packet"],
            output_requirements=["execution_plan"],
            approval_policy="always",
            max_retries=0,
            timeout_s=60.0,
            description="Produce execution/outreach planning packet (approval_required=true)",
        ))

        graph.add_edge(WorkflowEdge(
            edge_id="cryer_to_pyper",
            source_node_id="cryer_signal",
            target_node_id="pyper_plan",
            accepted_packet_types=["cryer_engagement_signal", "cryer_reputation_signal",
                                    "cryer_recon"],
            transformation_rule="extract_signal_for_planning",
            approval_gate="always",
        ))

        return graph

    @staticmethod
    def coder_to_pyper_workflow(
        workflow_id: Optional[str] = None,
        name: str = "coder_to_pyper",
    ) -> 'WorkflowGraph':
        """
        Build the CodER → PypER v0.8.0 demo workflow.

        CodER produces advisory patch plan.
        PypER produces execution plan/receipt simulation.
        No command execution. No filesystem mutation.
        """
        graph = WorkflowGraph(
            workflow_id=workflow_id,
            name=name,
            version="0.8.0",
            description="CodER patch advisory → PypER execution simulation (no execution, no mutation)",
        )

        graph.add_node(WorkflowNode(
            node_id="coder_patch",
            subagent="coder",
            packet_type="coder_patch_plan",
            input_requirements=["issue_context"],
            output_requirements=["patch_plan"],
            approval_policy="always",
            max_retries=1,
            timeout_s=60.0,
            description="Produce advisory patch plan",
        ))

        graph.add_node(WorkflowNode(
            node_id="pyper_simulate",
            subagent="pyper",
            packet_type="pyper_execution_receipt",
            input_requirements=["patch_plan"],
            output_requirements=["simulated_receipt"],
            approval_policy="always",
            max_retries=0,
            timeout_s=60.0,
            description="Produce execution plan and simulated receipt (no real execution)",
        ))

        graph.add_edge(WorkflowEdge(
            edge_id="coder_to_pyper",
            source_node_id="coder_patch",
            target_node_id="pyper_simulate",
            accepted_packet_types=["coder_patch_plan"],
            transformation_rule="extract_patch_for_simulation",
            approval_gate="always",
        ))

        return graph