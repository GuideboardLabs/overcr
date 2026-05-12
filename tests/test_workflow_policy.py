#!/usr/bin/env python3
"""
OverCR v0.8.0 — Test: Workflow Policy

Tests the WorkflowPolicy governance engine including:
  - check_node_execution: subagent validity, packet_type ownership, content safety
  - check_edge_handoff: sovereignty, packet type compatibility, node existence
  - check_approval_required: approval gating logic
  - check_retry_allowed: max_retries enforcement
  - check_deterministic_fallback: inference failure and policy config checks
  - _check_packet_content_safety: forbidden shell/network patterns
  - check_full_workflow: comprehensive graph validation
  - PolicyDecision __bool__ and to_dict
"""

import sys
from pathlib import Path

OVERCR_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(OVERCR_ROOT))

from runtime.workflow_graph import (
    WorkflowGraph, WorkflowNode, WorkflowEdge,
    VALID_SUBAGENTS, VALID_HANDOFF_PATHS,
    PACKET_TYPES_BY_SUBAGENT,
)
from runtime.workflow_policy import WorkflowPolicy, PolicyDecision

FAILED = False


# ────────────────────────────────────────────────────────
# check_node_execution
# ────────────────────────────────────────────────────────

def test_node_execution_allowed():
    """Valid node execution is allowed."""
    global FAILED
    policy = WorkflowPolicy()
    graph = WorkflowGraph.knower_to_cryer_workflow()
    graph.build()

    node = graph.nodes["knower_classify"]
    decision = policy.check_node_execution(graph, node)

    assert decision.allowed, f"Valid node should be allowed: {decision.reason}"
    assert bool(decision) is True
    print("  PASS: Valid node execution allowed")


def test_invalid_subagent_rejected():
    """Node with invalid subagent is rejected."""
    global FAILED
    policy = WorkflowPolicy()
    graph = WorkflowGraph(name="bad_subagent_test")
    # Bypass add_node validation so we can craft a node with bad subagent
    bad_node = WorkflowNode(
        node_id="bad_agent",
        subagent="evil_agent",
        packet_type="knower_claim_review",
    )
    # Place it directly in the graph's nodes dict to bypass WorkflowNode.validate()
    graph.nodes["bad_agent"] = bad_node

    decision = policy.check_node_execution(graph, bad_node)
    assert not decision.allowed, "Invalid subagent should be rejected"
    assert decision.policy_name == "valid_subagent"
    assert bool(decision) is False
    print("  PASS: Invalid subagent rejected")


def test_invalid_packet_type_for_subagent_rejected():
    """Node with packet_type not belonging to its subagent is rejected."""
    global FAILED
    policy = WorkflowPolicy()
    graph = WorkflowGraph(name="bad_packet_test")
    # knower cannot produce cryer_recon
    bad_node = WorkflowNode(
        node_id="mismatched_packet",
        subagent="knower",
        packet_type="cryer_recon",
    )
    # Bypass add_node validation by inserting directly
    graph.nodes["mismatched_packet"] = bad_node

    decision = policy.check_node_execution(graph, bad_node)
    assert not decision.allowed, "Wrong packet_type for subagent should be rejected"
    assert decision.policy_name == "packet_type_ownership"
    print("  PASS: Invalid packet_type for subagent rejected")


# ────────────────────────────────────────────────────────
# check_edge_handoff
# ────────────────────────────────────────────────────────

def test_edge_handoff_allowed():
    """Valid edge handoff is allowed."""
    global FAILED
    policy = WorkflowPolicy()
    graph = WorkflowGraph.knower_to_cryer_workflow()
    graph.build()

    edge = graph.edges["knower_to_cryer"]
    decision = policy.check_edge_handoff(graph, edge)

    assert decision.allowed, f"Valid edge handoff should be allowed: {decision.reason}"
    assert bool(decision) is True
    print("  PASS: Valid edge handoff allowed")


