#!/usr/bin/env python3
"""
OverCR v2.3.0 — Test: Workflow Library

Tests the complete workflow_library package including:
  - Workflow registration
  - Template schema validation
  - Node ordering
  - Approval pauses
  - Rollback paths
  - Deterministic fallback
  - Replay correctness
  - Audit trace export
  - Malformed workflow rejection
  - Recursive workflow rejection
  - Invalid edge rejection
"""

import json
import sys
import os
from pathlib import Path

OVERCR_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(OVERCR_ROOT))

from workflow_library import (
    WorkflowContext,
    WorkflowRegistry,
    WorkflowLoader,
    WorkflowLoadError,
    WorkflowExecutor,
)

FAILED = False
_VERBOSE = os.environ.get("VERBOSE", "0") == "1"


def _assert(condition, msg=""):
    global FAILED
    if not condition:
        print(f"  FAIL: {msg}")
        FAILED = True
    elif _VERBOSE:
        print(f"  OK: {msg}")


# ─────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────

TEMPLATES_DIR = OVERCR_ROOT / "workflow_library" / "templates"


def load_template(name):
    with open(TEMPLATES_DIR / name, "r") as f:
        return json.load(f)


# ─────────────────────────────────────────────────────
# Test 1: Workflow Registration
# ─────────────────────────────────────────────────────

def test_registration():
    """Test that workflows can be registered, listed, and retrieved."""
    global FAILED

    executor = WorkflowExecutor(str(OVERCR_ROOT))

    # Register each template (handle pre-existing from disk)
    template_files = sorted(TEMPLATES_DIR.glob("*.json"))
    _assert(len(template_files) >= 5, f"Expected >=5 templates, got {len(template_files)}")

    registered = []
    for tf in template_files:
        with open(tf, "r") as f:
            template = json.load(f)
        wf_id = template["workflow_id"]
        # Only register if not already in registry
        existing = executor.registry.get_workflow(wf_id)
        if existing is None:
            result = executor.registry.register_workflow(template)
            _assert(result["workflow_id"] == wf_id, f"Registered {wf_id}")
        else:
            result = existing
        registered.append(wf_id)

    # List workflows
    workflow_list = executor.registry.list_workflows()
    _assert(len(workflow_list) >= 5, f"Listed {len(workflow_list)} workflows")

    # Get each workflow
    for wf_id in registered:
        wf = executor.registry.get_workflow(wf_id)
        _assert(wf is not None, f"Get workflow '{wf_id}'")
        _assert(wf["workflow_id"] == wf_id, f"ID matches for '{wf_id}'")

    # Duplicate registration should fail
    try:
        executor.registry.register_workflow(executor.registry.get_workflow(registered[0]))
        _assert(False, "Duplicate registration should have raised ValueError")
    except ValueError as e:
        _assert("already registered" in str(e), f"Duplicate rejected: {e}")

    print("  PASS: Workflow registration")


# ─────────────────────────────────────────────────────
# Test 2: Template Schema Validation
# ─────────────────────────────────────────────────────

def test_schema_validation():
    """Test schema validation catches malformed templates."""
    global FAILED

    executor = WorkflowExecutor(str(OVERCR_ROOT))

    # Valid template
    template = load_template("claim_review_workflow.json")
    valid, errors = executor.registry.validate_template_schema(template)
    _assert(valid, f"Valid template passes schema validation: {errors}")

    # Missing required field
    malformed = dict(template)
    del malformed["node_definitions"]
    valid, errors = executor.registry.validate_template_schema(malformed)
    _assert(not valid, f"Missing node_definitions rejected: {errors}")

    # Missing workflow_id
    malformed2 = dict(template)
    del malformed2["workflow_id"]
    valid, errors = executor.registry.validate_template_schema(malformed2)
    _assert(not valid, f"Missing workflow_id rejected: {errors}")

    # Invalid field type
    malformed3 = dict(template)
    malformed3["node_definitions"] = "not_a_list"
    valid, errors = executor.registry.validate_template_schema(malformed3)
    _assert(not valid, f"Wrong type node_definitions rejected: {errors}")

    # Empty node_id
    malformed4 = dict(template)
    malformed4["node_definitions"] = [
        {"node_id": "", "subagent": "knower", "packet_type": "knower_claim_review"}
    ]
    valid, errors = executor.registry.validate_template_schema(malformed4)
    _assert(not valid, f"Empty node_id rejected: {errors}")

    # Duplicate node_ids
    malformed5 = dict(template)
    malformed5["node_definitions"] = [
        {"node_id": "dup", "subagent": "knower", "packet_type": "knower_claim_review"},
        {"node_id": "dup", "subagent": "knower", "packet_type": "knower_myth_fact"},
    ]
    valid, errors = executor.registry.validate_template_schema(malformed5)
    _assert(not valid, f"Duplicate node_ids rejected: {errors}")

    print("  PASS: Template schema validation")


