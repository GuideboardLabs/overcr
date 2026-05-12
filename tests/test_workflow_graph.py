#!/usr/bin/env python3
"""
OverCR v0.8.0 — Test: Workflow Graph

Tests the WorkflowGraph DAG model including:
  - Node and edge validation
  - Cycle detection
  - DAG integrity
  - Sovereignty (no direct subagent routing)
  - Packet type compatibility
  - Serialization/deserialization
  - Factory methods for demo workflows
  - Edge cases and error conditions
"""

import json
import sys
from pathlib import Path

OVERCR_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(OVERCR_ROOT))

from runtime.workflow_graph import (
    WorkflowGraph, WorkflowNode, WorkflowEdge,
    VALID_SUBAGENTS, ALL_PACKET_TYPES, VALID_HANDOFF_PATHS,
    PACKET_TYPES_BY_SUBAGENT,
)

FAILED = False


def test_node_validation():
    """Test WorkflowNode validation."""
    global FAILED

    # Valid node
    node = WorkflowNode(
        node_id="test_knower",
        subagent="knower",
        packet_type="knower_claim_review",
        input_requirements=["claims"],
        output_requirements=["assessment"],
        approval_policy="always",
        max_retries=1,
        timeout_s=30.0,
    )
    valid, errors = node.validate()
    assert valid, f"Valid node failed: {errors}"

    # Invalid subagent
    node2 = WorkflowNode(
        node_id="bad_subagent",
        subagent="invalid_agent",
        packet_type="knower_claim_review",
        approval_policy="always",
    )
    valid, errors = node2.validate()
    assert not valid, "Invalid subagent should fail"
    assert any("invalid subagent" in e for e in errors)

    # Invalid packet_type for subagent
    node3 = WorkflowNode(
        node_id="wrong_packet",
        subagent="knower",
        packet_type="cryer_recon",  # CryER packet type on KnowER
        approval_policy="always",
    )
    valid, errors = node3.validate()
    assert not valid, "Wrong packet type for subagent should fail"

    # Invalid approval policy
    node4 = WorkflowNode(
        node_id="bad_policy",
        subagent="knower",
        packet_type="knower_claim_review",
        approval_policy="invalid",
    )
    valid, errors = node4.validate()
    assert not valid, "Invalid approval policy should fail"

    # Negative max_retries
    node5 = WorkflowNode(
        node_id="neg_retry",
        subagent="knower",
        packet_type="knower_claim_review",
        max_retries=-1,
    )
    valid, errors = node5.validate()
    assert not valid, "Negative max_retries should fail"

    print("  PASS: Node validation")


def test_edge_validation():
    """Test WorkflowEdge validation."""
    global FAILED

    # Valid edge
    edge = WorkflowEdge(
        edge_id="e1",
        source_node_id="n1",
        target_node_id="n2",
        accepted_packet_types=["knower_claim_review"],
    )
    valid, errors = edge.validate({"n1", "n2"})
    assert valid, f"Valid edge failed: {errors}"

    # Self-loop
    edge2 = WorkflowEdge(
        edge_id="e2",
        source_node_id="n1",
        target_node_id="n1",
        accepted_packet_types=["knower_claim_review"],
    )
    valid, errors = edge2.validate({"n1"})
    assert not valid, "Self-loop should fail"
    assert any("self-loop" in e for e in errors)

    # Missing source node
    edge3 = WorkflowEdge(
        edge_id="e3",
        source_node_id="missing",
        target_node_id="n1",
        accepted_packet_types=["knower_claim_review"],
    )
    valid, errors = edge3.validate({"n1"})
    assert not valid, "Missing source node should fail"

    # Empty accepted_packet_types
    edge4 = WorkflowEdge(
        edge_id="e4",
        source_node_id="n1",
        target_node_id="n2",
        accepted_packet_types=[],
    )
    valid, errors = edge4.validate({"n1", "n2"})
    assert not valid, "Empty accepted_packet_types should fail"

    # Invalid packet type in accepted types
    edge5 = WorkflowEdge(
        edge_id="e5",
        source_node_id="n1",
        target_node_id="n2",
        accepted_packet_types=["invalid_packet_type"],
    )
    valid, errors = edge5.validate({"n1", "n2"})
    assert not valid, "Invalid packet type in edge should fail"

    print("  PASS: Edge validation")


def test_graph_build_valid():
    """Test building a valid workflow graph."""
    graph = WorkflowGraph(name="test_graph")
    graph.add_node(WorkflowNode(
        node_id="knower_1",
        subagent="knower",
        packet_type="knower_claim_review",
        approval_policy="on_failure",
        max_retries=1,
    ))
    graph.add_node(WorkflowNode(
        node_id="cryer_1",
        subagent="cryer",
        packet_type="cryer_recon",
        approval_policy="always",
        max_retries=1,
    ))
    graph.add_edge(WorkflowEdge(
        edge_id="k2c",
        source_node_id="knower_1",
        target_node_id="cryer_1",
        accepted_packet_types=["knower_claim_review"],
    ))

    valid, errors = graph.build()
    assert valid, f"Valid graph build failed: {errors}"
    assert graph._built
    print("  PASS: Valid graph build")


