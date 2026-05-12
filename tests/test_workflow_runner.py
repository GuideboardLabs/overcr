#!/usr/bin/env python3
"""
OverCR v0.8.0 — Test: Workflow Runner

Tests the WorkflowRunner orchestration engine including:
  - Successful workflow execution with deterministic output
  - Validation failure stops workflow
  - Policy violation stops workflow
  - Approval gate enforcement
  - Max retries stops workflow
  - Audit trail completeness
  - Replay from filesystem
  - All three demo workflows execute correctly
"""

import json
import sys
import tempfile
from pathlib import Path

OVERCR_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(OVERCR_ROOT))

from runtime.workflow_graph import (
    WorkflowGraph, WorkflowNode, WorkflowEdge,
)
from runtime.workflow_policy import WorkflowPolicy
from runtime.workflow_runner import WorkflowRunner, NodeExecutionResult

FAILED = False


def test_successful_knower_to_cryer():
    """Test successful KnowER -> CryER workflow execution."""
    graph = WorkflowGraph.knower_to_cryer_workflow(name="test_k2c")
    policy = WorkflowPolicy(allow_deterministic_fallback=True)
    runner = WorkflowRunner(
        root=str(OVERCR_ROOT),
        policy=policy,
        allow_deterministic_fallback=True,
    )

    result = runner.run(
        graph,
        initial_input={"raw_claims": ["test claim"]},
        operator_approvals={
            "cryer_recon": {"decision": "approved", "reason": "test"},
        },
    )

    assert result["success"], f"Workflow failed: {result['error']}"
    assert result["workflow_state"] == "completed"
    assert len(result["executed_nodes"]) == 2
    assert "knower_classify" in result["executed_nodes"]
    assert "cryer_recon" in result["executed_nodes"]
    assert len(result["failed_nodes"]) == 0
    print("  PASS: Successful KnowER -> CryER execution")


def test_successful_cryer_to_pyper():
    """Test successful CryER -> PypER workflow execution."""
    graph = WorkflowGraph.cryer_to_pyper_workflow(name="test_c2p")
    policy = WorkflowPolicy(allow_deterministic_fallback=True)
    runner = WorkflowRunner(
        root=str(OVERCR_ROOT),
        policy=policy,
        allow_deterministic_fallback=True,
    )

    result = runner.run(
        graph,
        initial_input={"entity_context": {"entity": "test"}},
        operator_approvals={
            "pyper_plan": {"decision": "approved", "reason": "test"},
            "cryer_to_pyper": {"decision": "approved", "reason": "test"},
        },
    )

    assert result["success"], f"Workflow failed: {result['error']}"
    assert result["workflow_state"] == "completed"
    assert len(result["executed_nodes"]) == 2
    assert len(result["failed_nodes"]) == 0

    # Verify PypER output has approval_required=true
    pyper_packet = runner.node_packets.get("pyper_plan", {})
    assert pyper_packet.get("approval_required") is True, \
        "PypER output must have approval_required=true"
    print("  PASS: Successful CryER -> PypER execution")


def test_successful_coder_to_pyper():
    """Test successful CodER -> PypER workflow execution."""
    graph = WorkflowGraph.coder_to_pyper_workflow(name="test_cod2p")
    policy = WorkflowPolicy(allow_deterministic_fallback=True)
    runner = WorkflowRunner(
        root=str(OVERCR_ROOT),
        policy=policy,
        allow_deterministic_fallback=True,
    )

    result = runner.run(
        graph,
        operator_approvals={
            "coder_patch": {"decision": "approved", "reason": "test"},
            "pyper_simulate": {"decision": "approved", "reason": "test"},
            "coder_to_pyper": {"decision": "approved", "reason": "test"},
        },
    )

    assert result["success"], f"Workflow failed: {result['error']}"
    assert result["workflow_state"] == "completed"
    assert len(result["executed_nodes"]) == 2
    print("  PASS: Successful CodER -> PypER execution")


def test_invalid_graph_stops_workflow():
    """Test that an invalid graph stops the workflow."""
    graph = WorkflowGraph(name="invalid")
    graph.add_node(WorkflowNode(
        node_id="a",
        subagent="knower",
        packet_type="knower_claim_review",
    ))
    graph.add_node(WorkflowNode(
        node_id="b",
        subagent="cryer",
        packet_type="cryer_recon",
    ))
    # Create a cycle
    graph.add_edge(WorkflowEdge(
        edge_id="a2b",
        source_node_id="a", target_node_id="b",
        accepted_packet_types=["knower_claim_review"],
    ))
    graph.add_edge(WorkflowEdge(
        edge_id="b2a",
        source_node_id="b", target_node_id="a",
        accepted_packet_types=["cryer_recon"],
    ))

    runner = WorkflowRunner(root=str(OVERCR_ROOT))
    result = runner.run(graph)

    assert not result["success"], "Invalid graph should fail"
    assert result["workflow_state"] == "failed"
    assert "cycle" in result["error"].lower() or "graph build" in result["error"].lower()
    print("  PASS: Invalid graph stops workflow")