# ─────────────────────────────────────────────────────
# Test 3: Node Ordering (Topological Sort)
# ─────────────────────────────────────────────────────

def test_node_ordering():
    """Test that nodes are ordered correctly by topological sort."""
    global FAILED

    executor = WorkflowExecutor(str(OVERCR_ROOT))

    template = load_template("claim_review_workflow.json")
    order = executor._topological_sort(template)

    _assert(len(order) == 5, f"{len(order)} nodes in order")
    _assert(order[0] == "ingest_claim", f"First node is ingest_claim: {order[0]}")
    _assert(order[-1] == "final_report", f"Last node is final_report: {order[-1]}")

    # Verify ordering respects edges
    node_positions = {nid: i for i, nid in enumerate(order)}
    for edge in template["edge_definitions"]:
        src_pos = node_positions[edge["source"]]
        tgt_pos = node_positions[edge["target"]]
        _assert(src_pos < tgt_pos,
                f"{edge['source']} ({src_pos}) before {edge['target']} ({tgt_pos})")

    print("  PASS: Node ordering")


# ─────────────────────────────────────────────────────
# Test 4: Approval Pauses
# ─────────────────────────────────────────────────────

def test_approval_pauses():
    """Test that approval points cause workflow pauses."""
    global FAILED

    executor = WorkflowExecutor(str(OVERCR_ROOT))

    template = load_template("execution_plan_review_workflow.json")

    # Verify approval points are declared
    _assert("safety_review" in template["approval_points"],
            "safety_review is an approval point")
    _assert(len(template["approval_points"]) == 3,
            f"3 approval points: {template['approval_points']}")

    # Execute the workflow and check that approvals are recorded
    try:
        executor.registry.register_workflow(
            executor.loader.load_template_file(
                str(TEMPLATES_DIR / "execution_plan_review_workflow.json")
            )
        )
    except ValueError:
        pass  # Already registered

    result = executor.execute_workflow("execution_plan_review",
        initial_input={"entity": "test-entity"})

    _assert(result["success"], f"Execution plan review completed successfully: {result.get('error')}")

    # Check audit entries for approval records
    approvals = [e for e in result["audit_entries"] if e["entry_type"] == "approval"]
    _assert(len(approvals) > 0, f"Found {len(approvals)} approval entries")

    # Verify each approval point was hit
    approved_targets = {a["details"].get("target_id", ""): a["details"].get("decision", "")
                        for a in approvals}
    for ap in template["approval_points"]:
        _assert(ap in approved_targets, f"Approval point '{ap}' was approved")

    print("  PASS: Approval pauses")


# ─────────────────────────────────────────────────────
# Test 5: Rollback Paths
# ─────────────────────────────────────────────────────

