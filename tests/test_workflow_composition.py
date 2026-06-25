#!/usr/bin/env python3
"""
OverCR v2.8.0 — Test: Workflow Composition

Tests the complete workflow composition subsystem:
  - Conditional branch routing
  - Confidence threshold routing
  - Retry limits enforced
  - Escalation triggers
  - Fallback activation
  - Illegal transition rejection
  - Recursive workflow rejection
  - Subworkflow loading
  - Version mismatch handling
  - Branch trace replay
  - Deterministic routing
  - Malformed condition rejection
"""

import json, os, sys, tempfile, uuid
from pathlib import Path

OVERCR_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(OVERCR_ROOT))

from workflow_composition import (
    ConditionEvaluator, EvaluatedCondition,
    RoutingPolicy, RoutingDecision,
    RetryPolicy, RetryRecord,
    EscalationPolicy, EscalationRecord,
    SubworkflowLoader, SubworkflowRef, SubworkflowLoadError,
    WorkflowStateMachine, StateTransition, InvalidTransitionError,
    BranchTrace, BranchEntry,
)

FAILED = False
def _assert(condition, msg=""):
    global FAILED
    if not condition:
        print(f"  FAIL: {msg}")
        FAILED = True

# ── Test 1: Confidence threshold routing ──────────────────

def test_confidence_threshold_routing():
    e = ConditionEvaluator()
    ctx = {"node_outcomes": {"verify": {"confidence": 3}}}
    cond = {"type": "confidence_threshold", "field": "node_outcomes.verify.confidence",
            "operator": ">=", "value": 3}
    result = e.evaluate(cond, ctx)
    _assert(result.passed, f"confidence >= 3 passes: {result.details}")
    cond2 = {"type": "confidence_threshold", "field": "node_outcomes.verify.confidence",
             "operator": ">=", "value": 4}
    r2 = e.evaluate(cond2, ctx)
    _assert(not r2.passed, "confidence >= 4 fails for value 3")
    print("  PASS: Confidence threshold routing")

# ── Test 2: Trust tier comparison ─────────────────────────

def test_trust_tier_comparison():
    e = ConditionEvaluator()
    ctx = {"source": {"trust_level": "reputable"}}
    cond = {"type": "trust_tier", "field": "source.trust_level",
            "operator": ">=", "value": "reputable"}
    _assert(e.evaluate(cond, ctx).passed, "reputable >= reputable passes")
    cond2 = {"type": "trust_tier", "field": "source.trust_level",
             "operator": ">=", "value": "verified"}
    _assert(not e.evaluate(cond2, ctx).passed, "reputable >= verified fails")
    print("  PASS: Trust tier comparison")

# ── Test 3: Conditional branch routing ────────────────────

def test_conditional_branch_routing():
    e = ConditionEvaluator()
    ctx = {"node_outcomes": {"check": {"confidence": 2}}}
    conditional_edges = [
        {"edge_id": "c1", "source": "check", "target": "high_confidence",
         "condition": {"type": "confidence_threshold",
                       "field": "node_outcomes.check.confidence",
                       "operator": ">=", "value": 4}, "priority": 0},
        {"edge_id": "c2", "source": "check", "target": "medium_confidence",
         "condition": {"type": "confidence_threshold",
                       "field": "node_outcomes.check.confidence",
                       "operator": ">=", "value": 2}, "priority": 1},
    ]
    matched = e.first_match(conditional_edges, ctx)
    _assert(matched is not None, "matched a conditional edge")
    _assert(matched["target"] == "medium_confidence", f"routed to medium: {matched['target']}")
    print("  PASS: Conditional branch routing")

# ── Test 4: Validation result routing ─────────────────────

def test_validation_result_routing():
    e = ConditionEvaluator()
    ctx = {"validation": {"valid": False}}
    cond = {"type": "validation_result", "field": "validation.valid",
            "operator": "==", "value": False}
    _assert(e.evaluate(cond, ctx).passed, "validation==False passes")
    cond2 = {"type": "validation_result", "field": "validation.valid",
             "operator": "==", "value": True}
    _assert(not e.evaluate(cond2, ctx).passed, "validation==True fails for False")
    print("  PASS: Validation result routing")