def test_edge_handoff_invalid_sovereignty():
    """Edge with invalid handoff path (sovereignty) is rejected."""
    global FAILED
    policy = WorkflowPolicy()
    graph = WorkflowGraph(name="sovereignty_test")
    # pyper -> knower is NOT in VALID_HANDOFF_PATHS
    node_a = WorkflowNode(
        node_id="pyper_1",
        subagent="pyper",
        packet_type="pyper_execution_plan",
    )
    node_b = WorkflowNode(
        node_id="knower_1",
        subagent="knower",
        packet_type="knower_claim_review",
    )
    # Direct insertion to bypass add_node validation on the edge
    graph.nodes["pyper_1"] = node_a
    graph.nodes["knower_1"] = node_b

    bad_edge = WorkflowEdge(
        edge_id="p2k",
        source_node_id="pyper_1",
        target_node_id="knower_1",
        accepted_packet_types=["pyper_execution_plan"],
    )
    graph.edges["p2k"] = bad_edge

    decision = policy.check_edge_handoff(graph, bad_edge)
    assert not decision.allowed, "Invalid handoff path should be rejected"
    assert decision.policy_name == "sovereignty"
    print("  PASS: Invalid handoff path (sovereignty) rejected")


def test_edge_missing_nodes_rejected():
    """Edge referencing missing nodes is rejected."""
    global FAILED
    policy = WorkflowPolicy()
    graph = WorkflowGraph(name="missing_nodes_test")
    # Edge referencing nodes that don't exist in graph
    ghost_edge = WorkflowEdge(
        edge_id="ghost_edge",
        source_node_id="nonexistent_src",
        target_node_id="nonexistent_tgt",
        accepted_packet_types=["knower_claim_review"],
    )
    graph.edges["ghost_edge"] = ghost_edge

    decision = policy.check_edge_handoff(graph, ghost_edge)
    assert not decision.allowed, "Edge with missing nodes should be rejected"
    assert decision.policy_name == "edge_nodes_exist"
    print("  PASS: Edge with missing nodes rejected")


def test_edge_packet_type_not_accepted():
    """Edge where source packet_type is not in accepted_packet_types is rejected."""
    global FAILED
    policy = WorkflowPolicy()
    graph = WorkflowGraph(name="bad_pkt_edge_test")
    node_src = WorkflowNode(
        node_id="knower_src",
        subagent="knower",
        packet_type="knower_claim_review",
    )
    node_tgt = WorkflowNode(
        node_id="cryer_tgt",
        subagent="cryer",
        packet_type="cryer_recon",
    )
    graph.nodes["knower_src"] = node_src
    graph.nodes["cryer_tgt"] = node_tgt

    edge = WorkflowEdge(
        edge_id="k2c_bad",
        source_node_id="knower_src",
        target_node_id="cryer_tgt",
        accepted_packet_types=["cryer_recon"],  # Source produces knower_claim_review, not cryer_recon
    )
    graph.edges["k2c_bad"] = edge

    source_packet = {"packet_type": "knower_claim_review"}
    decision = policy.check_edge_handoff(graph, edge, source_packet=source_packet)
    assert not decision.allowed, "Source packet type not in accepted_packet_types should be rejected"
    assert decision.policy_name == "packet_type_compatibility"
    print("  PASS: Packet type not in accepted_packet_types rejected")


# ────────────────────────────────────────────────────────
# check_approval_required
# ────────────────────────────────────────────────────────

def test_approval_not_needed_never():
    """Approval not needed when node has approval_policy=never and edge has no gate."""
    global FAILED
    policy = WorkflowPolicy()
    node = WorkflowNode(
        node_id="free_node",
        subagent="knower",
        packet_type="knower_claim_review",
        approval_policy="never",
    )
    decision = policy.check_approval_required(node)
    assert decision.allowed, "No approval should be needed for approval_policy=never"
    assert "No approval required" in decision.reason
    print("  PASS: Approval not needed when policy=never")