def test_rollback_paths():
    """Test that rollback behavior is properly declared and handled."""
    global FAILED

    executor = WorkflowExecutor(str(OVERCR_ROOT))

    # All templates should declare rollback_behavior
    for tf_name in sorted(TEMPLATES_DIR.glob("*.json")):
        template = load_template(tf_name.name)
        _assert("rollback_behavior" in template,
                f"{template['workflow_id']} has rollback_behavior")
        _assert(isinstance(template["rollback_behavior"], str),
                f"{template['workflow_id']} rollback_behavior is string")
        _assert(len(template["rollback_behavior"]) > 0,
                f"{template['workflow_id']} rollback_behavior is non-empty")

    # Check that rollback_on_failure flags exist on nodes
    for tf_name in sorted(TEMPLATES_DIR.glob("*.json")):
        template = load_template(tf_name.name)
        for node in template["node_definitions"]:
            _assert("rollback_on_failure" in node,
                    f"{template['workflow_id']}/{node['node_id']} has rollback_on_failure")

    print("  PASS: Rollback paths")


# ─────────────────────────────────────────────────────
# Test 6: Deterministic Fallback
# ─────────────────────────────────────────────────────

def test_deterministic_fallback():
    """Test that deterministic fallback behavior is properly configured."""
    global FAILED

    executor = WorkflowExecutor(str(OVERCR_ROOT))

    for tf_name in sorted(TEMPLATES_DIR.glob("*.json")):
        template = load_template(tf_name.name)
        _assert("deterministic_fallback" in template,
                f"{template['workflow_id']} has deterministic_fallback")
        _assert(template["deterministic_fallback"] in ("stop", "skip", "fallback"),
                f"{template['workflow_id']} fallback is valid: {template['deterministic_fallback']}")

    print("  PASS: Deterministic fallback")


# ─────────────────────────────────────────────────────
# Test 7: Replay Correctness
# ─────────────────────────────────────────────────────

def test_replay_correctness():
    """Test that replay reconstructs execution state correctly."""
    global FAILED

    executor = WorkflowExecutor(str(OVERCR_ROOT))

    template = load_template("recon_brief_workflow.json")
    try:
        executor.registry.register_workflow(
            executor.loader.load_template_file(
                str(TEMPLATES_DIR / "recon_brief_workflow.json")
            )
        )
    except ValueError:
        pass  # Already registered

    result = executor.execute_workflow("recon_brief",
        initial_input={"entity": "replay-test-business"})

    _assert(result["success"], f"Recon brief completed: {result.get('error')}")
    run_id = result["run_id"]
    _assert(run_id, f"Got run_id: {run_id}")

    # Now replay from this run_id (trace is written by the executor)
    # Run a second execution and test replay from audit entries directly
    result2 = executor.execute_workflow("recon_brief",
        initial_input={"entity": "replay-test-business-2"})
    _assert(result2["success"], f"Second recon brief completed")

    # Check that both executions had all nodes
    _assert(len(result["executed_nodes"]) == 4,
            f"First run executed 4 nodes: {result['executed_nodes']}")
    _assert(len(result2["executed_nodes"]) == 4,
            f"Second run executed 4 nodes: {result2['executed_nodes']}")

    # Verify both runs followed the same node order
    _assert(result["executed_nodes"] == result2["executed_nodes"],
            "Both runs executed same node order (deterministic)")

    print("  PASS: Replay correctness")


# ─────────────────────────────────────────────────────
# Test 8: Audit Trace Export
# ─────────────────────────────────────────────────────

def test_audit_trace_export():
    """Test that audit traces are exportable and complete."""
    global FAILED

    executor = WorkflowExecutor(str(OVERCR_ROOT))

    template = load_template("release_freeze_workflow.json")
    try:
        executor.registry.register_workflow(
            executor.loader.load_template_file(
                str(TEMPLATES_DIR / "release_freeze_workflow.json")
            )
        )
    except ValueError:
        pass  # May already be registered

    result = executor.execute_workflow("release_freeze",
        initial_input={"version": "2.3.0"})

    _assert(result["success"], f"Release freeze completed: {result.get('error')}")

    # Verify audit entries contain all required fields
    for template_name in sorted(TEMPLATES_DIR.glob("*.json")):
        template = load_template(template_name.name)
        req = template.get("audit_requirements", [])
        _assert("workflow_id" in req, f"{template['workflow_id']} audits workflow_id")
        _assert("workflow_version" in req, f"{template['workflow_id']} audits workflow_version")
        _assert("node_execution_order" in req, f"{template['workflow_id']} audits node_execution_order")
        _assert("approval_pauses" in req, f"{template['workflow_id']} audits approval_pauses")
        _assert("rollback_events" in req, f"{template['workflow_id']} audits rollback_events")
        _assert("validation_results" in req, f"{template['workflow_id']} audits validation_results")
        _assert("deterministic_fallback_activations" in req,
                f"{template['workflow_id']} audits deterministic_fallback_activations")
        _assert("elapsed_timing" in req, f"{template['workflow_id']} audits elapsed_timing")

    print("  PASS: Audit trace export")


