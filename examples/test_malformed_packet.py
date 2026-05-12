#!/usr/bin/env python3
"""
OverCR v0.1.0 Malformed-Packet Test
=====================================

Simulates a CryER → PypER flow where the PypER response packet is MALFORMED:
  - Missing task_id
  - Missing timestamp
  - Missing target

Expected results:
  1. Packet validation FAILS (Level 1 catches missing required fields)
  2. Runtime REFUSES routing (task stays in validation_failed, never reaches routed)
  3. Audit trail records the validation failure
  4. No subagent handoff occurs (task never passes validation)
  5. Operator summary reflects the failure state and governance blocked status
  6. Outbound action remains blocked at all times
  7. State machine prevents any forward progress from validation_failed

This test proves that malformed packets are caught early and cannot proceed
through the orchestration pipeline.
"""

import json
import sys
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

# Add core to path
CORE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CORE_DIR))

from runtime.overcr_runtime import OverCRRuntime
from runtime.approval_gate import ApprovalGate

# ── Helpers ──────────────────────────────────────────────────

FAILED = False


def banner(text: str, width: int = 72):
    print(f"\n{'=' * width}")
    print(f"  {text}")
    print(f"{'=' * width}")


def section(text: str):
    print(f"\n--- {text} ---")


def make_cryer_recon_packet(task_id: str) -> dict:
    """Synthesize a valid CryER recon response packet."""
    return {
        "packet_type": "cryer_recon",
        "version": "1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "cryer",
        "target": "overcr",
        "task_id": task_id,
        "summary": (
            "Recon on Example Business Group: yield 72/100. "
            "Active hiring, positive reviews, partial directory presence."
        ),
        "recon_data": {
            "targets": [
                {
                    "entity": "Example Business Group",
                    "type": "business",
                    "signals": {
                        "reviews": {
                            "count": 124,
                            "sentiment": "positive",
                            "recency": "2026-05-01",
                            "sources": ["Public Review Platform A", "Regional Business Directory"],
                        },
                        "engagement": {
                            "social_presence": True,
                            "response_rate": "~60%",
                            "active_signals": [
                                "Regular social media updates (3x/week)",
                                "Seasonal promotion content",
                            ],
                        },
                        "hiring": {
                            "active": True,
                            "roles": ["Operations Coordinator", "Marketing Associate"],
                            "growth_signal": "growing",
                        },
                        "directory": {
                            "listed": True,
                            "directories": ["Public Directory A", "Regional Business Directory"],
                            "completeness": "partial",
                        },
                        "reputation": {
                            "yield_score": 72,
                            "confidence": 78,
                            "risk_flags": [
                                "Moderate review response time",
                                "Partial directory presence",
                            ],
                        },
                    },
                    "raw_sources": [
                        "https://example-directory.com/business/example-business-group",
                        "https://public-reviews.com/example-business-group",
                    ],
                }
            ]
        },
"next_steps_recommendation": "Submit to OverCR for routing to outreach subagent.",
        "audit_trail": {
            "collection_timestamps": [datetime.now(timezone.utc).isoformat()],
            "methods_used": ["public_directory_crawl", "review_aggregation", "job_board_scan"],
        },
    }