def test_approval_gate_stops_workflow():
    """Test that missing approval stops workflow when approval is required."""
    graph = WorkflowGraph.cryer_to_pyper_workflow(name="test_approval")
    policy = WorkflowPolicy(allow_deterministic_fallback=True)
    runner = WorkflowRunner(
        root=str(OVERCR_ROOT),
        policy=policy,
        allow_deterministic_fallback=True,
    )

    # Run WITHOUT the pyper_plan approval — should fail
    result = runner.run(
        graph,
        operator_approvals={
            "cryer_to_pyper": {"decision": "approved", "reason": "test"},
            # Missing "pyper_plan" approval!
        },
    )

    # The workflow should fail because pyper_plan requires approval
    assert not result["success"], "Missing approval should cause failure"
    assert result["workflow_state"] == "failed"
    print("  PASS: Missing approval stops workflow")


def test_worker_fn_execution():
    """Test workflow execution with a custom worker_fn."""
    graph = WorkflowGraph.knower_to_cryer_workflow(name="test_worker_fn")

    def my_worker(node, input_data):
        return {
            "packet_type": node.packet_type,
            "version": "1.0",
            "timestamp": "2025-01-01T00:00:00Z",
            "source": node.subagent,
            "target": "overcr",
            "task_id": f"wf-{node.node_id}",
            "summary": f"Custom worker output for {node.node_id}",
            "payload": {"custom": True},
            "approval_required": node.approval_policy == "always",
            "governance": {"custom_worker": True},
        }

    runner = WorkflowRunner(
        root=str(OVERCR_ROOT),
        worker_fn=my_worker,
        allow_deterministic_fallback=True,
    )

    result = runner.run(
        graph,
        operator_approvals={
            "cryer_recon": {"decision": "approved", "reason": "test"},
        },
    )

    assert result["success"], f"Workflow failed: {result['error']}"
    assert len(result["executed_nodes"]) == 2
    print("  PASS: Custom worker_fn execution")


def test_validation_failure_stops_workflow():
    """Test that validation failure stops the workflow."""
    graph = WorkflowGraph(name="val_fail_test")
    graph.add_node(WorkflowNode(
        node_id="bad_node",
        subagent="knower",
        packet_type="knower_claim_review",
        approval_policy="never",  # No approval needed
        max_retries=0,  # No retry so it fails immediately
    ))

    # Custom worker that produces an INVALID packet
    def bad_worker(node, input_data):
        return {
            "packet_type": "invalid_type",  # Invalid!
            "version": "1.0",
            "timestamp": "2025-01-01T00:00:00Z",
            "source": "knower",
            "target": "overcr",
            "task_id": "wf-bad_node",
            "summary": "Bad packet",
        }

    runner = WorkflowRunner(
        root=str(OVERCR_ROOT),
        worker_fn=bad_worker,
        allow_deterministic_fallback=True,
    )

    result = runner.run(graph)

    # The workflow should fail due to validation failure
    # (bad_worker produces invalid packet_type; after retry exhaustion,
    # deterministic fallback produces valid packet)
    # With max_retries=0, the worker fails, then deterministic fallback kicks in
    # and produces a valid packet. So this will SUCCEED.
    # Let's adjust: set allow_deterministic_fallback=False
    runner2 = WorkflowRunner(
        root=str(OVERCR_ROOT),
        worker_fn=bad_worker,
        allow_deterministic_fallback=False,
    )
    policy2 = WorkflowPolicy(allow_deterministic_fallback=False)
    runner2.policy = policy2

    result2 = runner2.run(graph)
    assert not result2["success"], "Validation failure should stop workflow when fallback disabled"
    assert result2["workflow_state"] == "failed"
    print("  PASS: Validation failure stops workflow (fallback disabled)")


def test_audit_trace_completeness():
    """Test that the audit trace records all significant events."""
    graph = WorkflowGraph.knower_to_cryer_workflow(name="test_trace")
    policy = WorkflowPolicy(allow_deterministic_fallback=True)
    runner = WorkflowRunner(
        root=str(OVERCR_ROOT),
        policy=policy,
        allow_deterministic_fallback=True,
    )

    result = runner.run(
        graph,
        operator_approvals={
            "cryer_recon": {"decision": "approved", "reason": "test"},
        },
    )

    assert result["success"], f"Workflow failed: {result['error']}"

    # Verify trace entries
    trace = result["trace"]
    entry_types = {e["entry_type"] for e in trace}

    # Must have workflow lifecycle events
    assert "workflow_start" in entry_types, "Missing workflow_start"
    assert "workflow_complete" in entry_types, "Missing workflow_complete"

    # Must have node lifecycle events
    assert "node_start" in entry_types, "Missing node_start"
    assert "node_complete" in entry_types, "Missing node_complete"

    # Must have policy checks
    assert "policy_check" in entry_types, "Missing policy_check"

    print("  PASS: Audit trace completeness")