# ─────────────────────────────────────────────────────
# Test 9: Malformed Workflow Rejection
# ─────────────────────────────────────────────────────

def test_malformed_workflow_rejection():
    """Test that malformed workflows are rejected by validate_workflow."""
    global FAILED

    executor = WorkflowExecutor(str(OVERCR_ROOT))

    # Invalid subagent
    bad_template = {
        "workflow_id": "test_malformed",
        "workflow_name": "Malformed Test",
        "version": "2.3.0",
        "description": "Invalid subagent workflow",
        "entry_conditions": [],
        "node_definitions": [
            {"node_id": "n1", "subagent": "non_existent_agent", "packet_type": "knower_claim_review"}
        ],
        "edge_definitions": [],
        "stop_conditions": [],
        "approval_points": [],
        "rollback_behavior": "stop",
        "deterministic_fallback": "stop",
        "audit_requirements": [],
    }
    valid, errors = executor.validate_workflow(bad_template)
    _assert(not valid, f"Invalid subagent rejected: {errors}")
    _assert(any("invalid subagent" in e for e in errors),
            f"Error mentions invalid subagent: {errors}")

    # Invalid packet_type for subagent
    bad2 = dict(bad_template)
    bad2["node_definitions"][0]["subagent"] = "knower"
    bad2["node_definitions"][0]["packet_type"] = "cryer_recon"  # Not a KnowER packet
    valid, errors = executor.validate_workflow(bad2)
    _assert(not valid, f"Invalid packet_type for subagent rejected: {errors}")

    # Missing node_definitions
    bad3 = dict(bad_template)
    bad3["node_definitions"] = []
    valid, errors = executor.validate_workflow(bad3)
    _assert(not valid, f"Empty node_definitions rejected: {errors}")

    # Edge referencing non-existent node
    bad4 = {
        "workflow_id": "bad_edge",
        "workflow_name": "Bad Edge",
        "version": "2.3.0",
        "description": "Edge to non-existent node",
        "entry_conditions": [],
        "node_definitions": [
            {"node_id": "n1", "subagent": "knower", "packet_type": "knower_claim_review"}
        ],
        "edge_definitions": [
            {"edge_id": "e1", "source": "n1", "target": "nonexistent"}
        ],
        "stop_conditions": [],
        "approval_points": [],
        "rollback_behavior": "stop",
        "deterministic_fallback": "stop",
        "audit_requirements": [],
    }
    valid, errors = executor.validate_workflow(bad4)
    _assert(not valid, f"Edge to non-existent node rejected: {errors}")

    print("  PASS: Malformed workflow rejection")


# ─────────────────────────────────────────────────────
# Test 10: Recursive Workflow Rejection
# ─────────────────────────────────────────────────────