def make_malformed_pyper_packet(task_id: str, upstream_task_id: str) -> dict:
    """
    Construct a PypER approval packet that is MALFORMED:
      - task_id is MISSING (Level 1: missing required field)
      - timestamp is MISSING (Level 1: missing required field)
      - target is MISSING (Level 1: missing required field, and Level 5 would
        flag it but we never get there — Level 1 catches it first)

    All other fields are valid to isolate the structural failures.
    """
    return {
        "packet_type": "pyper_approval",
        "version": "1.0",
        # task_id: MISSING
        # timestamp: MISSING
        "source": "pyper",
        # target: MISSING
        "upstream_task_id": upstream_task_id,
        "summary": (
            "MALFORMED: Outreach draft missing task_id, timestamp, and target."
        ),
        "draft_data": {
            "prospects": [
                {
                    "entity": "Example Business Group",
                    "approach_type": "cold_email",
                    "personalization_signals": [
                        "Growing team — hiring Operations Coordinator and Marketing Associate",
                        "124 positive reviews with moderate response time",
                        "Partial directory presence — consolidation opportunity",
                    ],
                    "drafts": [
                        {
                            "channel": "email",
                            "subject": "Helping Example Business Group streamline growth operations",
                            "body": (
                                "Hi [First Name],\n\n"
                                "I noticed Example Business Group is expanding — congrats on the "
                                "recent hires. With your team growing, I wanted to share how similar "
                                "organizations have streamlined their digital operations.\n\n"
                                "Would it be helpful to chat briefly?\n\n"
                                "Best,\n[Sender]"
                            ),
                            "tone": "consultative",
                            "evidence_citations": [
                                f"{upstream_task_id}: hiring signals — Operations Coordinator, Marketing Associate",
                                f"{upstream_task_id}: positive reviews, moderate response time (~60%)",
                                f"{upstream_task_id}: partial directory presence",
                            ],
                        }
                    ],
                    "yield_score": 72,
                    "fit_score": 80,
                }
            ]
        },
        "approval_required": True,
        "next_steps_recommendation": "Present to operator for review and approval before any outbound action.",
        "audit_trail": {
            "upstream_sources": [f"{upstream_task_id} (CryER recon)"],
            "draft_methods": ["evidence-backed personalization", "objection anticipation"],
            "review_count": 1,
        },
    }


def make_valid_pyper_packet(task_id: str, upstream_task_id: str) -> dict:
    """A VALID PypER packet for the comparison test."""
    return {
        "packet_type": "pyper_approval",
        "version": "1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "pyper",
        "target": "overcr",
        "task_id": task_id,
        "upstream_task_id": upstream_task_id,
        "summary": "Valid outreach draft for Example Business Group.",
        "draft_data": {
            "prospects": [
                {
                    "entity": "Example Business Group",
                    "approach_type": "cold_email",
                    "personalization_signals": [
                        "Growing team — hiring Operations Coordinator",
                    ],
                    "drafts": [
                        {
                            "channel": "email",
                            "subject": "Helping streamline operations",
                            "body": "Hi [First Name],\n\nWould it be helpful to chat briefly?\n\nBest,\n[Sender]",
                            "tone": "consultative",
                            "evidence_citations": [
                                f"{upstream_task_id}: hiring signals",
                            ],
                        }
                    ],
                    "yield_score": 72,
                    "fit_score": 80,
                }
            ]
        },
        "approval_required": True,
        "next_steps_recommendation": "Present to operator for review.",
        "audit_trail": {
            "upstream_sources": [f"{upstream_task_id} (CryER recon)"],
            "draft_methods": ["evidence-backed personalization"],
            "review_count": 1,
        },
    }


def assert_test(name: str, condition: bool, detail: str = ""):
    """Assert a test condition and track failures."""
    global FAILED
    status = "PASS" if condition else "FAIL"
    if not condition:
        FAILED = True
    print(f"  [{status}] {name}")
    if detail:
        print(f"         {detail}")


# ── Main Test ────────────────────────────────────────────────

