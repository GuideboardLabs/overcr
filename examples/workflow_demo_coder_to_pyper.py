#!/usr/bin/env python3
"""
OverCR v0.8.0 — Workflow Demo: CodER → PypER

CodER produces advisory patch plan.
PypER produces execution plan/receipt simulation.
No command execution. No filesystem mutation.

This demo:
  1. Builds the CodER → PypER workflow graph
  2. Validates the graph (DAG integrity, cycle detection, sovereignty)
  3. Runs the workflow with deterministic simulated output
  4. Validates every packet produced
  5. Verifies PypER receipt is purely simulated (no commands, no file changes)
  6. Records the full audit trace
  7. Demonstrates replay from filesystem state

Safety guarantees:
  - No real model inference
  - No outbound contact
  - No shell execution
  - No filesystem mutation by nodes
  - No command execution (PypER receipt is simulated)
  - All packets validated through L1-L6
  - OverCR is the only router — no direct subagent authority
  - CodER patch plan is advisory only — no file mutation
  - PypER execution receipt is simulated — commands_executed=[], files_modified=[]
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
    print("OverCR v0.8.0 Workflow Demo: CodER -> PypER")
    print("=" * 60)
    print()

    # ── Phase 1: Build the workflow graph ──────────────
    print("[Phase 1] Building CodER -> PypER workflow graph...")
    graph = WorkflowGraph.coder_to_pyper_workflow(name="demo_coder_to_pyper")
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

    # Grant approvals for both nodes and the edge
    operator_approvals = {
        "coder_patch": {"decision": "approved", "reason": "Demo approval for CodER"},
        "pyper_simulate": {"decision": "approved", "reason": "Demo approval for PypER"},
        "coder_to_pyper": {"decision": "approved", "reason": "Demo approval for edge"},
    }

    result = runner.run(
        graph,
        initial_input={"issue_context": {"issue": "test-issue"}},
        operator_approvals=operator_approvals,
    )

    print(f"  Success: {result['success']}")
    print(f"  Workflow state: {result['workflow_state']}")
    print(f"  Executed nodes: {result['executed_nodes']}")

    if not result['success']:
        print(f"  FAIL: Workflow failed: {result['error']}")
        FAILED = True
        return 1

    # ── Phase 5: Verify CodER patch advisory only ──────
    print()
    print("[Phase 5] Verifying CodER patch plan is advisory only...")
    coder_packet = runner.node_packets.get("coder_patch", {})
    patch_data = coder_packet.get("patch_data", {})
    print(f"  CodER packet_type: {coder_packet.get('packet_type')}")
    print(f"  breaking_changes: {patch_data.get('breaking_changes')}")
    print(f"  reversible: {patch_data.get('reversible')}")
    assert patch_data.get("breaking_changes") is not True, \
        "  FAIL: CodER patch must not have breaking_changes=true"
    assert patch_data.get("reversible") is not False, \
        "  FAIL: CodER patch must be reversible"
    # Verify no actual file mutation is described
    for patch in patch_data.get("patches", []):
        action = patch.get("action", "")
        print(f"  Patch action: {action}")
        assert action == "advisory", f"  FAIL: non-advisory patch action: {action}"
    print("  PASS: CodER patch plan is advisory, reversible, non-breaking")

    # ── Phase 6: Verify PypER receipt is simulated ────
    print()
    print("[Phase 6] Verifying PypER receipt is purely simulated...")
    pyper_packet = runner.node_packets.get("pyper_simulate", {})
    receipt_data = pyper_packet.get("receipt_data", {})
    print(f"  PypER packet_type: {pyper_packet.get('packet_type')}")
    print(f"  execution_mode: {receipt_data.get('execution_mode')}")
    print(f"  commands_executed: {receipt_data.get('commands_executed')}")
    print(f"  files_modified: {receipt_data.get('files_modified')}")
    print(f"  outbound_actions: {receipt_data.get('outbound_actions')}")
    assert receipt_data.get("execution_mode") == "simulated", \
        "  FAIL: PypER receipt must be simulated"
    assert receipt_data.get("commands_executed") == [], \
        "  FAIL: PypER receipt must have no commands_executed"
    assert receipt_data.get("files_modified") == [], \
        "  FAIL: PypER receipt must have no files_modified"
    assert receipt_data.get("outbound_actions") == [], \
        "  FAIL: PypER receipt must have no outbound_actions"
    print("  PASS: PypER receipt is simulated with zero real execution")

    # ── Phase 7: Verify audit trace ────────────────────
    print()
    print("[Phase 7] Verifying audit trace...")
    trace_path = OVERCR_ROOT / "runtime" / f"workflow_trace_{graph.workflow_id}.jsonl"
    assert trace_path.exists(), "  FAIL: Trace file not found"
    trace_entries = []
    with open(trace_path, "r") as f:
        for line in f:
            if line.strip():
                trace_entries.append(json.loads(line.strip()))
    print(f"  Trace entries: {len(trace_entries)}")

    # ── Phase 8: Replay from filesystem ───────────────
    print()
    print("[Phase 8] Replay from filesystem state...")
    replay_result = WorkflowRunner.replay_from_trace(
        str(OVERCR_ROOT), graph.workflow_id
    )
    print(f"  Replay success: {replay_result['success']}")
    assert replay_result['success'], "  FAIL: Replay failed"
    print("  PASS: Replay verified")

    # ── Summary ────────────────────────────────────────
    print()
    print("=" * 60)
    print("DEMO COMPLETE: CodER -> PypER")
    print("=" * 60)
    print(f"  Graph: valid DAG, {len(graph.nodes)} nodes, {len(graph.edges)} edges")
    print(f"  Execution: {len(result['executed_nodes'])} nodes completed")
    print(f"  CodER: advisory patch, reversible, non-breaking")
    print(f"  PypER: simulated receipt, zero execution, zero mutation")
    print(f"  Audit: {len(trace_entries)} trace entries (append-only)")
    print(f"  Safety: no outbound, no shell, no file mutation, no direct subagent routing")
    return 0


if __name__ == "__main__":
    sys.exit(main())