def test_approval_needed_not_granted():
    """Approval needed but not granted blocks execution."""
    global FAILED
    policy = WorkflowPolicy()
    node = WorkflowNode(
        node_id="locked_node",
        subagent="cryer",
        packet_type="cryer_recon",
        approval_policy="always",
    )
    edge = WorkflowEdge(
        edge_id="e1",
        source_node_id="locked_node",
        target_node_id="some_target",
        accepted_packet_types=["cryer_recon"],
        approval_gate="always",
    )
    # No operator_approval provided
    decision = policy.check_approval_required(node, edge)
    assert not decision.allowed, "Approval required but not granted should block"
    assert "not granted" in decision.reason
    print("  PASS: Approval needed but not granted blocks execution")


def test_approval_needed_and_granted():
    """Approval needed and granted allows execution."""
    global FAILED
    policy = WorkflowPolicy()
    node = WorkflowNode(
        node_id="approved_node",
        subagent="cryer",
        packet_type="cryer_recon",
        approval_policy="always",
    )
    edge = WorkflowEdge(
        edge_id="e2",
        source_node_id="approved_node",
        target_node_id="some_target",
        accepted_packet_types=["cryer_recon"],
        approval_gate="always",
    )
    operator_approval = {"decision": "approved", "reason": "operator signed off"}
    decision = policy.check_approval_required(node, edge, operator_approval=operator_approval)
    assert decision.allowed, "Approval granted should allow execution"
    assert "granted" in decision.reason.lower()
    print("  PASS: Approval needed and granted allows execution")


# ────────────────────────────────────────────────────────
# check_retry_allowed
# ────────────────────────────────────────────────────────

def test_retry_allowed_under_limit():
    """Retry allowed when current count is under max_retries."""
    global FAILED
    policy = WorkflowPolicy()
    node = WorkflowNode(
        node_id="retry_node",
        subagent="knower",
        packet_type="knower_claim_review",
        max_retries=3,
    )
    decision = policy.check_retry_allowed(node, current_retry_count=1)
    assert decision.allowed, "Retry should be allowed when under limit"
    assert "1/3" in decision.reason
    print("  PASS: Retry allowed when under limit")


def test_retry_blocked_at_limit():
    """Retry blocked when current count equals max_retries."""
    global FAILED
    policy = WorkflowPolicy()
    node = WorkflowNode(
        node_id="retry_node",
        subagent="knower",
        packet_type="knower_claim_review",
        max_retries=2,
    )
    decision = policy.check_retry_allowed(node, current_retry_count=2)
    assert not decision.allowed, "Retry should be blocked at limit"
    assert "retry limit reached" in decision.reason.lower()
    print("  PASS: Retry blocked at limit")


def test_retry_blocked_zero_retries():
    """Retry blocked when max_retries=0."""
    global FAILED
    policy = WorkflowPolicy()
    node = WorkflowNode(
        node_id="no_retry_node",
        subagent="knower",
        packet_type="knower_claim_review",
        max_retries=0,
    )
    decision = policy.check_retry_allowed(node, current_retry_count=0)
    assert not decision.allowed, "Retry should be blocked when max_retries=0"
    assert "max_retries=0" in decision.reason
    print("  PASS: Retry blocked when max_retries=0")


# ────────────────────────────────────────────────────────
# check_deterministic_fallback
# ────────────────────────────────────────────────────────

def test_deterministic_fallback_allowed():
    """Deterministic fallback allowed when inference fails and policy permits."""
    global FAILED
    policy = WorkflowPolicy(allow_deterministic_fallback=True)
    node = WorkflowNode(
        node_id="fb_node",
        subagent="knower",
        packet_type="knower_claim_review",
    )
    decision = policy.check_deterministic_fallback(node, inference_failed=True)
    assert decision.allowed, "Fallback should be allowed when inference fails and policy permits"
    assert "inference failed" in decision.reason.lower()
    print("  PASS: Deterministic fallback allowed when inference fails and policy permits")