# ── Test 5: Routing policy next_node ──────────────────────

def test_routing_policy_next_node():
    rp = RoutingPolicy()
    ctx = {"node_outcomes": {"a": {"confidence": 4}}}
    static = [{"edge_id": "s1", "source": "a", "target": "b"}]
    cond = [{"edge_id": "c1", "source": "a", "target": "high_path",
             "condition": {"type": "confidence_threshold",
                           "field": "node_outcomes.a.confidence",
                           "operator": ">=", "value": 3}, "priority": 0}]
    d = rp.next_node("a", static, cond, ctx, "op")
    _assert(d.decision_type == "conditional_branch", f"conditional chosen: {d.decision_type}")
    _assert(d.target_node_id == "high_path", f"target: {d.target_node_id}")
    print("  PASS: Routing policy next_node")

# ── Test 6: Retry limits enforced ─────────────────────────

def test_retry_limits_enforced():
    rp = RetryPolicy(max_retries=3, fallback_threshold=2)
    _assert(rp.should_retry("n1", "validation_failed"), "1st retry allowed")
    rp.record_attempt("n1", "validation_failed")
    _assert(rp.should_retry("n1", "validation_failed"), "2nd retry allowed")
    rp.record_attempt("n1", "validation_failed")
    _assert(rp.should_fallback("n1"), "fallback at threshold 2")
    rp.record_attempt("n1", "validation_failed")
    _assert(not rp.should_retry("n1", "validation_failed"), "4th retry blocked")
    _assert(rp.is_exhausted("n1"), "exhausted at max 3")
    _assert(len(rp.get_records()) == 3, "3 records")
    # Strict policy
    srp = RetryPolicy.strict()
    _assert(not srp.should_retry("n1", "validation_failed"), "strict blocks all")
    print("  PASS: Retry limits enforced")

# ── Test 7: Escalation triggers ──────────────────────────

def test_escalation_triggers():
    ep = EscalationPolicy(
        escalation_points=["critical_node"],
        targets=[{"target": "operator_review", "pause_workflow": True}],
    )
    _assert(ep.should_escalate("critical_node"), "point-triggered escalation")
    _assert(ep.should_escalate("n2", retries_exhausted=True), "retry-exhausted escalation")
    erec = ep.escalate("bad_node", "retries exhausted", severity="high")
    _assert(erec.target == "operator_review", f"target: {erec.target}")
    _assert(erec.pause_workflow, "workflow paused")
    _assert(erec.severity == "high", "severity recorded")
    ep.resolve(erec.escalation_id, "operator acknowledged")
    _assert(erec.resolved, "resolved")
    print("  PASS: Escalation triggers")

# ── Test 8: Fallback activation ───────────────────────────

def test_fallback_activation():
    rp = RoutingPolicy()
    ctx = {"failed_node": "analyze"}
    fallback_routes = {"analyze": "retry_analyze"}
    d = rp.fallback_node("analyze", fallback_routes, ctx, "op")
    _assert(d.decision_type == "fallback", f"decision: {d.decision_type}")
    _assert(d.target_node_id == "retry_analyze", f"target: {d.target_node_id}")
    print("  PASS: Fallback activation")

# ── Test 9: Illegal transition rejection ──────────────────

def test_illegal_transition_rejection():
    sm = WorkflowStateMachine("initialized")
    sm.transition_to("running", "start")
    _assert(sm.state == "running", "now running")
    try:
        sm.transition_to("rolled_back", "illegal attempt")
        _assert(False, "should have raised InvalidTransitionError")
    except InvalidTransitionError as e:
        _assert("Illegal transition" in str(e), f"rejected: {e}")
    sm.transition_to("completed", "done")
    _assert(sm.is_terminal(), "terminal")
    print("  PASS: Illegal transition rejection")

# ── Test 10: State machine valid transitions ──────────────

