"""
OverCR Runtime — Workflow Policy (v0.8.0)

Enforces governance rules for workflow execution.

Rules:
  - OverCR is the only router — subagents never call each other directly
  - Workflow execution stops on validation failure
  - Workflow execution stops on policy violation
  - Workflow execution stops on approval_required unless operator approval exists
  - Workflow execution stops at max_retries
  - Model output remains untrusted until validated
  - Deterministic fallback may be used only if policy allows it
  - No outbound contact
  - No real shell execution
  - No filesystem mutation by inference output
  - No browser/crawling
  - No database dependency
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from runtime.workflow_graph import (
    WorkflowGraph,
    WorkflowNode,
    WorkflowEdge,
    VALID_SUBAGENTS,
    VALID_HANDOFF_PATHS,
    PACKET_TYPES_BY_SUBAGENT,
)


# ──────────────────────────────────────────────
# Policy decision types
# ──────────────────────────────────────────────

class PolicyDecision:
    """Result of a policy check."""
    def __init__(self, allowed: bool, reason: str, policy_name: str = "",
                 details: Optional[dict] = None):
        self.allowed = allowed
        self.reason = reason
        self.policy_name = policy_name
        self.details = details or {}

    def __bool__(self):
        return self.allowed

    def to_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "policy_name": self.policy_name,
            "details": self.details,
        }


# ──────────────────────────────────────────────
# Workflow Policy Engine
# ──────────────────────────────────────────────

class WorkflowPolicy:
    """
    Enforces all governance rules for workflow execution.

    Every node execution, every edge handoff, and every state transition
    must pass through this policy engine. If any rule is violated, the
    entire workflow stops.
    """

    # Forbidden patterns in packet content (runtime-level safety)
    FORBIDDEN_SHELL_PATTERNS = [
        "curl|bash", "wget|sh", "rm -rf", "mkfs", "dd if=",
        "> /dev/sd", "chmod 777", "/etc/passwd",
        "exec(", "__import__", "subprocess.Popen", "os.system(",
    ]

    FORBIDDEN_NETWORK_PATTERNS = [
        "requests.get", "requests.post", "urllib.request",
        "http://", "https://", "socket.connect",
    ]

    def __init__(self, allow_deterministic_fallback: bool = True):
        self.allow_deterministic_fallback = allow_deterministic_fallback

    # ── Node execution policy ───────────────────────────

    def check_node_execution(
        self,
        graph: WorkflowGraph,
        node: WorkflowNode,
        packet: Optional[dict] = None,
    ) -> PolicyDecision:
        """
        Check if a node is allowed to execute.

        Rules:
          1. Node subagent must be valid
          2. Node packet_type must belong to its subagent
          3. Node must not exceed max_retries (checked by caller with retry state)
          4. Node must not require approval unless approval is granted
          5. Packet content must not contain forbidden patterns
        """
        # Rule 1: Valid subagent
        if node.subagent not in VALID_SUBAGENTS:
            return PolicyDecision(
                allowed=False,
                reason=f"Node '{node.node_id}': invalid subagent '{node.subagent}'",
                policy_name="valid_subagent",
            )

        # Rule 2: Packet type belongs to subagent
        if node.packet_type not in PACKET_TYPES_BY_SUBAGENT.get(node.subagent, set()):
            return PolicyDecision(
                allowed=False,
                reason=f"Node '{node.node_id}': subagent '{node.subagent}' cannot "
                       f"produce packet_type '{node.packet_type}'",
                policy_name="packet_type_ownership",
            )

        # Rule 3: Approval policy
        if node.approval_policy == "always":
            # Approval must be granted by the workflow runner before execution
            # This check is advisory — the runner enforces the actual gate
            pass

        # Rule 4: Packet content safety (if packet provided)
        if packet:
            content_check = self._check_packet_content_safety(packet)
            if not content_check.allowed:
                return content_check

        return PolicyDecision(
            allowed=True,
            reason="All node execution policies satisfied",
            policy_name="node_execution",
        )

    # ── Edge handoff policy ─────────────────────────────

    def check_edge_handoff(
        self,
        graph: WorkflowGraph,
        edge: WorkflowEdge,
        source_packet: Optional[dict] = None,
    ) -> PolicyDecision:
        """
        Check if an edge handoff is allowed.

        Rules:
          1. Source and target must be different subagents (sovereignty for
             cross-subagent edges) or same subagent (internal)
          2. Cross-subagent handoff must go through a valid OverCR path
          3. No direct subagent-to-subagent routing (must be through OverCR)
          4. Edge approval gate must be satisfied if set
          5. Source packet type must be in edge's accepted_packet_types
        """
        src_node = graph.nodes.get(edge.source_node_id)
        tgt_node = graph.nodes.get(edge.target_node_id)

        if not src_node or not tgt_node:
            return PolicyDecision(
                allowed=False,
                reason=f"Edge '{edge.edge_id}': source or target node not found",
                policy_name="edge_nodes_exist",
            )

        # Cross-subagent handoff must be via a valid OverCR path
        if src_node.subagent != tgt_node.subagent:
            path = (src_node.subagent, tgt_node.subagent)
            if path not in VALID_HANDOFF_PATHS:
                return PolicyDecision(
                    allowed=False,
                    reason=f"Edge '{edge.edge_id}': invalid handoff path "
                           f"{src_node.subagent} -> {tgt_node.subagent}. "
                           f"Direct subagent-to-subagent routing is forbidden. "
                           f"All handoffs must go through OverCR.",
                    policy_name="sovereignty",
                )

        # Source packet type must be accepted by edge
        if source_packet:
            src_type = source_packet.get("packet_type", "")
            if src_type not in edge.accepted_packet_types:
                return PolicyDecision(
                    allowed=False,
                    reason=f"Edge '{edge.edge_id}': source packet type '{src_type}' "
                           f"not in accepted_packet_types {edge.accepted_packet_types}",
                    policy_name="packet_type_compatibility",
                )

        # Edge approval gate
        if edge.approval_gate == "always":
            # Advisory: the runner must enforce the actual approval
            pass

        return PolicyDecision(
            allowed=True,
            reason="All edge handoff policies satisfied",
            policy_name="edge_handoff",
        )

    # ── Approval policy ─────────────────────────────────

    def check_approval_required(
        self,
        node: WorkflowNode,
        edge: Optional[WorkflowEdge] = None,
        operator_approval: Optional[dict] = None,
    ) -> PolicyDecision:
        """
        Check if operator approval is required and whether it has been granted.

        Returns PolicyDecision:
          - allowed=True if no approval needed or approval granted
          - allowed=False if approval required but not granted
        """
        approval_needed = False
        reasons = []

        # Node-level approval
        if node.approval_policy == "always":
            approval_needed = True
            reasons.append(f"Node '{node.node_id}' has approval_policy='always'")

        # Edge-level approval
        if edge and edge.approval_gate == "always":
            approval_needed = True
            reasons.append(f"Edge '{edge.edge_id}' has approval_gate='always'")

        if not approval_needed:
            return PolicyDecision(
                allowed=True,
                reason="No approval required",
                policy_name="approval_gate",
            )

        # Approval is required — check if granted
        if operator_approval and operator_approval.get("decision") == "approved":
            return PolicyDecision(
                allowed=True,
                reason=f"Approval granted: {operator_approval.get('reason', '')}",
                policy_name="approval_gate",
                details={"operator_approval": operator_approval},
            )

        return PolicyDecision(
            allowed=False,
            reason="Approval required but not granted: " + "; ".join(reasons),
            policy_name="approval_gate",
        )

    # ── Retry policy ────────────────────────────────────

    def check_retry_allowed(
        self,
        node: WorkflowNode,
        current_retry_count: int,
        last_error: Optional[str] = None,
    ) -> PolicyDecision:
        """
        Check if retry is allowed for a node.

        Rules:
          - current_retry_count must be < node.max_retries
          - If max_retries == 0, no retry allowed
        """
        if node.max_retries == 0:
            return PolicyDecision(
                allowed=False,
                reason=f"Node '{node.node_id}': max_retries=0, no retry allowed",
                policy_name="retry_limit",
            )

        if current_retry_count >= node.max_retries:
            return PolicyDecision(
                allowed=False,
                reason=f"Node '{node.node_id}': retry limit reached "
                       f"({current_retry_count}/{node.max_retries})",
                policy_name="retry_limit",
                details={"last_error": last_error},
            )

        return PolicyDecision(
            allowed=True,
            reason=f"Retry allowed ({current_retry_count}/{node.max_retries})",
            policy_name="retry_limit",
        )

    # ── Deterministic fallback policy ──────────────────

    def check_deterministic_fallback(
        self,
        node: WorkflowNode,
        inference_failed: bool = False,
    ) -> PolicyDecision:
        """
        Check if deterministic fallback is allowed.

        Rules:
          - Only allowed if policy config allows it
          - Only allowed when inference has actually failed
        """
        if not self.allow_deterministic_fallback:
            return PolicyDecision(
                allowed=False,
                reason="Deterministic fallback is disabled by policy",
                policy_name="deterministic_fallback",
            )

        if not inference_failed:
            return PolicyDecision(
                allowed=False,
                reason="Deterministic fallback not allowed — inference did not fail",
                policy_name="deterministic_fallback",
            )

        return PolicyDecision(
            allowed=True,
            reason="Deterministic fallback allowed — inference failed and policy permits",
            policy_name="deterministic_fallback",
        )

    # ── Packet content safety ───────────────────────────

    def _check_packet_content_safety(self, packet: dict) -> PolicyDecision:
        """
        Check packet content for forbidden patterns.

        Scans all string values in the packet for:
          - Shell execution patterns
          - Network access patterns
        """
        packet_str = json.dumps(packet)

        for pattern in self.FORBIDDEN_SHELL_PATTERNS:
            if pattern.lower() in packet_str.lower():
                return PolicyDecision(
                    allowed=False,
                    reason=f"Forbidden shell pattern detected: '{pattern}'",
                    policy_name="content_safety_shell",
                )

        for pattern in self.FORBIDDEN_NETWORK_PATTERNS:
            # Allow https:// in source URLs that are entity references
            # but block active network access patterns
            if pattern in ("http://", "https://"):
                # Only flag if it looks like an active fetch, not a reference
                if f"{pattern}" in packet_str and ("fetch" in packet_str.lower() or
                                                      "request" in packet_str.lower()):
                    return PolicyDecision(
                        allowed=False,
                        reason=f"Forbidden network pattern detected: '{pattern}' with active fetch",
                        policy_name="content_safety_network",
                    )
            elif pattern.lower() in packet_str.lower():
                return PolicyDecision(
                    allowed=False,
                    reason=f"Forbidden network pattern detected: '{pattern}'",
                    policy_name="content_safety_network",
                )

        return PolicyDecision(
            allowed=True,
            reason="Packet content passed safety checks",
            policy_name="content_safety",
        )

    # ── Full workflow policy check ─────────────────────

    def check_full_workflow(
        self,
        graph: WorkflowGraph,
        operator_approvals: Optional[dict] = None,
    ) -> PolicyDecision:
        """
        Run a comprehensive policy check on the entire workflow graph.

        Checks every node and edge for policy compliance.
        Checks all approval requirements.
        """
        operator_approvals = operator_approvals or {}
        all_reasons = []

        # Check all nodes
        for node in graph.nodes.values():
            node_check = self.check_node_execution(graph, node)
            if not node_check.allowed:
                all_reasons.append(node_check.reason)

        # Check all edges
        for edge in graph.edges.values():
            edge_check = self.check_edge_handoff(graph, edge)
            if not edge_check.allowed:
                all_reasons.append(edge_check.reason)

            # Check approval requirements
            src_node = graph.nodes.get(edge.source_node_id)
            if src_node:
                approval_check = self.check_approval_required(
                    src_node, edge,
                    operator_approvals.get(edge.edge_id),
                )
                if not approval_check.allowed:
                    all_reasons.append(approval_check.reason)

        if all_reasons:
            return PolicyDecision(
                allowed=False,
                reason="Workflow policy violations: " + "; ".join(all_reasons),
                policy_name="full_workflow",
                details={"violations": all_reasons},
            )

        return PolicyDecision(
            allowed=True,
            reason="All workflow policies satisfied",
            policy_name="full_workflow",
        )