def test_deterministic_fallback_blocked_by_policy():
    """Deterministic fallback blocked when policy disables it."""
    global FAILED
    policy = WorkflowPolicy(allow_deterministic_fallback=False)
    node = WorkflowNode(
        node_id="fb_node",
        subagent="knower",
        packet_type="knower_claim_review",
    )
    decision = policy.check_deterministic_fallback(node, inference_failed=True)
    assert not decision.allowed, "Fallback should be blocked when policy disables it"
    assert "disabled" in decision.reason.lower()
    print("  PASS: Deterministic fallback blocked when policy disables")


def test_deterministic_fallback_blocked_no_failure():
    """Deterministic fallback blocked when inference didn't fail."""
    global FAILED
    policy = WorkflowPolicy(allow_deterministic_fallback=True)
    node = WorkflowNode(
        node_id="fb_node",
        subagent="knower",
        packet_type="knower_claim_review",
    )
    decision = policy.check_deterministic_fallback(node, inference_failed=False)
    assert not decision.allowed, "Fallback should be blocked when inference didn't fail"
    assert "did not fail" in decision.reason.lower()
    print("  PASS: Deterministic fallback blocked when inference didn't fail")


# ────────────────────────────────────────────────────────
# _check_packet_content_safety
# ────────────────────────────────────────────────────────

def test_forbidden_shell_pattern_rejected():
    """Packet content with forbidden shell pattern is rejected."""
    global FAILED
    policy = WorkflowPolicy()
    node = WorkflowNode(
        node_id="shell_node",
        subagent="knower",
        packet_type="knower_claim_review",
    )
    bad_packet = {
        "packet_type": "knower_claim_review",
        "payload": {"command": "rm -rf /tmp/junk"},
    }
    decision = policy.check_node_execution(
        WorkflowGraph(name="shell_test"),
        node,
        packet=bad_packet,
    )
    assert not decision.allowed, "Forbidden shell pattern should be rejected"
    assert decision.policy_name == "content_safety_shell"
    assert "rm -rf" in decision.reason
    print("  PASS: Forbidden shell pattern in packet content rejected")


def test_forbidden_network_pattern_rejected():
    """Packet content with forbidden network pattern is rejected."""
    global FAILED
    policy = WorkflowPolicy()
    node = WorkflowNode(
        node_id="net_node",
        subagent="knower",
        packet_type="knower_claim_review",
    )
    bad_packet = {
        "packet_type": "knower_claim_review",
        "payload": {"action": "requests.get('http://evil.com/data')"},
    }
    decision = policy.check_node_execution(
        WorkflowGraph(name="net_test"),
        node,
        packet=bad_packet,
    )
    assert not decision.allowed, "Forbidden network pattern should be rejected"
    assert "content_safety_network" in decision.policy_name
    print("  PASS: Forbidden network pattern in packet content rejected")


def test_safe_https_urls_not_flagged():
    """Safe https:// URLs in entity references are not flagged."""
    global FAILED
    policy = WorkflowPolicy()
    node = WorkflowNode(
        node_id="safe_node",
        subagent="knower",
        packet_type="knower_claim_review",
    )
    safe_packet = {
        "packet_type": "knower_claim_review",
        "payload": {
            "source_url": "https://example.com/references/entity-123",
            "entity_id": "entity-123",
        },
    }
    # This should NOT be flagged because the URL is a passive reference,
    # not accompanied by "fetch" or "request" keywords
    decision = policy.check_node_execution(
        WorkflowGraph(name="safe_url_test"),
        node,
        packet=safe_packet,
    )
    assert decision.allowed, f"Safe URL reference should not be flagged: {decision.reason}"
    print("  PASS: Safe URLs (https:// in entity references) not flagged")