def test_state_machine_transitions():
    sm = WorkflowStateMachine()
    _assert(sm.can_transition_to("running"), "init -> running ok")
    _assert(sm.can_transition_to("paused"), "init -> paused ok")
    _assert(not sm.can_transition_to("completed"), "init -> completed blocked")
    sm.transition_to("running")
    sm.transition_to("awaiting_approval", "approval needed", "node1")
    _assert(sm.state == "awaiting_approval", "awaiting approval")
    sm.transition_to("running", "approved")
    sm.transition_to("failed", "error", "node2")
    _assert(sm.is_terminal(), "failed is terminal")
    hist = sm.export_history()
    _assert(len(hist) >= 4, f"at least 4 transitions: {len(hist)}")
    print("  PASS: State machine valid transitions")

# ── Test 11: Subworkflow loading ──────────────────────────

def test_subworkflow_loading():
    # Create a minimal subworkflow template on disk
    td = tempfile.mkdtemp(prefix="overcr_sw_test_")
    sw_path = Path(td) / "sub_verify_workflow.json"
    sw_template = {
        "workflow_id": "sub_verify", "workflow_name": "Sub Verify",
        "version": "1.0.0", "description": "Sub workflow",
        "entry_conditions": [], "node_definitions": [
            {"node_id": "v1", "subagent": "knower", "packet_type": "knower_claim_review"}
        ], "edge_definitions": [], "stop_conditions": ["v1"],
        "approval_points": [], "rollback_behavior": "stop",
        "deterministic_fallback": "stop", "audit_requirements": [],
    }
    with open(sw_path, "w") as f:
        json.dump(sw_template, f)
    loader = SubworkflowLoader(td)
    ref = loader.load_subworkflow({
        "ref_id": "verify_step", "workflow_id": "sub_verify",
        "version": "1.0.0", "input_map": {"topic": "child_topic"},
        "output_map": {"result": "parent_result"},
    })
    _assert(ref.ref_id == "verify_step", "ref_id ok")
    _assert(ref.loaded_template["workflow_id"] == "sub_verify", "template loaded")
    # Version mismatch
    try:
        loader.load_subworkflow({
            "ref_id": "bad_ver", "workflow_id": "sub_verify",
            "version": "2.0.0",
        })
        _assert(False, "version mismatch should raise")
    except SubworkflowLoadError as e:
        _assert("Version mismatch" in str(e), f"version reject: {e}")
    import shutil; shutil.rmtree(td, ignore_errors=True)
    print("  PASS: Subworkflow loading")

# ── Test 12: Subworkflow cycle detection ──────────────────

def test_subworkflow_cycle_detection():
    td = tempfile.mkdtemp(prefix="overcr_sw_cycle_")
    # Create two mutually referencing templates matching load_all ref_ids
    for idx, wf_id in enumerate(["sub_a", "sub_b"]):
        other_idx = 1 - idx
        tpl = {
            "workflow_id": wf_id, "workflow_name": wf_id,
            "version": "1.0.0", "description": "",
            "entry_conditions": [], "node_definitions": [
                {"node_id": "n1", "subagent": "knower", "packet_type": "knower_claim_review"}
            ], "edge_definitions": [], "stop_conditions": ["n1"],
            "approval_points": [], "rollback_behavior": "stop",
            "deterministic_fallback": "stop", "audit_requirements": [],
            "subworkflow_refs": [
                {"ref_id": f"{'b' if idx == 0 else 'a'}_ref",
                 "workflow_id": "sub_b" if idx == 0 else "sub_a",
                 "version": "1.0.0"}
            ],
        }
        with open(Path(td) / f"{wf_id}_workflow.json", "w") as f:
            json.dump(tpl, f)
    loader = SubworkflowLoader(td)
    # Load both into a single workflow to create mutual dependency
    try:
        loader.load_all([
            {"ref_id": "a_ref", "workflow_id": "sub_a", "version": "1.0.0"},
            {"ref_id": "b_ref", "workflow_id": "sub_b", "version": "1.0.0"},
        ])
        _assert(False, "cycle should be detected")
    except SubworkflowLoadError as e:
        _assert("Cycle" in str(e) or "cycle" in str(e).lower(), f"cycle detected: {e}")
    import shutil; shutil.rmtree(td, ignore_errors=True)
    print("  PASS: Subworkflow cycle detection")