def test_graph_cycle_detection():
    """Test cycle detection in graphs."""
    graph = WorkflowGraph(name="cycle_test")
    graph.add_node(WorkflowNode(
        node_id="a", subagent="knower", packet_type="knower_claim_review",
    ))
    graph.add_node(WorkflowNode(
        node_id="b", subagent="cryer", packet_type="cryer_recon",
    ))
    graph.add_edge(WorkflowEdge(
        edge_id="a2b",
        source_node_id="a",
        target_node_id="b",
        accepted_packet_types=["knower_claim_review"],
    ))
    graph.add_edge(WorkflowEdge(
        edge_id="b2a",
        source_node_id="b",
        target_node_id="a",
        accepted_packet_types=["cryer_recon"],
    ))

    valid, errors = graph.build()
    assert not valid, "Cyclic graph should fail validation"
    assert any("cycle" in e.lower() for e in errors)
    print("  PASS: Cycle detection")


def test_graph_sovereignty():
    """Test that direct subagent routing is rejected."""
    # Create a graph with an invalid handoff path
    graph = WorkflowGraph(name="sovereignty_test")
    graph.add_node(WorkflowNode(
        node_id="pyper_1",
        subagent="pyper",
        packet_type="pyper_execution_plan",
    ))
    graph.add_node(WorkflowNode(
        node_id="knower_1",
        subagent="knower",
        packet_type="knower_claim_review",
    ))
    # pyper -> knower is NOT a valid handoff path
    graph.add_edge(WorkflowEdge(
        edge_id="p2k",
        source_node_id="pyper_1",
        target_node_id="knower_1",
        accepted_packet_types=["pyper_execution_plan"],
    ))

    valid, errors = graph.build()
    assert not valid, "Invalid handoff path should fail"
    assert any("invalid handoff" in e.lower() or "sovereignty" in e.lower()
               for e in errors)
    print("  PASS: Sovereignty enforcement")


def test_graph_packet_type_compatibility():
    """Test packet type compatibility on edges."""
    graph = WorkflowGraph(name="type_compat_test")
    graph.add_node(WorkflowNode(
        node_id="knower_1",
        subagent="knower",
        packet_type="knower_claim_review",
    ))
    graph.add_node(WorkflowNode(
        node_id="cryer_1",
        subagent="cryer",
        packet_type="cryer_recon",
    ))
    # Edge accepts wrong packet type (source produces knower_claim_review,
    # but edge only accepts cryer_recon)
    graph.add_edge(WorkflowEdge(
        edge_id="bad_edge",
        source_node_id="knower_1",
        target_node_id="cryer_1",
        accepted_packet_types=["cryer_recon"],  # Wrong! Source produces knower_claim_review
    ))

    valid, errors = graph.build()
    assert not valid, "Incompatible packet type on edge should fail"
    print("  PASS: Packet type compatibility enforcement")


def test_graph_empty():
    """Test that empty graph is rejected."""
    graph = WorkflowGraph(name="empty")
    valid, errors = graph.build()
    assert not valid, "Empty graph should fail"
    assert any("no nodes" in e.lower() for e in errors)
    print("  PASS: Empty graph rejected")


def test_graph_duplicate_node():
    """Test that duplicate node IDs are rejected."""
    graph = WorkflowGraph(name="dup_node")
    graph.add_node(WorkflowNode(
        node_id="dup", subagent="knower", packet_type="knower_claim_review",
    ))
    try:
        graph.add_node(WorkflowNode(
            node_id="dup", subagent="knower", packet_type="knower_assessment",
        ))
        assert False, "Duplicate node_id should raise ValueError"
    except ValueError:
        pass
    print("  PASS: Duplicate node ID rejected")


def test_topological_order():
    """Test topological ordering of nodes."""
    graph = WorkflowGraph(name="topo_test")
    graph.add_node(WorkflowNode(
        node_id="a", subagent="knower", packet_type="knower_claim_review",
    ))
    graph.add_node(WorkflowNode(
        node_id="b", subagent="cryer", packet_type="cryer_recon",
    ))
    graph.add_node(WorkflowNode(
        node_id="c", subagent="pyper", packet_type="pyper_execution_plan",
    ))
    graph.add_edge(WorkflowEdge(
        edge_id="a2b",
        source_node_id="a", target_node_id="b",
        accepted_packet_types=["knower_claim_review"],
    ))
    graph.add_edge(WorkflowEdge(
        edge_id="b2c",
        source_node_id="b", target_node_id="c",
        accepted_packet_types=["cryer_recon"],
    ))

    # Note: knower->cryer and cryer->pyper are valid handoffs
    valid, errors = graph.build()
    assert valid, f"Graph build failed: {errors}"

    order = graph.topological_order()
    assert order.index("a") < order.index("b"), "a must come before b"
    assert order.index("b") < order.index("c"), "b must come before c"
    print("  PASS: Topological order")


