#!/usr/bin/env python3
"""
OverCR v0.8.0 — Workflow Demo: CryER → PypER

CryER produces public signal packet.
PypER produces execution/outreach planning packet.
Output remains approval_required=true. No outbound action.

This demo:
  1. Builds the CryER → PypER workflow graph
  2. Validates the graph (DAG integrity, cycle detection, sovereignty)
  3. Runs the workflow with deterministic simulated output
  4. Validates every packet produced
  5. Verifies PypER output has approval_required=true
  6. Records the full audit trace
  7. Demonstrates replay from filesystem state

Safety guarantees:
  - No real model inference
  - No outbound contact
  - No shell execution
  - No filesystem mutation by nodes
  - All packets validated through L1-L6
  - OverCR is the only router — no direct subagent authority
  - PypER output ALWAYS approval_required=true
"""

import json
import sys
from pathlib import Path

# Resolve OVERCR_ROOT
OVERCR_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(OVERCR_ROOT))

from runtime.workflow_graph import WorkflowGraph, WorkflowNode, WorkflowEdge
from runtime.workflow_policy import WorkflowPolicy
from runtime.workflow_runner import WorkflowRunner

FAILED = False


def main():
    global FAILED
    print("=" * 60)
    print("OverCR v0.8.0 Workflow Demo: CryER -> PypER")
    print("=" * 60)
    print()

    # ── Phase 1: Build the workflow graph ──────────────
    print("[Phase 1] Building CryER -> PypER workflow graph...")
    graph = WorkflowGraph.cryer_to_pyper_workflow(name="demo_cryer_to_pyper")
    print(f"  Workflow ID: {graph.workflow_id}")
    print(f"  Nodes: {list(graph.nodes.keys())}")
    print(f"  Edges: {list(graph.edges.keys())}")

    # ── Phase 2: Validate the graph ────────────────────
    print()
    print("[Phase 2] Validating graph integrity...")
    valid, errors = graph.build()
    if not valid:
        print(f"  FAIL: Graph validation failed: {errors}")
        FAILED = True
        return 1
    print("  PASS: Graph is a valid DAG, no cycles, all handoffs through OverCR")
    print(f"  Topological order: {graph.topological_order()}")

    # ── Phase 3: Serialize and deserialize ──────────────
    print()
    print("[Phase 3] Serialization round-trip...")
    json_str = graph.to_json()
    graph2 = WorkflowGraph.from_json(json_str)
    assert graph2.workflow_id == graph.workflow_id
    assert set(graph2.nodes.keys()) == set(graph.nodes.keys())
    print("  PASS: JSON serialization round-trip successful")

    # ── Phase 4: Run the workflow ──────────────────────
    print()
    print("[Phase 4] Running workflow with deterministic output...")
    policy = WorkflowPolicy(allow_deterministic_fallback=True)
    runner = WorkflowRunner(
        root=str(OVERCR_ROOT),
        policy=policy,
        allow_deterministic_fallback=True,
    )

    # Grant approvals for PypER node and CryER->PypER edge
    operator_approvals = {
        "pyper_plan": {"decision": "approved", "reason": "Demo approval for PypER"},
        "cryer_to_pyper": {"decision": "approved", "reason": "Demo approval for edge"},
    }

    result = runner.run(
        graph,
        initial_input={"entity_context": {"entity": "test-entity"}},
        operator_approvals=operator_approvals,
    )

    print(f"  Success: {result['success']}")
    print(f"  Workflow state: {result['workflow_state']}")
    print(f"  Executed nodes: {result['executed_nodes']}")
    print(f"  Failed nodes: {result['failed_nodes']}")

    if not result['success']:
        print(f"  FAIL: Workflow failed: {result['error']}")
        FAILED = True
        return 1

    # ── Phase 5: Verify PypER approval_required ────────
    print()
    print("[Phase 5] Verifying PypER approval_required=true...")
    pyper_packet = runner.node_packets.get("pyper_plan", {})
    print(f"  PypER packet_type: {pyper_packet.get('packet_type')}")
    print(f"  PypER approval_required: {pyper_packet.get('approval_required')}")
    print(f"  PypER outbound_blocked: {pyper_packet.get('outbound_blocked')}")
    assert pyper_packet.get("approval_required") is True, \
        "  FAIL: PypER output must have approval_required=true"
    assert pyper_packet.get("outbound_blocked") is True, \
        "  FAIL: PypER output must have outbound_blocked=true"
    print("  PASS: PypER output has approval_required=true, outbound_blocked=true")

    # ── Phase 6: Verify no outbound action ─────────────
    print()
    print("[Phase 6] Verifying no outbound action in PypER plan...")
    plan_data = pyper_packet.get("plan_data", {})
    steps = plan_data.get("steps", [])
    for i, step in enumerate(steps):
        action = step.get("action", "")
        print(f"  Step {i+1}: {action}")
        assert "send" not in action.lower(), f"  FAIL: outbound action detected: {action}"
        assert "execute" not in action.lower() or "review" in action.lower(), \
            f"  FAIL: execution action detected: {action}"
    print("  PASS: No outbound actions in PypER plan")

    # ── Phase 7: Verify audit trace ────────────────────
    print()
    print("[Phase 7] Verifying audit trace...")
    trace_summary = runner.get_trace_summary()
    print(f"  Total trace entries: {trace_summary['total_entries']}")
    trace_path = OVERCR_ROOT / "runtime" / f"workflow_trace_{graph.workflow_id}.jsonl"
    assert trace_path.exists(), f"  FAIL: Trace file not found"
    trace_entries = []
    with open(trace_path, "r") as f:
        for line in f:
            if line.strip():
                trace_entries.append(json.loads(line.strip()))
    print(f"  Trace file entries: {len(trace_entries)}")

    # ── Phase 8: Replay from filesystem ───────────────
    print()
    print("[Phase 8] Replay from filesystem state...")
    replay_result = WorkflowRunner.replay_from_trace(
        str(OVERCR_ROOT), graph.workflow_id
    )
    print(f"  Replay success: {replay_result['success']}")
    assert replay_result['success'], f"  FAIL: Replay failed"
    print("  PASS: Replay verified")

    # ── Summary ────────────────────────────────────────
    print()
    print("=" * 60)
    print("DEMO COMPLETE: CryER -> PypER")
    print("=" * 60)
    print(f"  Graph: valid DAG, {len(graph.nodes)} nodes, {len(graph.edges)} edges")
    print(f"  Execution: {len(result['executed_nodes'])} nodes completed")
    print(f"  PypER: approval_required=true, outbound_blocked=true")
    print(f"  Audit: {len(trace_entries)} trace entries (append-only)")
    print(f"  Safety: no outbound, no execution, no direct subagent routing")
    return 0


if __name__ == "__main__":
    sys.exit(main())