def run_malformed_packet_test():
    global FAILED

    # Clean workspace
    workspace = "/tmp/overcr-malformed-packet-test"
    if os.path.exists(workspace):
        shutil.rmtree(workspace)
    os.makedirs(workspace, exist_ok=True)
    orch_dir = os.path.join(workspace, "orchestration", "tasks")
    os.makedirs(orch_dir, exist_ok=True)
    with open(os.path.join(workspace, "orchestration", "task_counter.json"), "w") as f:
        json.dump({"last_task_id": "0000", "last_updated": datetime.now(timezone.utc).isoformat()}, f)

    # Copy the validator
    tools_dir = os.path.join(workspace, "tools")
    os.makedirs(tools_dir, exist_ok=True)
    shutil.copy2(
        str(CORE_DIR / "tools" / "validate_packet.py"),
        os.path.join(tools_dir, "validate_packet.py"),
    )

    banner("OverCR v0.1.0 — Malformed-Packet Test")
    print(f"  Workspace : {workspace}")
    print(f"  Time       : {datetime.now(timezone.utc).isoformat()}")
    print(f"  Purpose    : Prove malformed packets fail validation and cannot")
    print(f"               proceed to routing or subagent handoff")
    print(f"  Attack     : Missing task_id, timestamp, and target from PypER packet")

    rt = OverCRRuntime(workspace)

    # ═══════════════════════════════════════════════════════════
    # PHASE 1: Create and complete CryER recon task (normal upstream)
    # ═══════════════════════════════════════════════════════════
    section("Phase 1: Create CryER Recon Task (upstream — normal flow)")
    task1 = rt.create_task(
        domain="recon",
        description="Recon for malformed-packet test",
        instruction="Recon on Example Business Group — public signals only.",
        input_context={"entity": "Example Business Group", "type": "business"},
    )
    task1 = rt.simulate_acknowledge(task1["task_id"])
    cryer_packet = make_cryer_recon_packet(task1["task_id"])
    task1 = rt.receive_response(task1["task_id"], cryer_packet)
    v1 = rt.validate_response(task1["task_id"])
    assert_test("CryER packet validates (upstream is clean)", v1["valid"], f"Errors: {v1['errors']}")

    routing1 = rt.route(task1["task_id"])
    assert_test("CryER routes to PypER", routing1["routing_target"] == "pyper",
                 f"Got {routing1['routing_target']}")
    task1 = rt.get_task(task1["task_id"])
    gate = ApprovalGate()
    if not gate.check_approval_required(task1):
        task1 = rt.complete_task(task1["task_id"], "CryER task completed — routed to PypER")
    print(f"  CryER task: {task1['task_id']}  state={task1['state']}")

    # ═══════════════════════════════════════════════════════════
    # PHASE 2: Create PypER downstream task
    # ═══════════════════════════════════════════════════════════
    section("Phase 2: Create PypER Downstream Task")
    task2 = rt.create_downstream_task(
        upstream_task_id=task1["task_id"],
        routing_target="pyper",
    )
    task2 = rt.simulate_acknowledge(task2["task_id"])
    print(f"  PypER task: {task2['task_id']}  state={task2['state']}")

    # ═══════════════════════════════════════════════════════════
    # PHASE 3: Submit MALFORMED PypER packet (missing task_id, timestamp, target)
    # ═══════════════════════════════════════════════════════════
    section("Phase 3: Submit MALFORMED PypER Packet")
    malformed_packet = make_malformed_pyper_packet(task2["task_id"], task1["task_id"])
    print(f"  Malformed packet fields:")
    print(f"    task_id   = {malformed_packet.get('task_id', '<MISSING>')}")
    print(f"    timestamp = {malformed_packet.get('timestamp', '<MISSING>')}")
    print(f"    target    = {malformed_packet.get('target', '<MISSING>')}")
    print(f"    source    = {malformed_packet.get('source')}")
    print(f"    packet_type = {malformed_packet.get('packet_type')}")

    # NOTE: receive_response verifies task_id matches — since the packet has no
    # task_id, it won't match. We need to handle this differently.
    # The packet's task_id is None/missing, which won't match the task's task_id.
    # This means receive_response will raise a ValueError.
    packet_tid = malformed_packet.get("task_id")
    expected_tid = task2["task_id"]
    assert_test(
        "Malformed packet task_id does NOT match expected task_id",
        packet_tid != expected_tid,
        f"Packet task_id='{packet_tid}', expected to differ from '{expected_tid}'",
    )
    assert_test(
        "Malformed packet task_id is None (missing)",
        packet_tid is None,
        f"Expected None, got '{packet_tid}'",
    )

    # receive_response should REJECT the packet due to task_id mismatch
    receive_error = None
    try:
        rt.receive_response(task2["task_id"], malformed_packet)
    except ValueError as e:
        receive_error = str(e)
        print(f"  receive_response correctly REJECTED: {e}")

    assert_test(
        "receive_response raises ValueError for task_id mismatch",
        receive_error is not None,
        "receive_response did NOT raise an error for malformed packet!",
    )
    if receive_error:
        assert_test(
            "Error message mentions task_id mismatch",
            "task_id" in receive_error.lower(),
            f"Error message: {receive_error}",
        )

    # ═══════════════════════════════════════════════════════════
    # PHASE 4: Bypass receive_response — test the validator directly
    # ═══════════════════════════════════════════════════════════
    section("Phase 4: Standalone 6-Level Validator on Malformed Packet")
    validator = rt.validator
    valid, errors, warnings = validator.validate_packet(malformed_packet)

    assert_test(
        "Validator REJECTS the malformed packet",
        not valid,
        f"Validator passed the malformed packet as valid!",
    )

    # Count and categorize Level 1 errors
    l1_missing = [e for e in errors if "Level 1" in e and "missing" in e]
    l1_fields_missing = [e for e in l1_missing if "missing required" in e]
    print(f"\n  Total errors: {len(errors)}")
    print(f"  Level 1 missing-field errors: {len(l1_fields_missing)}")
    for e in errors:
        print(f"    ERROR: {e}")

    assert_test(
        "Level 1 catches missing 'task_id' field",
        any("task_id" in e and "missing" in e for e in errors),
        "No error found for missing task_id",
    )
    assert_test(
        "Level 1 catches missing 'timestamp' field",
        any("timestamp" in e and "missing" in e for e in errors),
        "No error found for missing timestamp",
    )
    assert_test(
        "Level 1 catches missing 'target' field",
        any("target" in e and "missing" in e for e in errors),
        "No error found for missing target",
    )

    # Verify that at least 3 Level 1 missing-field errors were raised
    assert_test(
        "At least 3 Level 1 missing-field errors detected",
        len(l1_fields_missing) >= 3,
        f"Expected >= 3 Level 1 missing-field errors, got {len(l1_fields_missing)}",
    )

    # ═══════════════════════════════════════════════════════════
    # PHASE 5: Force packet into the pipeline (bypass receive_response
    #           task_id check) to test validate_response state machine
    # ═══════════════════════════════════════════════════════════
    section("Phase 5: Force Malformed Packet Through Pipeline (bypass receive_response)")

    # Manually set the response packet on the task record, bypassing the
    # receive_response task_id check. This simulates what would happen if
    # a subagent produced a malformed packet that somehow got past the
    # intake layer. The validator should still catch it.
    malformed_with_tid = malformed_packet.copy()
    malformed_with_tid["task_id"] = task2["task_id"]  # Fix task_id so receive_response accepts it
    # But timestamp and target are still MISSING

    task2 = rt.receive_response(task2["task_id"], malformed_with_tid)
    print(f"  Packet submitted (task_id fixed, timestamp/target still missing)")
    print(f"  Task state: {task2['state']}")

    # Now validate — this should FAIL
    v2 = rt.validate_response(task2["task_id"])
    print(f"\n  Validation result: {'PASS' if v2['valid'] else 'FAIL'}")
    print(f"  Errors:   {len(v2['errors'])}")
    for e in v2["errors"]:
        print(f"    ERROR: {e}")
    print(f"  Warnings: {len(v2['warnings'])}")
    for w in v2["warnings"]:
        print(f"    WARN:  {w}")

    assert_test(
        "Runtime validate_response REJECTS the malformed packet",
        not v2["valid"],
        "validate_response passed the malformed packet!",
    )

    task2 = rt.get_task(task2["task_id"])
    assert_test(
        "Task state is 'validation_failed'",
        task2["state"] == "validation_failed",
        f"Task state is '{task2['state']}', expected 'validation_failed'",
    )

    # ═══════════════════════════════════════════════════════════
    # PHASE 6: Verify routing is REFUSED from validation_failed state
    # ═══════════════════════════════════════════════════════════
    section("Phase 6: Verify Routing is REFUSED From validation_failed")
    route_error = None
    try:
        rt.route(task2["task_id"])
    except ValueError as e:
        route_error = str(e)
        print(f"  route() correctly REJECTED: {e}")

    assert_test(
        "route() raises ValueError from validation_failed state",
        route_error is not None,
        "route() did NOT raise an error — packet could proceed despite invalid state!",
    )
    if route_error:
        assert_test(
            "Error message references the invalid state",
            "validation_failed" in route_error,
            f"Error message: {route_error}",
        )

    # ═══════════════════════════════════════════════════════════
    # PHASE 7: Verify state machine blocks forward progress
    # ═══════════════════════════════════════════════════════════
    section("Phase 7: State Machine Blocks Forward Progress From validation_failed")
    # From validation_failed, valid transitions are: assigned (revision) or abandoned
    # The following transitions should ALL be blocked:
    illegal_targets = ["routed", "approval_pending", "approved", "completed", "response_received"]
    for target_state in illegal_targets:
        try:
            rt.task_store.advance_state(task2["task_id"], target_state, f"illegal transition to {target_state}")
            assert_test(
                f"State machine blocks transition to '{target_state}'",
                False,
                f"State machine ALLOWED transition to '{target_state}' from validation_failed!",
            )
        except ValueError as e:
            assert_test(
                f"State machine blocks transition to '{target_state}'",
                True,
                f"Blocked: ValueError('{e}')",
            )

    # ═══════════════════════════════════════════════════════════
    # PHASE 8: Audit trail records validation failure
    # ═══════════════════════════════════════════════════════════
    section("Phase 8: Audit Trail Records Validation Failure")
    audit_entries = rt.get_audit_trail(task_id=task2["task_id"], limit=100)

    val_entries = [e for e in audit_entries if e.get("entry_type") == "validation_result"]
    assert_test(
        "Audit log contains validation_result entry",
        len(val_entries) > 0,
        "No validation_result entries found in audit log",
    )
    if val_entries:
        val_entry = val_entries[-1]
        assert_test(
            "Audit records validation as FAILED",
            val_entry["details"].get("valid") is False,
            f"Validation result: {val_entry['details'].get('valid')}, expected False",
        )
        assert_test(
            "Audit records error count > 0",
            val_entry["details"].get("error_count", 0) > 0,
            f"Error count: {val_entry['details'].get('error_count', 0)}, expected > 0",
        )
        details_errors = val_entry["details"].get("errors", [])
        l1_errors_in_audit = [e for e in details_errors if "Level 1" in e]
        assert_test(
            "Audit captures Level 1 errors in detail",
            len(l1_errors_in_audit) > 0,
            f"No Level 1 errors found in audit detail: {details_errors}",
        )

    # Check state transition to validation_failed
    state_entries = [e for e in audit_entries if e.get("entry_type") == "state_transition"]
    vf_transitions = [e for e in state_entries
                      if e.get("details", {}).get("to_state") == "validation_failed"]
    assert_test(
        "Audit records state transition to 'validation_failed'",
        len(vf_transitions) > 0,
        "No 'validation_failed' transition found in audit log",
    )

    # ═══════════════════════════════════════════════════════════
    # PHASE 9: Outbound action is ALWAYS blocked
    # ═══════════════════════════════════════════════════════════
    section("Phase 9: Outbound Action Is Always Blocked")
    blocked, block_reason = rt.check_outbound_block(task2["task_id"])
    assert_test(
        "Outbound blocked in validation_failed state",
        blocked,
        f"Outbound not blocked: {block_reason}",
    )
    print(f"  Outbound block reason: {block_reason}")

    # Governance summary should reflect blocked status
    summary = rt.operator_summary(task2["task_id"])
    gov = summary.get("governance", {})
    assert_test(
        "governance.approval_required is True (PypER always gated)",
        gov.get("approval_required") is True,
        f"governance.approval_required={gov.get('approval_required')}, expected True",
    )
    assert_test(
        "governance.outbound_blocked is True",
        gov.get("outbound_blocked") is True,
        f"governance.outbound_blocked={gov.get('outbound_blocked')}, expected True",
    )
    assert_test(
        "governance.validation_passed is False",
        gov.get("validation_passed") is False,
        f"governance.validation_passed={gov.get('validation_passed')}, expected False",
    )
    assert_test(
        "governance.execution_authority restricts action",
        gov.get("execution_authority") in ("operator_decision_required", "outbound_blocked_no_approval"),
        f"governance.execution_authority={gov.get('execution_authority')}",
    )
    assert_test(
        "Operator summary state is 'validation_failed'",
        summary.get("state") == "validation_failed",
        f"Summary state is '{summary.get('state')}', expected 'validation_failed'",
    )

    # Packet claims section should exist even for malformed packets
    claims = summary.get("packet_claims", {})
    assert_test(
        "packet_claims section exists (untrusted claims preserved)",
        isinstance(claims, dict),
        f"Expected dict, got {type(claims)}",
    )
    # Since task_id in the packet was set (we patched it), but timestamp/target are missing
    assert_test(
        "packet_claims.next_steps_recommendation preserved (untrusted)",
        claims.get("next_steps_recommendation") is not None,
        "Expected next_steps_recommendation in packet_claims",
    )

    # next_steps from the runtime should reference validation failure
    runtime_next = " ".join(summary.get("next_steps", []))
    assert_test(
        "Runtime next_steps reference validation failure",
        any(kw in runtime_next.lower() for kw in ["validation", "error", "review"]),
        f"Runtime next_steps don't reference validation: {summary.get('next_steps')}",
    )

    # ═══════════════════════════════════════════════════════════
    # PHASE 10: No subagent handoff occurs
    # ═══════════════════════════════════════════════════════════
    section("Phase 10: No Subagent Handoff Occurred")
    # The task never progressed past validation_failed, so:
    # - No routing_decision should exist on the task
    task2_check = rt.get_task(task2["task_id"])
    assert_test(
        "No routing_decision on the task",
        task2_check.get("routing_decision") is None,
        f"routing_decision exists: {task2_check.get('routing_direction')}",
    )

    # - No operator_approval should exist
    assert_test(
        "No operator_approval on the task",
        task2_check.get("operator_approval") is None,
        f"operator_approval exists: {task2_check.get('operator_approval')}",
    )

    # - No downstream task was created (only 2 tasks exist: CryER + PypER)
    all_tasks = rt.list_tasks()
    assert_test(
        "Only 2 tasks exist (upstream CryER + failed PypER — no downstream)",
        len(all_tasks) == 2,
        f"Expected 2 tasks, found {len(all_tasks)}: {[t['task_id'] for t in all_tasks]}",
    )

    # - No routing audit entries for task2
    routing_entries = [e for e in audit_entries if e.get("entry_type") == "routing_decision"]
    assert_test(
        "No routing audit entries for the failed PypER task",
        len(routing_entries) == 0,
        f"Found routing entries: {routing_entries}",
    )

    # - No approval audit entries (never reached approval_pending)
    approval_entries = [e for e in audit_entries if e.get("entry_type") == "approval_action"]
    assert_test(
        "No approval audit entries (never reached approval gate)",
        len(approval_entries) == 0,
        f"Found approval entries: {approval_entries}",
    )

    # ═══════════════════════════════════════════════════════════
    # PHASE 11: Compare with a valid packet on the same task
    # ═══════════════════════════════════════════════════════════
    section("Phase 11: Positive Control — Valid Packet on Same Task Path")
    # Create a fresh task and submit a VALID packet to show the pipeline
    # works normally when the packet is well-formed
    task3 = rt.create_task(
        domain="recon",
        description="Positive control — valid CryER packet",
        instruction="Valid recon on Example Business Group.",
        input_context={"entity": "Example Business Group", "type": "business"},
    )
    task3 = rt.simulate_acknowledge(task3["task_id"])
    valid_cryer = make_cryer_recon_packet(task3["task_id"])
    task3 = rt.receive_response(task3["task_id"], valid_cryer)
    v3 = rt.validate_response(task3["task_id"])
    assert_test(
        "Valid CryER packet PASSES validation (positive control)",
        v3["valid"],
        f"Valid packet failed validation! Errors: {v3['errors']}",
    )
    task3 = rt.get_task(task3["task_id"])
    assert_test(
        "Task state advances to 'validation_passed' for valid packet",
        task3["state"] == "validation_passed",
        f"Task state is '{task3['state']}', expected 'validation_passed'",
    )
    # Route should succeed
    routing3 = rt.route(task3["task_id"])
    assert_test(
        "Valid packet routes successfully",
        routing3["routing_target"] in ("pyper", "knower", "operator"),
        f"Unexpected routing target: {routing3['routing_target']}",
    )
    task3 = rt.get_task(task3["task_id"])
    assert_test(
        "Task state after route is 'routed' or 'approval_pending'",
        task3["state"] in ("routed", "approval_pending"),
        f"Task state is '{task3['state']}'",
    )

    # ═══════════════════════════════════════════════════════════
    # PHASE 12: Recovery — revision or abandon from validation_failed
    # ═══════════════════════════════════════════════════════════
    section("Phase 12: Recovery From validation_failed")
    # From validation_failed, the task can go to 'assigned' (revision) or 'abandoned'
    task2 = rt.get_task(task2["task_id"])
    assert_test(
        "Task is in validation_failed state before recovery test",
        task2["state"] == "validation_failed",
        f"Task state is '{task2['state']}', expected 'validation_failed'",
    )

    # Test revision path: validation_failed -> assigned
    task2_rev = rt.task_store.advance_state(
        task2["task_id"], "assigned",
        "Reassigning for revision after validation failure"
    )
    assert_test(
        "Task can transition to 'assigned' for revision",
        task2_rev["state"] == "assigned",
        f"Task state is '{task2_rev['state']}', expected 'assigned'",
    )

    # Test abandon path: go back to validation_failed first, then abandon
    # (can't go assigned -> abandoned directly, need to go through the pipeline again
    #  or use abandon_task which checks valid transitions)
    # Actually let's test: from 'assigned' we can go to 'abandoned'
    task2_abandon = rt.task_store.advance_state(
        task2["task_id"], "abandoned",
        "Abandoning task after persistent validation failures"
    )
    assert_test(
        "Task can transition to 'abandoned' from 'assigned'",
        task2_abandon["state"] == "abandoned",
        f"Task state is '{task2_abandon['state']}', expected 'abandoned'",
    )

    # Abandoned state should be terminal
    try:
        rt.task_store.advance_state(task2["task_id"], "assigned", "Attempt to revive abandoned task")
        assert_test("Terminal state 'abandoned' blocks transitions", False,
                     "State machine allowed transition from 'abandoned'!")
    except ValueError as e:
        assert_test("Terminal state 'abandoned' blocks transitions", True,
                     f"Blocked: ValueError('{e}')")

    # ═══════════════════════════════════════════════════════════
    # FULL AUDIT TRAIL
    # ═══════════════════════════════════════════════════════════
    section("Full Audit Trail (PypER Task — Malformed Packet)")
    all_entries = rt.get_audit_trail(task_id=task2["task_id"], limit=200)
    for e in all_entries:
        etype = e.get("entry_type", "?")
        ts = e.get("timestamp", "")[11:19]
        details = e.get("details", {})
        if etype == "state_transition":
            note = f"{details.get('from_state', '?')} -> {details.get('to_state', '?')}"
        elif etype == "validation_result":
            note = f"valid={details.get('valid')} errors={details.get('error_count', 0)}"
        elif etype == "approval_action":
            note = f"{details.get('decision', '?')} by {details.get('operator', '?')}"
        elif etype == "routing_decision":
            note = f"-> {details.get('routing_target', '?')}"
        else:
            note = str(details)[:70]
        print(f"    {ts} [{etype:>20}] {note}")

    # ═══════════════════════════════════════════════════════════
    # TASK RECORDS ON DISK
    # ═══════════════════════════════════════════════════════════
    section("Task Records on Disk")
    tasks = rt.list_tasks()
    for t in tasks:
        tid = t["task_id"]
        state = t["state"]
        domain = t["domain"]
        sub = t["assigned_subagent"]
        upstream = t.get("upstream_task_id") or ""
        vr = t.get("validation_result") or {}
        v_status = vr.get("valid", "N/A")
        print(f"  {tid}  state={state:<20} sub={sub:<8} domain={domain:<16} valid={v_status}  upstream={upstream}")

    # ═══════════════════════════════════════════════════════════
    # FINAL RESULTS
    # ═══════════════════════════════════════════════════════════
    banner("Malformed-Packet Test Results")

    if FAILED:
        print("\n  SOME TESTS FAILED — malformed packets may not be fully caught!\n")
        print("  Review the FAIL entries above.\n")
        return 1
    else:
        print("""
  ALL TESTS PASSED — malformed packets are correctly rejected:

    1.  Packet validation FAILS (Level 1 catches 3+ missing required fields)
    2.  Runtime REFUSES routing from validation_failed state
    3.  Audit trail records the validation failure with error details
    4.  No subagent handoff occurs (no routing, no approval, no downstream task)
    5.  State machine blocks all forward transitions from validation_failed
    6.  Outbound action remains blocked at all stages
    7.  Operator summary reflects validation_failed state and blocked governance
    8.  Positive control confirms valid packets pass normally
    9.  Recovery paths work: validation_failed → assigned (revision) or abandoned
   10.  Terminal state (abandoned) blocks all further transitions

  Conclusion: Malformed packets cannot penetrate the orchestration pipeline.
  The 6-level validator catches structural defects at Level 1, the state machine
  prevents routing from invalid states, and audit trails record every failure.""")

    # Clean up
    print(f"\n  Workspace (preserved for inspection): {workspace}")
    print(f"  Audit log:  {workspace}/runtime/audit.jsonl")
    print(f"  Task files: {workspace}/orchestration/tasks/")
    print()

    return 0


if __name__ == "__main__":
    exit_code = run_malformed_packet_test()
    sys.exit(exit_code)