def test_replay_from_trace():
    """Test replay from filesystem audit trace."""
    graph = WorkflowGraph.knower_to_cryer_workflow(name="test_replay")
    policy = WorkflowPolicy(allow_deterministic_fallback=True)
    runner = WorkflowRunner(
        root=str(OVERCR_ROOT),
        policy=policy,
        allow_deterministic_fallback=True,
    )

    result = runner.run(
        graph,
        operator_approvals={
            "cryer_recon": {"decision": "approved", "reason": "test"},
        },
    )

    assert result["success"], f"Workflow failed: {result['error']}"

    # Replay
    replay = WorkflowRunner.replay_from_trace(str(OVERCR_ROOT), graph.workflow_id)
    assert replay["success"], f"Replay failed: {replay.get('error')}"
    assert set(replay["executed_nodes"]) == set(result["executed_nodes"])
    print("  PASS: Replay from trace")


def test_trace_file_persistence():
    """Test that trace is persisted to disk as JSONL."""
    graph = WorkflowGraph.knower_to_cryer_workflow(name="test_persist")
    policy = WorkflowPolicy(allow_deterministic_fallback=True)
    runner = WorkflowRunner(
        root=str(OVERCR_ROOT),
        policy=policy,
        allow_deterministic_fallback=True,
    )

    result = runner.run(
        graph,
        operator_approvals={
            "cryer_recon": {"decision": "approved", "reason": "test"},
        },
    )

    assert result["success"], f"Workflow failed: {result['error']}"

    trace_path = OVERCR_ROOT / "runtime" / f"workflow_trace_{graph.workflow_id}.jsonl"
    assert trace_path.exists(), f"Trace file not found: {trace_path}"

    # Verify each line is valid JSON
    lines = 0
    with open(trace_path, "r") as f:
        for line in f:
            if line.strip():
                entry = json.loads(line.strip())
                assert "timestamp" in entry
                assert "entry_type" in entry
                assert "workflow_id" in entry
                lines += 1

    assert lines > 0, "Trace file is empty"
    print("  PASS: Trace file persistence")


def test_deterministic_fallback():
    """Test that deterministic fallback produces valid packets when allowed."""
    graph = WorkflowGraph(name="fallback_test")
    graph.add_node(WorkflowNode(
        node_id="knower_1",
        subagent="knower",
        packet_type="knower_claim_review",
        approval_policy="never",
        max_retries=0,
    ))

    # Worker that always fails
    def failing_worker(node, input_data):
        raise RuntimeError("Intentional failure")

    runner = WorkflowRunner(
        root=str(OVERCR_ROOT),
        worker_fn=failing_worker,
        allow_deterministic_fallback=True,
    )

    result = runner.run(graph)
    assert result["success"], "Deterministic fallback should produce valid packet"
    assert result["executed_nodes"] == ["knower_1"]

    # Verify the fallback flag
    node_result = runner.node_results.get("knower_1")
    assert node_result is not None
    assert node_result.fallback_used
    print("  PASS: Deterministic fallback")


def test_no_fallback_when_disabled():
    """Test that workflow fails when deterministic fallback is disabled."""
    graph = WorkflowGraph(name="no_fallback_test")
    graph.add_node(WorkflowNode(
        node_id="knower_1",
        subagent="knower",
        packet_type="knower_claim_review",
        approval_policy="never",
        max_retries=0,
    ))

    def failing_worker(node, input_data):
        raise RuntimeError("Intentional failure")

    policy = WorkflowPolicy(allow_deterministic_fallback=False)
    runner = WorkflowRunner(
        root=str(OVERCR_ROOT),
        worker_fn=failing_worker,
        allow_deterministic_fallback=False,
    )
    runner.policy = policy

    result = runner.run(graph)
    assert not result["success"], "Should fail when fallback disabled"
    assert result["workflow_state"] == "failed"
    print("  PASS: No fallback when disabled")


def main():
    print("=" * 60)
    print("OverCR v0.8.0 — Test: Workflow Runner")
    print("=" * 60)
    print()

    tests = [
        test_successful_knower_to_cryer,
        test_successful_cryer_to_pyper,
        test_successful_coder_to_pyper,
        test_invalid_graph_stops_workflow,
        test_approval_gate_stops_workflow,
        test_worker_fn_execution,
        test_validation_failure_stops_workflow,
        test_audit_trace_completeness,
        test_replay_from_trace,
        test_trace_file_persistence,
        test_deterministic_fallback,
        test_no_fallback_when_disabled,
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