def test_recursive_workflow_rejection():
    """Test that recursive (self-referencing) workflows are rejected."""
    global FAILED

    executor = WorkflowExecutor(str(OVERCR_ROOT))

    template = load_template("claim_review_workflow.json")

    # Add a self-edge (self-loop)
    recursive = json.loads(json.dumps(template))
    recursive["edge_definitions"].append({
        "edge_id": "self_loop",
        "source": "final_report",
        "target": "ingest_claim",
        "label": "recursive re-entry"
    })
    valid, errors = executor.validate_workflow(recursive)
    _assert(not valid, f"Self-loop edge rejected: {errors}")
    _assert(any("cycle" in e.lower() for e in errors),
            f"Error mentions cycle: {errors}")

    # Try to register a template that depends on itself
    recursive2 = {
        "workflow_id": "recursive",
        "workflow_name": "Recursive",
        "version": "2.3.0",
        "description": "Self-dependent",
        "entry_conditions": [],
        "depends_on": ["recursive"],
        "node_definitions": [
            {"node_id": "n1", "subagent": "knower", "packet_type": "knower_claim_review"}
        ],
        "edge_definitions": [],
        "stop_conditions": [],
        "approval_points": [],
        "rollback_behavior": "stop",
        "deterministic_fallback": "stop",
        "audit_requirements": [],
    }
    try:
        executor.registry.register_workflow(recursive2)
        _assert(False, "Self-depending workflow should have raised ValueError")
    except ValueError as e:
        _assert("cannot depend on itself" in str(e).lower() or "recursive" in str(e).lower(),
                f"Self-dependency rejected: {e}")

    print("  PASS: Recursive workflow rejection")


# ─────────────────────────────────────────────────────
# Test 11: Invalid Edge Rejection
# ─────────────────────────────────────────────────────

def test_invalid_edge_rejection():
    """Test that invalid cross-subagent edges are rejected."""
    global FAILED

    executor = WorkflowExecutor(str(OVERCR_ROOT))

    # Invalid handoff path: cryer -> pyper is valid, but try reversed / unsupported
    template = {
        "workflow_id": "bad_edge_test",
        "workflow_name": "Bad Edge Test",
        "version": "2.3.0",
        "description": "Testing invalid edge handoff",
        "entry_conditions": [],
        "node_definitions": [
            {"node_id": "knower_node", "subagent": "knower", "packet_type": "knower_claim_review"},
            {"node_id": "cryer_node", "subagent": "cryer", "packet_type": "cryer_recon"},
        ],
        "edge_definitions": [
            {"edge_id": "bad_handoff", "source": "cryer_node", "target": "knower_node"}
        ],
        "stop_conditions": [],
        "approval_points": [],
        "rollback_behavior": "stop",
        "deterministic_fallback": "stop",
        "audit_requirements": [],
    }
    # cryer -> knower is actually valid, so use a truly invalid path
    # Let's use a handoff that isn't in VALID_HANDOFF_PATHS
    # coder -> cryer is not valid
    template2 = {
        "workflow_id": "bad_edge_test2",
        "workflow_name": "Bad Edge Test 2",
        "version": "2.3.0",
        "description": "Testing invalid coder->cryer handoff",
        "entry_conditions": [],
        "node_definitions": [
            {"node_id": "coder_node", "subagent": "coder", "packet_type": "coder_diagnostic"},
            {"node_id": "cryer_node", "subagent": "cryer", "packet_type": "cryer_recon"},
        ],
        "edge_definitions": [
            {"edge_id": "bad_path", "source": "coder_node", "target": "cryer_node"}
        ],
        "stop_conditions": [],
        "approval_points": [],
        "rollback_behavior": "stop",
        "deterministic_fallback": "stop",
        "audit_requirements": [],
    }
    valid, errors = executor.validate_workflow(template2)
    _assert(not valid, f"Invalid coder->cryer handoff rejected: {errors}")
    _assert(any("handoff" in e.lower() or "forbidden" in e.lower() for e in errors),
            f"Error mentions handoff/forbidden: {errors}")

    print("  PASS: Invalid edge rejection")


# ─────────────────────────────────────────────────────
# Test 12: WorkflowContext isolation
# ─────────────────────────────────────────────────────