def test_serialization():
    """Test JSON serialization and deserialization."""
    graph = WorkflowGraph.knower_to_cryer_workflow(name="ser_test")
    graph.build()

    json_str = graph.to_json()
    graph2 = WorkflowGraph.from_json(json_str)

    assert graph2.workflow_id == graph.workflow_id
    assert graph2.name == graph.name
    assert graph2.version == graph.version
    assert set(graph2.nodes.keys()) == set(graph.nodes.keys())
    assert set(graph2.edges.keys()) == set(graph.edges.keys())

    # Verify node fields survive round-trip
    for nid in graph.nodes:
        n1 = graph.nodes[nid]
        n2 = graph2.nodes[nid]
        assert n1.subagent == n2.subagent
        assert n1.packet_type == n2.packet_type
        assert n1.approval_policy == n2.approval_policy
        assert n1.max_retries == n2.max_retries
        assert n1.timeout_s == n2.timeout_s

    # Verify edge fields survive round-trip
    for eid in graph.edges:
        e1 = graph.edges[eid]
        e2 = graph2.edges[eid]
        assert e1.source_node_id == e2.source_node_id
        assert e1.target_node_id == e2.target_node_id
        assert e1.accepted_packet_types == e2.accepted_packet_types
        assert e1.transformation_rule == e2.transformation_rule
        assert e1.approval_gate == e2.approval_gate

    print("  PASS: Serialization round-trip")


def test_factory_knower_to_cryer():
    """Test the KnowER → CryER factory method."""
    graph = WorkflowGraph.knower_to_cryer_workflow()
    valid, errors = graph.build()
    assert valid, f"Factory graph build failed: {errors}"
    assert len(graph.nodes) == 2
    assert len(graph.edges) == 1
    assert "knower_classify" in graph.nodes
    assert "cryer_recon" in graph.nodes
    print("  PASS: KnowER -> CryER factory")


def test_factory_cryer_to_pyper():
    """Test the CryER → PypER factory method."""
    graph = WorkflowGraph.cryer_to_pyper_workflow()
    valid, errors = graph.build()
    assert valid, f"Factory graph build failed: {errors}"
    assert len(graph.nodes) == 2
    assert len(graph.edges) == 1
    assert "cryer_signal" in graph.nodes
    assert "pyper_plan" in graph.nodes
    print("  PASS: CryER -> PypER factory")


def test_factory_coder_to_pyper():
    """Test the CodER → PypER factory method."""
    graph = WorkflowGraph.coder_to_pyper_workflow()
    valid, errors = graph.build()
    assert valid, f"Factory graph build failed: {errors}"
    assert len(graph.nodes) == 2
    assert len(graph.edges) == 1
    assert "coder_patch" in graph.nodes
    assert "pyper_simulate" in graph.nodes
    print("  PASS: CodER -> PypER factory")


def test_roots_and_leaves():
    """Test root and leaf node detection."""
    graph = WorkflowGraph.knower_to_cryer_workflow()
    graph.build()
    roots = graph._find_roots()
    leaves = graph._find_leaves()
    assert "knower_classify" in roots, "KnowER should be root"
    assert "cryer_recon" in leaves, "CryER should be leaf"
    print("  PASS: Roots and leaves detection")


def test_edge_queries():
    """Test edge query methods."""
    graph = WorkflowGraph.knower_to_cryer_workflow()
    graph.build()
    from_knower = graph.edges_from("knower_classify")
    to_cryer = graph.edges_to("cryer_recon")
    assert len(from_knower) == 1
    assert len(to_cryer) == 1
    assert from_knower[0].edge_id == to_cryer[0].edge_id
    preds = graph.predecessor_nodes("cryer_recon")
    succs = graph.successor_nodes("knower_classify")
    assert preds == ["knower_classify"]
    assert succs == ["cryer_recon"]
    print("  PASS: Edge queries")


def main():
    print("=" * 60)
    print("OverCR v0.8.0 — Test: Workflow Graph")
    print("=" * 60)
    print()

    tests = [
        test_node_validation,
        test_edge_validation,
        test_graph_build_valid,
        test_graph_cycle_detection,
        test_graph_sovereignty,
        test_graph_packet_type_compatibility,
        test_graph_empty,
        test_graph_duplicate_node,
        test_topological_order,
        test_serialization,
        test_factory_knower_to_cryer,
        test_factory_cryer_to_pyper,
        test_factory_coder_to_pyper,
        test_roots_and_leaves,
        test_edge_queries,
    ]

    passed = 0
    for test_fn in tests:
        try:
            test_fn()
            passed += 1
        except Exception as e:
            print(f"  FAIL: {test_fn.__name__}: {e}")
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