# ── Test 13: Branch trace recording ───────────────────────

def test_branch_trace_recording():
    bt = BranchTrace("run-123")
    bt.record_conditional_branch("check", "high", {"type": "confidence_threshold"})
    bt.record_retry("check", 1, "validation_failed")
    bt.record_escalation("check", "operator_review", "retries exhausted", "high")
    bt.record_fallback("check", "fallback_node", "escalation")
    bt.record_routing("check", "next", "static_edge")
    entries = bt.get_entries()
    _assert(len(entries) == 5, f"5 entries: {len(entries)}")
    types = {e.entry_type for e in entries}
    _assert("conditional_branch" in types, "conditional recorded")
    _assert("retry" in types, "retry recorded")
    _assert("escalation" in types, "escalation recorded")
    _assert("fallback" in types, "fallback recorded")
    _assert("routing" in types, "routing recorded")
    # Replay path
    path = bt.replay_path()
    _assert("check" in path, "check in path")
    # Export
    exported = bt.export()
    _assert(len(exported) == 5, "5 exported")
    print("  PASS: Branch trace recording")

# ── Test 14: Deterministic routing ────────────────────────

def test_deterministic_routing():
    e = ConditionEvaluator()
    ctx = {"conf": 3}
    # Same condition, same context → same result every time
    for _ in range(5):
        r = e.evaluate({"type": "confidence_threshold", "field": "conf",
                        "operator": ">=", "value": 3}, ctx)
        _assert(r.passed, "deterministic result")
    print("  PASS: Deterministic routing")

# ── Test 15: Malformed condition rejection ────────────────

def test_malformed_condition_rejection():
    e = ConditionEvaluator()
    ctx = {}
    # Unknown type defaults to False (not an explosion)
    r = e.evaluate({"type": "nonexistent_type", "field": "x"}, ctx)
    _assert(not r.passed, "unknown type fails safely")
    # Missing field resolves to None
    r2 = e.evaluate({"type": "confidence_threshold", "field": "missing.deeply",
                     "operator": ">=", "value": 3}, ctx)
    _assert(not r2.passed, "missing field fails safely")
    print("  PASS: Malformed condition rejection")

# ── Test 16: Routing policy records decisions ─────────────

def test_routing_policy_records():
    rp = RoutingPolicy()
    ctx = {"n": {}}
    rp.next_node("start", [{"edge_id": "s1", "source": "start", "target": "end"}],
                 [], ctx, "op")
    rp.rejection_node("end", "done", ctx, "op")
    decisions = rp.get_decisions()
    _assert(len(decisions) == 2, "2 decisions")
    _assert(decisions[0].decision_type == "static_edge", "static")
    _assert(decisions[1].decision_type == "rejection", "rejection")
    trace = rp.export_trace()
    _assert(len(trace) == 2, "2 in trace")
    print("  PASS: Routing policy records")

# ── Test 17: Escalation export ────────────────────────────


# ── Test 16: Full routing pipeline end-to-end ──────────────

