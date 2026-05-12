#!/usr/bin/env python3
"""
OverCR v0.1.0 Approval-Boundary Test
======================================

Simulates an operator-facing final packet that recommends sending a message.
Tests that the boundary between "may prepare" and "may execute" is enforced.

Core properties tested:
  1. System MAY prepare the message (task progresses through its lifecycle,
     response packet is stored, validation passes, routing decides next hop)
  2. System MAY mark approval_required=true (gate identifies PypER/outreach
     as always-gated, routes to approval_pending)
  3. System MUST NOT execute send/contact (outbound is blocked until explicit
     operator approval; outbound_contact is captured as an untrusted claim)
  4. Task remains in approval_pending until human action (no auto-advance
     past the approval gate, operator_summary reflects the boundary)

This test is distinct from test_failure_governance_approval_bypass.py which
tests a *malicious* packet trying to bypass the gate. Here, the packet is
*legitimate* — it contains valid recommendations and correct approval flags —
but the system must still hold the boundary: prepare yes, execute no.
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
from runtime.approval_gate import ApprovalGate, ApprovalGateError
from runtime.task_store import VALID_TRANSITIONS


# ── Helpers ──────────────────────────────────────────────────

FAILED = False  # global tracker


def banner(text: str, width: int = 76):
    print(f"\n{'=' * width}")
    print(f"  {text}")
    print(f"{'=' * width}")


def section(text: str):
    print(f"\n--- {text} ---")


def make_pyper_approval_packet(
    task_id: str,
    upstream_task_id: str,
    outbound_contact: dict | None = None,
) -> dict:
    """
    Construct a *legitimate* PypER approval packet that recommends
    sending an outreach message. This is NOT malicious — the packet
    correctly sets approval_required=true. The system should:
      - Accept and validate the packet
      - Route to approval_pending
      - Block outbound action until operator approves
    """
    packet = {
        "packet_type": "pyper_approval",
        "version": "1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "pyper",
        "target": "overcr",
        "task_id": task_id,
        "upstream_task_id": upstream_task_id,
        "summary": (
            "Outreach draft for Region X Manufacturing — "
            "recommended send after operator review."
        ),
        "draft_data": {
            "prospects": [
                {
                    "entity": "Region X Manufacturing Corp",
                    "approach_type": "warm_intro",
                    "personalization_signals": [
                        "Recent facility expansion announcement",
                        "Public sustainability initiative launched Q3",
                        "C-suite blog post on digital transformation",
                    ],
                    "drafts": [
                        {
                            "channel": "email",
                            "subject": "Aligning on sustainability & digital transformation",
                            "body": (
                                "Dear [First Name],\n\n"
                                "I noticed Region X Manufacturing's recent sustainability "
                                "initiative and digital transformation efforts. Our platform "
                                "has helped similar organizations reduce overhead by 15-20%.\n\n"
                                "Would you be open to a brief call this week?\n\n"
                                "Best regards,\n[Sender]"
                            ),
                            "tone": "consultative",
                            "evidence_citations": [
                                f"{upstream_task_id}: facility expansion",
                                f"{upstream_task_id}: sustainability initiative",
                                f"{upstream_task_id}: digital transformation blog",
                            ],
                        }
                    ],
                    "yield_score": 72,
                    "fit_score": 68,
                }
            ]
        },
        # Correct governance — this is a legitimate packet
        "approval_required": True,
        "next_steps_recommendation": (
            "Operator review recommended before sending outreach email. "
            "Yield score 72, fit score 68 — strong candidate."
        ),
        "audit_trail": {
            "upstream_sources": [f"{upstream_task_id} (CryER recon)"],
            "draft_methods": ["evidence-backed personalization", "signal-matched approach"],
            "review_count": 1,
        },
    }

    # Optionally include outbound_contact (legitimate intent declaration)
    if outbound_contact is not None:
        packet["outbound_contact"] = outbound_contact

    return packet


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

def run_approval_boundary_test(workspace_arg: str | None = None):
    global FAILED

    workspace = workspace_arg or "/tmp/overcr-approval-boundary-test"

    # Clean workspace
    if os.path.exists(workspace):
        shutil.rmtree(workspace)
    os.makedirs(workspace, exist_ok=True)
    orch_dir = os.path.join(workspace, "orchestration", "tasks")
    os.makedirs(orch_dir, exist_ok=True)
    with open(os.path.join(workspace, "orchestration", "task_counter.json"), "w") as f:
        json.dump({"last_task_id": "0000", "last_updated": datetime.now(timezone.utc).isoformat()}, f)

    # Copy validator into workspace
    tools_dir = os.path.join(workspace, "tools")
    os.makedirs(tools_dir, exist_ok=True)
    shutil.copy2(str(CORE_DIR / "tools" / "validate_packet.py"), os.path.join(tools_dir, "validate_packet.py"))

    banner("OverCR v0.1.0 — Approval-Boundary Test")
    print(f"  Workspace : {workspace}")
    print(f"  Time       : {datetime.now(timezone.utc).isoformat()}")
    print(f"  Purpose    : Verify that a legitimate PypER packet recommending")
    print(f"               send is prepared but NOT executed without approval")
    print(f"  Boundary   : may prepare YES / may mark approval_required YES /")
    print(f"               must NOT execute send/contact / stays approval_pending")

    rt = OverCRRuntime(workspace)
    gate = ApprovalGate()

    # ═══════════════════════════════════════════════════════════
    # PHASE 1: Create Upstream CryER Recon Task
    # ═══════════════════════════════════════════════════════════
    section("Phase 1: Create Upstream CryER Recon Task")
    task1 = rt.create_task(
        domain="recon",
        description="Recon on Region X Manufacturing — approval boundary test",
        instruction="Gather public reputation and hiring signals for Region X Manufacturing.",
        input_context={"entity": "Region X Manufacturing Corp", "type": "business"},
    )
    task1 = rt.simulate_acknowledge(task1["task_id"])
    print(f"  Upstream task: {task1['task_id']}  state={task1['state']}")

    # Give CryER a recon response to make the pipeline realistic
    cryer_packet = {
        "packet_type": "cryer_recon",
        "version": "1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "cryer",
        "target": "overcr",
        "task_id": task1["task_id"],
        "summary": "Region X Manufacturing: strong signals. Expansion + sustainability initiative.",
        "recon_data": {
            "targets": [
                {
                    "entity": "Region X Manufacturing Corp",
                    "type": "business",
                    "signals": {
                        "reputation": {
                            "yield_score": 72,
                            "confidence": 85,
                            "risk_flags": [],
                        }
                    },
                    "raw_sources": [
                        "https://example.com/regionx-news",
                        "https://example.com/regionx-careers",
                    ],
                }
            ]
        },
        "audit_trail": {
            "collection_timestamps": [datetime.now(timezone.utc).isoformat()],
            "methods_used": ["public_web_crawl", "directory_scan"],
        },
        "approval_required": False,
        "next_steps_recommendation": "Submit to OverCR for routing to outreach subagent.",
    }
    task1 = rt.receive_response(task1["task_id"], cryer_packet)
    val1 = rt.validate_response(task1["task_id"])
    assert_test(
        "CryER packet validates successfully",
        val1["valid"],
        f"Expected valid=True, got {val1['valid']} with errors={val1.get('errors', [])}",
    )

    route1 = rt.route(task1["task_id"])
    print(f"  CryER routed to: {route1['routing_target']}  creates_downstream={route1['creates_downstream_task']}")
    print(f"  CryER final state: {rt.get_task(task1['task_id'])['state']}")

    # ═══════════════════════════════════════════════════════════
    # PHASE 2: Create Downstream PypER Outreach Task
    # ═══════════════════════════════════════════════════════════
    section("Phase 2: Create Downstream PypER Outreach Task")
    task2 = rt.create_downstream_task(
        upstream_task_id=task1["task_id"],
        routing_target="pyper",
        instruction_override="Draft outreach email for Region X Manufacturing based on recon findings.",
    )
    task2 = rt.simulate_acknowledge(task2["task_id"])
    print(f"  PypER task: {task2['task_id']}  state={task2['state']}")

    # ═══════════════════════════════════════════════════════════
    # PHASE 3: Submit Legitimate PypER Packet (recommends send)
    # ═══════════════════════════════════════════════════════════
    section("Phase 3: Submit PypER Approval Packet (recommends send, approval_required=true)")

    pyper_packet = make_pyper_approval_packet(
        task_id=task2["task_id"],
        upstream_task_id=task1["task_id"],
        outbound_contact={
            "method": "email",
            "recipient": "contact@regionxmanufacturing.example.com",
            "intent": "warm_outreach",
            "channel": "email",
        },
    )
    task2 = rt.receive_response(task2["task_id"], pyper_packet)
    print(f"  Packet received. Task state: {task2['state']}")
    print(f"  approval_required in packet: {pyper_packet.get('approval_required')}")
    print(f"  outbound_contact in packet: {pyper_packet.get('outbound_contact', {}).get('method')}")

    # ═══════════════════════════════════════════════════════════
    # PHASE 4: Validate — Packet Should PASS (it's legitimate)
    # ═══════════════════════════════════════════════════════════
    section("Phase 4: Validate Packet — LEGITIMATE Packet Should PASS")

    validation = rt.validate_response(task2["task_id"])
    print(f"\n  Validation result: {'PASS' if validation['valid'] else 'FAIL'}")
    print(f"  Errors:   {len(validation['errors'])}")
    for e in validation["errors"]:
        print(f"    ERROR: {e}")
    print(f"  Warnings: {len(validation['warnings'])}")
    for w in validation["warnings"]:
        print(f"    WARN:  {w}")

    # Test 1: Legitimate packet validates
    assert_test(
        "Legitimate PypER packet validates successfully",
        validation["valid"],
        f"Packet valid={validation['valid']}, errors: {validation['errors']}",
    )

    # Test 2: Task advances to validation_passed
    task2 = rt.get_task(task2["task_id"])
    assert_test(
        "Task state is 'validation_passed'",
        task2["state"] == "validation_passed",
        f"Task state is '{task2['state']}', expected 'validation_passed'",
    )

    # ═══════════════════════════════════════════════════════════
    # PHASE 5: Route — Task Must Reach approval_pending
    # ═══════════════════════════════════════════════════════════
    section("Phase 5: Route — Task MUST Reach approval_pending")

    route2 = rt.route(task2["task_id"])
    print(f"  Routing target: {route2['routing_target']}")
    print(f"  Routing reason: {route2['reason']}")
    print(f"  Creates downstream: {route2.get('creates_downstream_task', False)}")
    print(f"  Final state after route: {route2['final_state']}")

    # Test 3: PypER routes to operator
    assert_test(
        "PypER routes to operator (not to another subagent)",
        route2["routing_target"] == "operator",
        f"Routing target is '{route2['routing_target']}', expected 'operator'",
    )

    # Test 4: Task state is approval_pending (not completed, not routed)
    task2 = rt.get_task(task2["task_id"])
    assert_test(
        "Task state is 'approval_pending' (held at gate)",
        task2["state"] == "approval_pending",
        f"Task state is '{task2['state']}', expected 'approval_pending'",
    )

    # ═══════════════════════════════════════════════════════════
    # PHASE 6: Approval Gate Enforcement — Verify the Boundary
    # ═══════════════════════════════════════════════════════════
    section("Phase 6: Approval Gate — Verify the Boundary")

    # Test 5: Gate identifies the task as approval_required
    gate_required = gate.check_approval_required(task2)
    assert_test(
        "Gate confirms approval_required=true for PypER task",
        gate_required is True,
        f"check_approval_required returned {gate_required}, expected True",
    )

    # Test 6: Gate blocks completion (direct path to 'completed' is forbidden)
    gate_decision = gate.enforce_gate(task2, "completed")
    assert_test(
        "Gate blocks direct completion (approval_required + not yet approved)",
        not gate_decision["allowed"],
        f"gate allowed completion: {gate_decision}",
    )
    print(f"  Gate block reason: {gate_decision['reason']}")

    # Test 7: Gate blocks outbound action
    blocked, block_reason = gate.should_block_outbound(task2)
    assert_test(
        "Outbound action is BLOCKED (no send/contact yet)",
        blocked,
        f"should_block_outbound returned {blocked}, expected True",
    )
    print(f"  Outbound block reason: {block_reason}")

    # Test 8: Cannot advance task to 'completed' from approval_pending
    try:
        rt.task_store.advance_state(task2["task_id"], "completed", "attempt to bypass approval")
        assert_test(
            "State machine BLOCKS approval_pending -> completed",
            False,
            "State machine allowed illegal transition!",
        )
    except ValueError as e:
        print(f"  State machine correctly REJECTED: {e}")
        assert_test(
            "State machine BLOCKS approval_pending -> completed",
            True,
            f"ValueError: {e}",
        )

    # ═══════════════════════════════════════════════════════════
    # PHASE 7: Operator Summary — Verify Human-Facing Boundary
    # ═══════════════════════════════════════════════════════════
    section("Phase 7: Operator Summary — Human-Facing Boundary")

    summary = rt.operator_summary(task2["task_id"])
    print(f"\n  Operator Summary:")
    print(json.dumps(summary, indent=4))

    gov = summary.get("governance", {})
    claims = summary.get("packet_claims", {})

    # Test 9: Summary shows approval_pending state
    assert_test(
        "Operator summary shows state='approval_pending'",
        summary.get("state") == "approval_pending",
        f"Summary state='{summary.get('state')}', expected 'approval_pending'",
    )

    # Test 10: Governance fields — approval_required is True (from gate)
    assert_test(
        "governance.approval_required = True (gate-authenticated)",
        gov.get("approval_required") is True,
        f"governance.approval_required={gov.get('approval_required')}, expected True",
    )

    # Test 11: Governance fields — outbound_blocked is True
    assert_test(
        "governance.outbound_blocked = True (gate-authenticated)",
        gov.get("outbound_blocked") is True,
        f"governance.outbound_blocked={gov.get('outbound_blocked')}, expected True",
    )

    # Test 12: Governance fields — execution_authority reflects operator decision required
    assert_test(
        "governance.execution_authority = 'operator_decision_required'",
        gov.get("execution_authority") == "operator_decision_required",
        f"governance.execution_authority={gov.get('execution_authority')}, expected 'operator_decision_required'",
    )

    # Test 13: Packet claims captured honestly (including outbound intent)
    assert_test(
        "packet_claims.approval_required = True (matches packet truthfully)",
        claims.get("approval_required") is True,
        f"packet_claims.approval_required={claims.get('approval_required')}, expected True",
    )

    # Test 14: outbound_contact is in packet_claims (untrusted)
    assert_test(
        "packet_claims.outbound_contact captured (untrusted intent declaration)",
        claims.get("outbound_contact") is not None,
        f"packet_claims.outbound_contact={claims.get('outbound_contact')}, expected dict",
    )

    # Test 15: next_steps reference operator review (not "send immediately")
    next_steps = summary.get("next_steps", [])
    next_steps_text = " ".join(next_steps).lower()
    assert_test(
        "next_steps reference operator review/decision",
        any("review" in s.lower() or "approve" in s.lower() or "reject" in s.lower() for s in next_steps),
        f"next_steps do not reference operator review: {next_steps}",
    )
    assert_test(
        "next_steps do NOT authorize sending",
        "send" not in next_steps_text or "no further action" in next_steps_text,
        f"next_steps appear to authorize sending: {next_steps}",
    )

    # ═══════════════════════════════════════════════════════════
    # PHASE 8: Attempt Direct Outbound — Must Be Blocked
    # ═══════════════════════════════════════════════════════════
    section("Phase 8: Attempt Direct Outbound — Must Be Blocked")

    # Even if someone tries to call should_block_outbound from different angles,
    # it must remain blocked
    for test_desc, test_state, test_approval in [
        ("approval_pending + no approval", "approval_pending", None),
        ("routed + no approval", "routed", None),
        ("in_progress + no approval", "in_progress", None),
    ]:
        # We can't change task state illegally, so use a synthetic task dict
        synthetic = {
            "task_id": "test-boundary",
            "state": test_state,
            "assigned_subagent": "pyper",
            "domain": "outreach",
            "response_packet": {"approval_required": True},
            "operator_approval": test_approval,
        }
        synth_blocked, synth_reason = gate.should_block_outbound(synthetic)
        assert_test(
            f"Outbound blocked for {test_desc}",
            synth_blocked,
            f"Outbound not blocked for {test_desc}: reason={synth_reason}",
        )

    # ═══════════════════════════════════════════════════════════
    # PHASE 9: Approve the Task — Boundary Opens Only After
    #           Explicit Human Action
    # ═══════════════════════════════════════════════════════════
    section("Phase 9: Approve the Task — Boundary Opens Only After Human Action")

    task2 = rt.process_approval(
        task2["task_id"],
        decision="approved",
        reason="Operator reviewed outreach draft and approves sending.",
        operator="operator",
    )
    print(f"  Post-approval state: {task2['state']}")

    # Test 16: After operator approval, PypER task auto-completes
    # (process_approval routes to operator -> auto-completes since no downstream task)
    assert_test(
        "Task reaches terminal state after operator approval (approved -> completed)",
        task2["state"] in ("approved", "completed"),
        f"Task state is '{task2['state']}', expected 'approved' or 'completed'",
    )

    # The approval record must be stored regardless of auto-completion
    approval = task2.get("operator_approval", {})
    assert_test(
        "operator_approval.decision = 'approved'",
        approval.get("decision") == "approved",
        f"operator_approval.decision={approval.get('decision')}, expected 'approved'",
    )
    assert_test(
        "operator_approval.operator = 'operator'",
        approval.get("operator") == "operator",
        f"operator_approval.operator={approval.get('operator')}, expected 'operator'",
    )

    # Test 18: After approval, outbound is UNBLOCKED
    task2 = rt.get_task(task2["task_id"])
    post_blocked, post_reason = gate.should_block_outbound(task2)
    assert_test(
        "After operator approval, outbound is UNBLOCKED",
        not post_blocked,
        f"After approval, outbound still blocked: reason={post_reason}",
    )
    print(f"  Post-approval outbound: {'unblocked' if not post_blocked else 'BLOCKED'}")
    print(f"  Reason: {post_reason}")

    # Test 19: Approval was exercised — the gate was respected even though
    # auto-completion happened. The key boundary is: no outbound WITHOUT approval.
    # Once operator approved, the boundary opened correctly.
    assert_test(
        "Operator approval exercised — boundary opened correctly",
        not post_blocked and approval.get("decision") == "approved",
        "Boundary did not open after operator approval",
    )

    # ═══════════════════════════════════════════════════════════
    # PHASE 10: Verify Task State — Auto-Completed After Approval
    # ═══════════════════════════════════════════════════════════
    section("Phase 10: Verify Task State — Auto-Completed After Approval")

    # process_approval already auto-completed the task (routed to operator,
    # no downstream task). Verify terminal state is correct.
    task2 = rt.get_task(task2["task_id"])
    print(f"  Final state: {task2['state']}")

    # Test 20: Task is in 'completed' state
    assert_test(
        "Task is in 'completed' state (auto-completed after approval)",
        task2["state"] == "completed",
        f"Task state is '{task2['state']}', expected 'completed'",
    )

    # Test 21: Completed task with approval still allows outbound
    final_blocked, final_reason = gate.should_block_outbound(task2)
    assert_test(
        "Completed task with operator approval: outbound unblocked",
        not final_blocked,
        f"Completed task outbound still blocked: {final_reason}",
    )

    # ═══════════════════════════════════════════════════════════
    # PHASE 11: Audit Trail — Verify End-to-End Evidence
    # ═══════════════════════════════════════════════════════════
    section("Phase 11: Audit Trail — Verify End-to-End Evidence")

    audit_entries = rt.get_audit_trail(task_id=task2["task_id"], limit=50)
    audit_types = [e.get("entry_type") for e in audit_entries]

    # Test 22: Audit trail includes all major lifecycle events
    assert_test(
        "Audit trail has approval_action entries",
        "approval_action" in audit_types,
        f"approval_action not in audit types: {set(audit_types)}",
    )

    # Test 23: Approval audit entry records the operator decision
    approval_entries = [e for e in audit_entries if e.get("entry_type") == "approval_action"]
    assert_test(
        "Audit records approval decision",
        len(approval_entries) > 0,
        "No approval_action entries found",
    )
    if approval_entries:
        ae = approval_entries[0]
        assert_test(
            "Audit records operator as decision-maker",
            ae.get("details", {}).get("operator") == "operator",
            f"Operator in audit: {ae.get('details', {}).get('operator')}",
        )
        assert_test(
            "Audit records decision='approved'",
            ae.get("details", {}).get("decision") == "approved",
            f"Decision in audit: {ae.get('details', {}).get('decision')}",
        )

    # Test 24: State transitions include approval_pending -> approved
    state_transitions = [
        (e.get("details", {}).get("from_state"), e.get("details", {}).get("to_state"))
        for e in audit_entries
        if e.get("entry_type") == "state_transition"
    ]
    assert_test(
        "Audit captures approval_pending -> approved transition",
        ("approval_pending", "approved") in state_transitions,
        f"approval_pending -> approved not in transitions: {state_transitions}",
    )
    assert_test(
        "Audit captures approved -> completed transition",
        ("approved", "completed") in state_transitions,
        f"approved -> completed not in transitions: {state_transitions}",
    )

    # ═══════════════════════════════════════════════════════════
    # PHASE 12: Rejection Path — Task Stays Blocked
    # ═══════════════════════════════════════════════════════════
    section("Phase 12: Rejection Path — Task Stays Blocked Until New Approval")

    # Create a second PypER task to test the rejection path
    task3 = rt.create_downstream_task(
        upstream_task_id=task1["task_id"],
        routing_target="pyper",
        instruction_override="Second outreach draft for rejection path test.",
    )
    task3 = rt.simulate_acknowledge(task3["task_id"])
    pyper_packet_3 = make_pyper_approval_packet(
        task_id=task3["task_id"],
        upstream_task_id=task1["task_id"],
    )
    rt.receive_response(task3["task_id"], pyper_packet_3)
    rt.validate_response(task3["task_id"])
    rt.route(task3["task_id"])

    task3 = rt.get_task(task3["task_id"])
    print(f"  Task 3 state: {task3['state']}")

    assert_test(
        "Second PypER task reaches approval_pending",
        task3["state"] == "approval_pending",
        f"Task 3 state={task3['state']}, expected 'approval_pending'",
    )

    # Reject the task
    task3 = rt.process_approval(
        task3["task_id"],
        decision="rejected",
        reason="Draft tone too aggressive.",
        operator="operator",
    )
    print(f"  Post-rejection state: {task3['state']}")

    # Test 25: After rejection, task goes to 'rejected' then 'assigned' (revision)
    assert_test(
        "Rejected task enters revision loop (state='assigned')",
        task3["state"] == "assigned",
        f"Task 3 state after rejection={task3['state']}, expected 'assigned'",
    )

    # Test 26: Rejected task outbound is still blocked
    rejected_blocked, rejected_reason = gate.should_block_outbound(task3)
    assert_test(
        "Rejected task outbound is STILL BLOCKED",
        rejected_blocked,
        f"Rejected task outbound not blocked: {rejected_reason}",
    )

    # Test 27: revision count is 1
    assert_test(
        "Revision count is 1 after first rejection",
        task3.get("revision_count") == 1,
        f"revision_count={task3.get('revision_count')}, expected 1",
    )

    # ═══════════════════════════════════════════════════════════
    # PHASE 13: State Machine — All Boundaries at Every State
    # ═══════════════════════════════════════════════════════════
    section("Phase 13: State Machine — Approval Boundary at Every State")

    # Verify that the approval gate blocks outbound at every state
    # before operator approval for a PypER outreach task
    print("\n  Testing outbound blocking at each pre-approval state:")
    boundary_states = [
        ("created", None),
        ("assigned", None),
        ("in_progress", None),
        ("response_received", None),
        ("validation_passed", None),
        ("routed", None),
        ("approval_pending", None),
    ]
    for state, approval in boundary_states:
        synthetic = {
            "task_id": "test-boundary",
            "state": state,
            "assigned_subagent": "pyper",
            "domain": "outreach",
            "response_packet": {"approval_required": True},
            "operator_approval": approval,
        }
        is_blocked, reason = gate.should_block_outbound(synthetic)
        assert_test(
            f"State '{state}': outbound blocked",
            is_blocked,
            f"State '{state}' not blocked: {reason}",
        )

    # Verify outbound is UNBLOCKED after approval
    synthetic_approved = {
        "task_id": "test-boundary",
        "state": "approved",
        "assigned_subagent": "pyper",
        "domain": "outreach",
        "response_packet": {"approval_required": True},
        "operator_approval": {"decision": "approved", "operator": "operator"},
    }
    approved_blocked, approved_reason = gate.should_block_outbound(synthetic_approved)
    assert_test(
        "State 'approved' with operator approval: outbound UNBLOCKED",
        not approved_blocked,
        f"State 'approved' still blocked: {approved_reason}",
    )

    # Verify outbound is UNBLOCKED for completed+approved
    synthetic_completed = {
        "task_id": "test-boundary",
        "state": "completed",
        "assigned_subagent": "pyper",
        "domain": "outreach",
        "response_packet": {"approval_required": True},
        "operator_approval": {"decision": "approved", "operator": "operator"},
    }
    completed_blocked, completed_reason = gate.should_block_outbound(synthetic_completed)
    assert_test(
        "State 'completed' with operator approval: outbound UNBLOCKED",
        not completed_blocked,
        f"State 'completed' still blocked: {completed_reason}",
    )

    # ═══════════════════════════════════════════════════════════
    # PHASE 14: Valid Transitions from approval_pending
    # ═══════════════════════════════════════════════════════════
    section("Phase 14: State Machine — Valid Transitions from approval_pending")

    allowed_from_pending = VALID_TRANSITIONS.get("approval_pending", set())
    print(f"  Allowed transitions from 'approval_pending': {allowed_from_pending}")

    # Test 28: approval_pending can only go to 'approved' or 'rejected'
    assert_test(
        "approval_pending allows only 'approved' and 'rejected'",
        allowed_from_pending == {"approved", "rejected"},
        f"allowed_from_pending={allowed_from_pending}, expected {{'approved', 'rejected'}}",
    )

    # Test 29: approval_pending -> completed is NOT a valid transition
    assert_test(
        "approval_pending -> completed is NOT a valid transition",
        "completed" not in allowed_from_pending,
        f"'completed' is in transitions from approval_pending!",
    )

    # ═══════════════════════════════════════════════════════════
    # PHASE 15: Workspace Integrity — No Unexpected State Leaks
    # ═══════════════════════════════════════════════════════════
    section("Phase 15: Workspace Integrity — No State Leaks")

    all_tasks = rt.list_tasks()
    print(f"  Total tasks in workspace: {len(all_tasks)}")
    for t in all_tasks:
        print(f"    {t['task_id']}: state={t['state']}  subagent={t['assigned_subagent']}")

    # Task 1 (CryER) should be in a terminal or in-progress state
    # Task 2 (PypER approved) should be completed
    # Task 3 (PypER rejected -> revision) should be in assigned state
    assert_test(
        "3 tasks exist in workspace",
        len(all_tasks) == 3,
        f"Expected 3 tasks, found {len(all_tasks)}",
    )

    task2_check = rt.get_task(task2["task_id"])
    assert_test(
        "Task 2 (approved path) is completed",
        task2_check["state"] == "completed",
        f"Task 2 state={task2_check['state']}, expected 'completed'",
    )

    task3_check = rt.get_task(task3["task_id"])
    assert_test(
        "Task 3 (rejection path) is in assigned (revision)",
        task3_check["state"] == "assigned",
        f"Task 3 state={task3_check['state']}, expected 'assigned'",
    )

    # ═══════════════════════════════════════════════════════════
    # FINAL RESULTS
    # ═══════════════════════════════════════════════════════════
    banner("Approval-Boundary Test Results")

    if FAILED:
        print("\n  SOME TESTS FAILED — approval boundary may not be fully enforced!")
        print("  Review the FAIL entries above.\n")
        return 1
    else:
        print("  ALL TESTS PASSED — approval boundary correctly enforced:\n")
        print("  1. System MAY prepare the message (valid packet, validation passes)")
        print("  2. System MAY mark approval_required=true (gate identifies PypER)")
        print("  3. System MUST NOT execute send/contact (outbound blocked)")
        print("  4. Task remains approval_pending until human action")
        print("  5. Operator approval opens the boundary (outbound unblocked)")
        print("  6. Operator rejection stays in revision loop (still blocked)")
        print("  7. State machine blocks approval_pending -> completed")
        print("  8. Audit trail captures full lifecycle including approval decision")
        print("  9. Operator summary shows correct governance (gate-authenticated)")
        print("  10. Outbound blocked at every pre-approval state\n")
        print("  Conclusion: The approval boundary is enforced at the gate,")
        print("  the state machine, AND the operator summary trust boundary.\n")
        return 0


if __name__ == "__main__":
    # Allow workspace path as CLI arg
    workspace = sys.argv[1] if len(sys.argv) > 1 else None
    exit_code = run_approval_boundary_test(workspace)
    sys.exit(exit_code)