def test_active_fetch_with_https_flagged():
    """Active fetch/request with https:// URL IS flagged."""
    global FAILED
    policy = WorkflowPolicy()
    node = WorkflowNode(
        node_id="active_fetch_node",
        subagent="knower",
        packet_type="knower_claim_review",
    )
    dangerous_packet = {
        "packet_type": "knower_claim_review",
        "payload": {
            "action": "fetch data from https://evil.com/api",
        },
    }
    decision = policy.check_node_execution(
        WorkflowGraph(name="active_fetch_test"),
        node,
        packet=dangerous_packet,
    )
    assert not decision.allowed, "Active fetch with URL should be flagged"
    assert "content_safety_network" in decision.policy_name
    print("  PASS: Active fetch with https:// URL flagged as dangerous")


# ────────────────────────────────────────────────────────
# check_full_workflow
# ────────────────────────────────────────────────────────

def test_full_workflow_valid_graph():
    """Full workflow check passes for a valid graph."""
    global FAILED
    policy = WorkflowPolicy()
    graph = WorkflowGraph.knower_to_cryer_workflow()
    graph.build()

    # Provide approvals for nodes that require them
    operator_approvals = {
        "knower_to_cryer": {"decision": "approved", "reason": "test"},
    }
    decision = policy.check_full_workflow(graph, operator_approvals)
    assert decision.allowed, f"Valid graph should pass full check: {decision.reason}"
    assert decision.policy_name == "full_workflow"
    print("  PASS: Full workflow check passes for valid graph")


def test_full_workflow_invalid_node():
    """Full workflow check fails for graph with invalid node."""
    global FAILED
    policy = WorkflowPolicy()
    graph = WorkflowGraph(name="bad_wf")
    # Insert a node with invalid subagent directly (bypassing add_node validation)
    bad_node = WorkflowNode(
        node_id="evil_node",
        subagent="hacker",
        packet_type="knower_claim_review",
    )
    graph.nodes["evil_node"] = bad_node

    decision = policy.check_full_workflow(graph)
    assert not decision.allowed, "Graph with invalid node should fail full check"
    assert "invalid subagent" in decision.reason.lower()
    assert decision.policy_name == "full_workflow"
    print("  PASS: Full workflow check fails for graph with invalid node")


def test_full_workflow_cryer_to_pyper():
    """Full workflow check fails for cryer_to_pyper when approval missing."""
    global FAILED
    policy = WorkflowPolicy()
    graph = WorkflowGraph.cryer_to_pyper_workflow()
    graph.build()

    # Don't provide the required approval for the edge with approval_gate="always"
    decision = policy.check_full_workflow(graph, operator_approvals={})
    assert not decision.allowed, "Should fail without required approval"
    assert "approval" in decision.reason.lower()
    print("  PASS: Full workflow check fails for cryer_to_pyper without approval")


# ────────────────────────────────────────────────────────
# PolicyDecision __bool__ and to_dict
# ────────────────────────────────────────────────────────

def test_policy_decision_bool_and_to_dict():
    """PolicyDecision __bool__ and to_dict work correctly."""
    global FAILED

    # allowed=True
    d1 = PolicyDecision(allowed=True, reason="ok", policy_name="test")
    assert bool(d1) is True
    d1_dict = d1.to_dict()
    assert d1_dict["allowed"] is True
    assert d1_dict["reason"] == "ok"
    assert d1_dict["policy_name"] == "test"
    assert d1_dict["details"] == {}

    # allowed=False
    d2 = PolicyDecision(
        allowed=False,
        reason="blocked",
        policy_name="gate",
        details={"key": "value"},
    )
    assert bool(d2) is False
    d2_dict = d2.to_dict()
    assert d2_dict["allowed"] is False
    assert d2_dict["reason"] == "blocked"
    assert d2_dict["policy_name"] == "gate"
    assert d2_dict["details"] == {"key": "value"}

    # Verify to_dict returns a dict with the correct structure
    # Note: to_dict returns a new dict, but nested dicts share references
    # (standard Python behavior). We verify the values are correct.
    assert d2.to_dict()["details"] == {"key": "value"}
    assert d2.to_dict()["allowed"] is False

    print("  PASS: PolicyDecision __bool__ and to_dict work correctly")