def test_full_routing_pipeline():
    """
    Verify the complete routing pipeline end-to-end:
    1. Conditional edge is evaluated
    2. Correct branch is selected based on context
    3. State machine transitions
    4. Routing decision is recorded in audit trail
    
    Sets up a workflow with two conditional branches (high confidence vs low),
    feeds context that triggers high-confidence path, and verifies the
    decision record contains matched condition, target node, and timestamp.
    """
    rp = RoutingPolicy()
    sm = WorkflowStateMachine()
    
    # Setup: Two conditional branches from "check" node
    # - high_confidence path: requires confidence >= 4
    # - medium_confidence path: requires confidence >= 2 but < 4
    conditional_edges = [
        {
            "edge_id": "c1",
            "source": "check",
            "target": "high_confidence",
            "condition": {
                "type": "confidence_threshold",
                "field": "node_outcomes.check.confidence",
                "operator": ">=",
                "value": 4,
            },
            "priority": 0,
        },
        {
            "edge_id": "c2",
            "source": "check",
            "target": "medium_confidence",
            "condition": {
                "type": "confidence_threshold",
                "field": "node_outcomes.check.confidence",
                "operator": ">=",
                "value": 2,
            },
            "priority": 1,
        },
    ]
    
    # Static fallback edge
    static_edges = [
        {"edge_id": "s1", "source": "check", "target": "default_handler"},
    ]
    
    # Context that triggers high-confidence path
    ctx = {
        "node_outcomes": {
            "check": {
                "confidence": 5,
            },
        },
    }
    
    # Execute: Route from "check" node
    decision = rp.next_node("check", static_edges, conditional_edges, ctx, "operator123")
    
    # Verify: Decision type and target node
    _assert(decision.decision_type == "conditional_branch",
            f"Expected conditional_branch, got {decision.decision_type}")
    _assert(decision.target_node_id == "high_confidence",
            f"Expected high_confidence target, got {decision.target_node_id}")
    
    # Verify: Matched condition is recorded
    _assert(decision.matched_condition is not None,
            "matched_condition should be recorded")
    _assert(decision.matched_condition["edge_id"] == "c1",
            f"Expected edge_id c1, got {decision.matched_condition.get("edge_id")}")
    
    # Verify: Evaluated conditions contain the evaluated result
    _assert(len(decision.evaluated_conditions) > 0,
            "evaluated_conditions should contain evaluated results")
    evaluated = decision.evaluated_conditions[0]
    _assert(evaluated.passed == True,
            f"Condition should pass for confidence=5")
    
    # Verify: Workflow state snapshot is recorded
    _assert("workflow_state_snapshot" in decision.__dict__,
            "workflow_state_snapshot should be recorded")
    snapshot = decision.workflow_state_snapshot
    _assert("node_outcomes" in snapshot,
            "node_outcomes should be in snapshot")
    _assert(snapshot["node_outcomes"]["check"]["confidence"] == 5,
            f"Snapshot should preserve confidence=5, got {snapshot.get("node_outcomes")}")
    
    # Verify: Operator context is recorded
    _assert(decision.operator_context == "operator123",
            f"Expected operator123, got {decision.operator_context}")
    
    # Verify: Timestamp is recorded
    _assert("timestamp" in decision.__dict__,
            "timestamp should be recorded")
    timestamp = decision.timestamp
    _assert(len(timestamp) > 0 and timestamp.startswith("20"),
            f"Timestamp should be ISO format, got {timestamp}")
    
    # Verify: Decision is recorded in policy history
    decisions = rp.get_decisions()
    _assert(len(decisions) >= 1, f"Should have at least 1 decision, got {len(decisions)}")
    
    # Verify: Decision trace is exported correctly
    trace = rp.export_trace()
    _assert(len(trace) >= 1, f"Trace should contain at least 1 entry, got {len(trace)}")
    
    # Verify: State machine transition is recorded
    sm.transition_to("running", "workflow started")
    hist = sm.export_history()
    _assert(len(hist) == 1, f"Should have 1 transition in history, got {len(hist)}")
    
    # Verify: Transition history contains from/to states
    _assert(hist[0]["from_state"] == "initialized",
            f"Expected from_state=initialized, got {hist[0].get("from_state")}")
    _assert(hist[0]["to_state"] == "running",
            f"Expected to_state=running, got {hist[0].get("to_state")}")
    
    # Verify: Timestamp in transition history
    _assert("timestamp" in hist[0],
            "Transition history should contain timestamp")
    
    print("  PASS: Full routing pipeline end-to-end")


# ── Test 17: Escalation export ───────────────────────────

def test_escalation_export():
    ep = EscalationPolicy()
    ep.escalate("n1", "test", severity="low")
    ep.escalate("n2", "test2", severity="critical", target="governance_review")
    records = ep.export_records()
    _assert(len(records) == 2, "2 records")
    _assert(records[1]["target"] == "governance_review", "gov target")
    _assert(records[1]["severity"] == "critical", "critical severity")
    print("  PASS: Escalation export")

# ── Test 18: Negation in conditions ───────────────────────

