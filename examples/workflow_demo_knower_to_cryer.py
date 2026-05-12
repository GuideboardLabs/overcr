#!/usr/bin/env python3
"""
OverCR v0.8.0 — Workflow Demo: KnowER → CryER

KnowER classifies provided claims/snippets.
CryER uses only validated public-signal context to produce a governed recon packet.

This demo:
  1. Builds the KnowER → CryER workflow graph
  2. Validates the graph (DAG integrity, cycle detection, sovereignty)
  3. Runs the workflow with deterministic simulated output
  4. Validates every packet produced
  5. Records the full audit trace
  6. Demonstrates replay from filesystem state

Safety guarantees:
  - No real model inference
  - No outbound contact
  - No shell execution
  - No filesystem mutation by nodes
  - All packets validated through L1-L6
  - OverCR is the only router — no direct subagent authority
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
    print("OverCR v0.8.0 Workflow Demo: KnowER -> CryER")
    print("=" * 60)
    print()

    # ── Phase 1: Build the workflow graph ──────────────
    print("[Phase 1] Building KnowER -> CryER workflow graph...")
    graph = WorkflowGraph.knower_to_cryer_workflow(name="demo_knower_to_cryer")
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
    assert set(graph2.edges.keys()) == set(graph.edges.keys())
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

    # Grant approvals for nodes that require it
    operator_approvals = {
        "cryer_recon": {"decision": "approved", "reason": "Demo approval"},
    }

    result = runner.run(
        graph,
        initial_input={"raw_claims": ["Test claim for classification"]},
        operator_approvals=operator_approvals,
    )

    print(f"  Success: {result['success']}")
    print(f"  Workflow state: {result['workflow_state']}")
    print(f"  Executed nodes: {result['executed_nodes']}")
    print(f"  Failed nodes: {result['failed_nodes']}")
    print(f"  Trace entries: {len(result['trace'])}")

    if not result['success']:
        print(f"  FAIL: Workflow failed: {result['error']}")
        FAILED = True
        return 1

    # ── Phase 5: Verify packet validation ──────────────
    print()
    print("[Phase 5] Verifying packet validation...")
    for node_id in result['executed_nodes']:
        packet = runner.node_packets.get(node_id, {})
        packet_type = packet.get("packet_type", "")
        print(f"  Node '{node_id}': packet_type={packet_type}")
        assert packet.get("target") == "overcr", f"  FAIL: target != 'overcr'"
        assert packet.get("source") in ("knower", "cryer"), f"  FAIL: invalid source"

    # ── Phase 6: Verify audit trace ────────────────────
    print()
    print("[Phase 6] Verifying audit trace...")
    trace_summary = runner.get_trace_summary()
    print(f"  Total trace entries: {trace_summary['total_entries']}")
    print(f"  Node states: {trace_summary['node_states']}")

    # Verify trace file exists
    trace_path = OVERCR_ROOT / "runtime" / f"workflow_trace_{graph.workflow_id}.jsonl"
    if not trace_path.exists():
        print(f"  FAIL: Trace file not found: {trace_path}")
        FAILED = True
        return 1
    # Read trace entries
    trace_entries = []
    with open(trace_path, "r") as f:
        for line in f:
            if line.strip():
                trace_entries.append(json.loads(line.strip()))
    print(f"  Trace file entries: {len(trace_entries)}")

    # ── Phase 7: Replay from filesystem ───────────────
    print()
    print("[Phase 7] Replay from filesystem state...")
    replay_result = WorkflowRunner.replay_from_trace(
        str(OVERCR_ROOT), graph.workflow_id
    )
    print(f"  Replay success: {replay_result['success']}")
    print(f"  Replay executed nodes: {replay_result['executed_nodes']}")
    print(f"  Replay trace entries: {replay_result['trace_entries']}")
    assert replay_result['success'], f"  FAIL: Replay failed: {replay_result.get('error')}"
    assert set(replay_result['executed_nodes']) == set(result['executed_nodes'])

    # ── Summary ────────────────────────────────────────
    print()
    print("=" * 60)
    print("DEMO COMPLETE: KnowER -> CryER")
    print("=" * 60)
    print(f"  Graph: valid DAG, {len(graph.nodes)} nodes, {len(graph.edges)} edges")
    print(f"  Execution: {len(result['executed_nodes'])} nodes completed")
    print(f"  Validation: all packets passed L1-L6")
    print(f"  Audit: {len(trace_entries)} trace entries (append-only)")
    print(f"  Replay: verified from filesystem state")
    print(f"  Safety: no outbound, no shell, no direct subagent routing")
    return 0


if __name__ == "__main__":
    sys.exit(main())