# ────────────────────────────────────────────────────────
# Additional coverage
# ────────────────────────────────────────────────────────

def test_forbidden_shell_pattern_exec():
    """Packet content with 'exec(' shell pattern is rejected."""
    global FAILED
    policy = WorkflowPolicy()
    node = WorkflowNode(
        node_id="exec_node",
        subagent="coder",
        packet_type="coder_completion",
    )
    bad_packet = {
        "packet_type": "coder_completion",
        "payload": {"code": "exec('malicious')"},
    }
    decision = policy.check_node_execution(
        WorkflowGraph(name="exec_test"),
        node,
        packet=bad_packet,
    )
    assert not decision.allowed, "exec( pattern should be rejected"
    assert decision.policy_name == "content_safety_shell"
    print("  PASS: Forbidden shell pattern 'exec(' rejected")


def test_forbidden_shell_pattern_subprocess():
    """Packet content with 'subprocess.Popen' pattern is rejected."""
    global FAILED
    policy = WorkflowPolicy()
    node = WorkflowNode(
        node_id="subproc_node",
        subagent="coder",
        packet_type="coder_blocked",
    )
    bad_packet = {
        "packet_type": "coder_blocked",
        "payload": {"code": "subprocess.Popen(['rm', '-rf', '/'])"},
    }
    decision = policy.check_node_execution(
        WorkflowGraph(name="subproc_test"),
        node,
        packet=bad_packet,
    )
    assert not decision.allowed, "subprocess.Popen pattern should be rejected"
    assert decision.policy_name == "content_safety_shell"
    print("  PASS: Forbidden shell pattern 'subprocess.Popen' rejected")


def test_forbidden_network_pattern_socket():
    """Packet content with 'socket.connect' pattern is rejected."""
    global FAILED
    policy = WorkflowPolicy()
    node = WorkflowNode(
        node_id="socket_node",
        subagent="knower",
        packet_type="knower_research",
    )
    bad_packet = {
        "packet_type": "knower_research",
        "payload": {"action": "socket.connect(('evil.com', 8080))"},
    }
    decision = policy.check_node_execution(
        WorkflowGraph(name="socket_test"),
        node,
        packet=bad_packet,
    )
    assert not decision.allowed, "socket.connect pattern should be rejected"
    assert decision.policy_name == "content_safety_network"
    print("  PASS: Forbidden network pattern 'socket.connect' rejected")


def test_forbidden_network_pattern_http():
    """Packet content with 'http://' pattern accompanied by request/fetch is flagged."""
    global FAILED
    policy = WorkflowPolicy()
    node = WorkflowNode(
        node_id="http_node",
        subagent="knower",
        packet_type="knower_research",
    )
    bad_packet = {
        "packet_type": "knower_research",
        "payload": {"action": "request from http://evil.com/data"},
    }
    decision = policy.check_node_execution(
        WorkflowGraph(name="http_test"),
        node,
        packet=bad_packet,
    )
    assert not decision.allowed, "http:// with request should be flagged"
    assert decision.policy_name == "content_safety_network"
    print("  PASS: Forbidden network pattern 'http://' with request flagged")