def test_negation_in_conditions():
    e = ConditionEvaluator()
    ctx = {"ok": True}
    cond = {"type": "validation_result", "field": "ok", "operator": "==",
            "value": True, "negate": True}
    _assert(not e.evaluate(cond, ctx).passed, "negated true == false")
    cond2 = {"type": "validation_result", "field": "ok", "operator": "==",
             "value": False, "negate": True}
    _assert(e.evaluate(cond2, ctx).passed, "negated false == true")
    print("  PASS: Negation in conditions")

# ── Test: Schema validation ───────────────────────────────

import jsonschema

def test_schema_validation():
    """
    Validate a workflow dict against the JSON schema.
    1. Create a valid workflow dict
    2. Create an invalid workflow dict (missing required field)
    3. Verify jsonschema catches the invalid one
    """
    schema_path = OVERCR_ROOT / "workflow_composition" / "schema" / "composite_workflow.schema.json"
    with open(schema_path) as f:
        schema = json.load(f)
    
    # Valid workflow
    valid_workflow = {
        "workflow_id": "wf_123",
        "workflow_name": "Test Workflow",
        "version": "1.0.0",
        "node_definitions": [
            {
                "node_id": "node_1",
                "subagent": "verify",
                "packet_type": "verification"
            }
        ]
    }
    try:
        jsonschema.validate(valid_workflow, schema)
        _assert(True, "Valid workflow accepted")
    except jsonschema.ValidationError as e:
        print(f"  FAIL: Valid workflow rejected: {e.message}")
        FAILED = True
    
    # Invalid workflow (missing required workflow_id)
    invalid_workflow = {
        "workflow_name": "Test Workflow",
        "version": "1.0.0",
        "node_definitions": []
    }
    try:
        jsonschema.validate(invalid_workflow, schema)
        print("  FAIL: Invalid workflow accepted (should have raised ValidationError)")
        FAILED = True
    except jsonschema.ValidationError as e:
        _assert(True, "Invalid workflow rejected: " + e.message)
    
    # Invalid workflow (missing required node_definitions)
    invalid_workflow2 = {
        "workflow_id": "wf_456",
        "workflow_name": "Test Workflow",
        "version": "1.0.0"
    }
    try:
        jsonschema.validate(invalid_workflow2, schema)
        print("  FAIL: Invalid workflow accepted (should have raised ValidationError)")
        FAILED = True
    except jsonschema.ValidationError as e:
        _assert(True, "Invalid workflow rejected: " + e.message)
    
    print("  PASS: Schema validation")
# ── Main ──────────────────────────────────────────────────

def main():
    global FAILED
    print("=" * 60)
    print("OverCR v2.8.0 — Workflow Composition Tests")
    print("=" * 60)

    tests = [
        ("Confidence threshold routing", test_confidence_threshold_routing),
        ("Trust tier comparison", test_trust_tier_comparison),
        ("Conditional branch routing", test_conditional_branch_routing),
        ("Validation result routing", test_validation_result_routing),
        ("Routing policy next_node", test_routing_policy_next_node),
        ("Retry limits enforced", test_retry_limits_enforced),
        ("Escalation triggers", test_escalation_triggers),
        ("Fallback activation", test_fallback_activation),
        ("Illegal transition rejection", test_illegal_transition_rejection),
        ("State machine transitions", test_state_machine_transitions),
        ("Subworkflow loading", test_subworkflow_loading),
        ("Subworkflow cycle detection", test_subworkflow_cycle_detection),
        ("Branch trace recording", test_branch_trace_recording),
        ("Deterministic routing", test_deterministic_routing),
        ("Malformed condition rejection", test_malformed_condition_rejection),
        ("Routing policy records", test_routing_policy_records),
        ("Escalation export", test_escalation_export),
        ("Full routing pipeline", test_full_routing_pipeline),
        ("Schema validation", test_schema_validation),
    ]
    for name, fn in tests:
        print(f"\n--- {name} ---")
        try:
            fn()
        except Exception as e:
            print(f"  ERROR: {e}")
            import traceback; traceback.print_exc()
            FAILED = True

    print("\n" + "=" * 60)
    print("RESULT: ALL TESTS PASSED" if not FAILED else "RESULT: SOME TESTS FAILED")
    return 1 if FAILED else 0

if __name__ == "__main__":
    sys.exit(main())