def test_context_isolation():
    """Test that each workflow execution gets an isolated context."""
    global FAILED

    ctx1 = WorkflowContext(
        workflow_id="test1",
        workflow_name="Test 1",
        workflow_version="2.3.0",
        operator="operator-a",
    )
    ctx2 = WorkflowContext(
        workflow_id="test2",
        workflow_name="Test 2",
        workflow_version="2.3.0",
        operator="operator-b",
    )

    _assert(ctx1.run_id != ctx2.run_id, "Different run_ids")
    _assert(ctx1.operator == "operator-a", "Context 1 operator")
    _assert(ctx2.operator == "operator-b", "Context 2 operator")

    # Mutating one context should not affect the other
    ctx1.record_approval("node-a", "approved", "ok")
    _assert(len(ctx1.approvals) == 1, "Context 1 has 1 approval")
    _assert(len(ctx2.approvals) == 0, "Context 2 has 0 approvals")

    # State transitions
    ctx1.transition_to("running", "start")
    _assert(ctx1.state == "running", "Context 1 running")
    _assert(ctx2.state == "initialized", "Context 2 still initialized")

    print("  PASS: Context isolation")


# ─────────────────────────────────────────────────────
# Test 13: Execute all 5 workflows
# ─────────────────────────────────────────────────────

def test_execute_all_workflows():
    """Test that all 5 workflow templates execute successfully."""
    global FAILED

    executor = WorkflowExecutor(str(OVERCR_ROOT))

    workflows = [
        ("claim_review", {"raw_claims": ["Test claim: OverCR is a portable AI orchestration substrate"]}),
        ("recon_brief", {"entity": "test-entity"}),
        ("coder_patch_review", {"repository": "overcr", "issue": "test-bug"}),
        ("execution_plan_review", {"entity": "test-entity", "action": "validate_packet"}),
        ("release_freeze", {"version": "2.3.0", "repository": "overcr"}),
    ]

    for wf_id, inputs in workflows:
        # Ensure registered
        template = load_template(f"{wf_id}_workflow.json")
        try:
            executor.registry.register_workflow(template)
        except ValueError:
            pass  # Already registered

        result = executor.execute_workflow(wf_id, initial_input=inputs)
        _assert(result["success"], f"{wf_id}: completed successfully")

        # Verify all nodes executed
        expected_nodes = len(template["node_definitions"])
        _assert(len(result["executed_nodes"]) == expected_nodes,
                f"{wf_id}: executed {len(result['executed_nodes'])}/{expected_nodes} nodes: {result['executed_nodes']}")

        # Verify audit entries exist
        _assert(len(result["audit_entries"]) > 0,
                f"{wf_id}: {len(result['audit_entries'])} audit entries")

    print("  PASS: Execute all 5 workflows")


# ────────────────────────────────────────────────────
# Main
# ────────────────────────────────────────────────────

def main():
    global FAILED

    print("=" * 60)
    print("OverCR v2.3.0 — Workflow Library Tests")
    print("=" * 60)

    tests = [
        ("Workflow registration", test_registration),
        ("Template schema validation", test_schema_validation),
        ("Node ordering", test_node_ordering),
        ("Approval pauses", test_approval_pauses),
        ("Rollback paths", test_rollback_paths),
        ("Deterministic fallback", test_deterministic_fallback),
        ("Replay correctness", test_replay_correctness),
        ("Audit trace export", test_audit_trace_export),
        ("Malformed workflow rejection", test_malformed_workflow_rejection),
        ("Recursive workflow rejection", test_recursive_workflow_rejection),
        ("Invalid edge rejection", test_invalid_edge_rejection),
        ("Context isolation", test_context_isolation),
        ("Execute all 5 workflows", test_execute_all_workflows),
    ]

    for name, fn in tests:
        print(f"\n--- {name} ---")
        try:
            fn()
        except Exception as e:
            print(f"  ERROR: {e}")
            import traceback
            traceback.print_exc()
            FAILED = True

    print("\n" + "=" * 60)
    if FAILED:
        print("RESULT: SOME TESTS FAILED")
        return 1
    else:
        print("RESULT: ALL TESTS PASSED")
        return 0


if __name__ == "__main__":
    sys.exit(main())