def test_safe_packet_content_allowed():
    """Safe packet content with no forbidden patterns is allowed."""
    global FAILED
    policy = WorkflowPolicy()
    graph = WorkflowGraph.knower_to_cryer_workflow()
    node = graph.nodes["knower_classify"]

    safe_packet = {
        "packet_type": "knower_claim_review",
        "version": "1.0",
        "source": "knower",
        "target": "overcr",
        "payload": {
            "summary": "Claims are classified as verified",
            "claims": ["Sky is blue", "Water is wet"],
        },
    }
    decision = policy.check_node_execution(graph, node, packet=safe_packet)
    assert decision.allowed, f"Safe packet should be allowed: {decision.reason}"
    print("  PASS: Safe packet content with no forbidden patterns allowed")


def test_edge_handoff_same_subagent():
    """Edge handoff between nodes of the same subagent is allowed (internal edge)."""
    global FAILED
    policy = WorkflowPolicy()
    graph = WorkflowGraph(name="same_subagent_test")
    node_a = WorkflowNode(
        node_id="knower_a",
        subagent="knower",
        packet_type="knower_claim_review",
    )
    node_b = WorkflowNode(
        node_id="knower_b",
        subagent="knower",
        packet_type="knower_assessment",
    )
    graph.nodes["knower_a"] = node_a
    graph.nodes["knower_b"] = node_b

    edge = WorkflowEdge(
        edge_id="internal_edge",
        source_node_id="knower_a",
        target_node_id="knower_b",
        accepted_packet_types=["knower_claim_review"],
    )
    graph.edges["internal_edge"] = edge

    decision = policy.check_edge_handoff(graph, edge)
    assert decision.allowed, f"Same-subagent edge handoff should be allowed: {decision.reason}"
    print("  PASS: Same-subagent edge handoff allowed")


def test_retry_with_last_error():
    """Retry decision includes last_error in details when provided."""
    global FAILED
    policy = WorkflowPolicy()
    node = WorkflowNode(
        node_id="retry_err_node",
        subagent="knower",
        packet_type="knower_claim_review",
        max_retries=2,
    )
    decision = policy.check_retry_allowed(
        node, current_retry_count=2, last_error="timeout"
    )
    assert not decision.allowed
    assert decision.details.get("last_error") == "timeout"
    print("  PASS: Retry decision includes last_error in details")


def test_approval_required_node_only():
    """Approval required check with only node (no edge)."""
    global FAILED
    policy = WorkflowPolicy()
    node = WorkflowNode(
        node_id="approval_node",
        subagent="cryer",
        packet_type="cryer_recon",
        approval_policy="always",
    )
    # Without operator approval
    decision = policy.check_approval_required(node)
    assert not decision.allowed, "Node with approval_policy=always should require approval"
    # With operator approval
    approval = {"decision": "approved", "reason": "ok"}
    decision2 = policy.check_approval_required(node, operator_approval=approval)
    assert decision2.allowed, "Approved node should be allowed"
    print("  PASS: Approval required check with node only (no edge)")


def test_approval_required_edge_only():
    """Approval required check with node approval_policy=never but edge approval_gate=always."""
    global FAILED
    policy = WorkflowPolicy()
    node = WorkflowNode(
        node_id="free_node",
        subagent="knower",
        packet_type="knower_claim_review",
        approval_policy="never",
    )
    edge = WorkflowEdge(
        edge_id="gated_edge",
        source_node_id="free_node",
        target_node_id="some_target",
        accepted_packet_types=["knower_claim_review"],
        approval_gate="always",
    )
    # No approval
    decision = policy.check_approval_required(node, edge)
    assert not decision.allowed, "Edge with approval_gate=always should require approval"
    # With approval
    approval = {"decision": "approved", "reason": "signed off"}
    decision2 = policy.check_approval_required(node, edge, operator_approval=approval)
    assert decision2.allowed, "Approved edge should be allowed"
    print("  PASS: Approval required check with edge gate (node policy=never)")


def test_full_workflow_coder_to_pyper():
    """Full workflow check on coder_to_pyper graph (needs approval on edge)."""
    global FAILED
    policy = WorkflowPolicy()
    graph = WorkflowGraph.coder_to_pyper_workflow()
    graph.build()

    # coder_to_pyper edge has approval_gate="always", so we need approval
    approvals = {
        "coder_to_pyper": {"decision": "approved", "reason": "test"},
    }
    decision = policy.check_full_workflow(graph, operator_approvals=approvals)
    assert decision.allowed, f"Valid coder_to_pyper graph should pass: {decision.reason}"
    print("  PASS: Full workflow check passes for coder_to_pyper with approval")


def test_node_execution_with_null_packet():
    """Node execution check with no packet (None) passes content safety."""
    global FAILED
    policy = WorkflowPolicy()
    graph = WorkflowGraph.knower_to_cryer_workflow()
    node = graph.nodes["knower_classify"]

    decision = policy.check_node_execution(graph, node, packet=None)
    assert decision.allowed, f"Node with no packet should pass: {decision.reason}"
    print("  PASS: Node execution with null packet passes content safety")


def test_edge_handoff_no_source_packet():
    """Edge handoff check with no source_packet skips packet type compatibility."""
    global FAILED
    policy = WorkflowPolicy()
    graph = WorkflowGraph.knower_to_cryer_workflow()
    edge = graph.edges["knower_to_cryer"]

    decision = policy.check_edge_handoff(graph, edge, source_packet=None)
    assert decision.allowed, f"Edge with no source_packet should pass: {decision.reason}"
    print("  PASS: Edge handoff with no source packet passes")


# ────────────────────────────────────────────────────────
# Main
# ────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("OverCR v0.8.0 — Test: Workflow Policy")
    print("=" * 60)
    print()

    tests = [
        # check_node_execution
        test_node_execution_allowed,
        test_invalid_subagent_rejected,
        test_invalid_packet_type_for_subagent_rejected,
        # check_edge_handoff
        test_edge_handoff_allowed,
        test_edge_handoff_invalid_sovereignty,
        test_edge_missing_nodes_rejected,
        test_edge_packet_type_not_accepted,
        test_edge_handoff_same_subagent,
        # check_approval_required
        test_approval_not_needed_never,
        test_approval_needed_not_granted,
        test_approval_needed_and_granted,
        test_approval_required_node_only,
        test_approval_required_edge_only,
        # check_retry_allowed
        test_retry_allowed_under_limit,
        test_retry_blocked_at_limit,
        test_retry_blocked_zero_retries,
        test_retry_with_last_error,
        # check_deterministic_fallback
        test_deterministic_fallback_allowed,
        test_deterministic_fallback_blocked_by_policy,
        test_deterministic_fallback_blocked_no_failure,
        # _check_packet_content_safety
        test_forbidden_shell_pattern_rejected,
        test_forbidden_network_pattern_rejected,
        test_safe_https_urls_not_flagged,
        test_active_fetch_with_https_flagged,
        test_forbidden_shell_pattern_exec,
        test_forbidden_shell_pattern_subprocess,
        test_forbidden_network_pattern_socket,
        test_forbidden_network_pattern_http,
        test_safe_packet_content_allowed,
        # check_full_workflow
        test_full_workflow_valid_graph,
        test_full_workflow_invalid_node,
        test_full_workflow_cryer_to_pyper,
        test_full_workflow_coder_to_pyper,
        # PolicyDecision
        test_policy_decision_bool_and_to_dict,
        # Additional
        test_node_execution_with_null_packet,
        test_edge_handoff_no_source_packet,
    ]

    passed = 0
    for test_fn in tests:
        try:
            test_fn()
            passed += 1
        except Exception as e:
            print(f"  FAIL: {test_fn.__name__}: {e}")
            import traceback
            traceback.print_exc()
            global FAILED
            FAILED = True

    print()
    print(f"Results: {passed}/{len(tests)} tests passed")
    if FAILED:
        print("OVERALL: FAIL")
        return 1
    else:
        print("OVERALL: PASS")
        return 0


if __name__ == "__main__":
    sys.exit(main())