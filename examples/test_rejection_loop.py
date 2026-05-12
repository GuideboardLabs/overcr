#!/usr/bin/env python3
"""
OverCR v0.1.0 Rejection-Loop Test
===================================

Simulates a normal CryER → PypER flow, but when PypER produces the outreach
packet, the OPERATOR REJECTS it. Tests the full rejection + revision loop
pathway.

Expected results:
  1. PypER task enters 'rejected' state after operator rejection
  2. No outbound action occurs (blocked at all stages)
  3. Audit trail records operator rejection with reason
  4. Task routes back to 'assigned' for revision (under 3-revision limit)
  5. Revision count increments
  6. Second rejection (revision 2) also routes correctly
  7. Third rejection at limit triggers 'abandoned' state
  8. Operator summary correctly reflects governance throughout
  9. Outbound action remains blocked at every stage

This test exercises the REAL state machine, approval gate, and audit writer —
only the subagent response packets are simulated.
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

FAILED = False  # global tracker


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
            "Recon on Example Business Group: strong yield (72/100). "
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
                                "Moderate review response time (2-3 days average)",
                                "Partial directory presence across platforms",
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
        "next_steps_recommendation": (
            "Submit to OverCR for outreach routing. High yield score with actionable signals."
        ),
        "audit_trail": {
            "collection_timestamps": [datetime.now(timezone.utc).isoformat()],
            "methods_used": ["public_directory_crawl", "review_aggregation", "job_board_scan"],
        },
    }


def make_pyper_approval_packet(task_id: str, upstream_task_id: str) -> dict:
    """Synthesize a valid PypER approval response packet."""
    return {
        "packet_type": "pyper_approval",
        "version": "1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "pyper",
        "target": "overcr",
        "task_id": task_id,
        "upstream_task_id": upstream_task_id,
        "summary": (
            "Outreach draft for Example Business Group — consultative approach "
            "addressing growth-stage operational friction."
        ),
        "draft_data": {
            "prospects": [
                {
                    "entity": "Example Business Group",
                    "approach_type": "cold_email",
                    "personalization_signals": [
                        "Growing team — hiring Operations Coordinator and Marketing Associate",
                        "124 positive reviews but moderate response time suggesting capacity strain",
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
        "next_steps_recommendation": (
            "Present to operator for review and approval before any outbound action."
        ),
        "audit_trail": {
            "upstream_sources": [f"{upstream_task_id} (CryER recon)"],
            "draft_methods": ["evidence-backed personalization", "objection anticipation"],
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

def run_rejection_loop_test():
    global FAILED

    # Clean workspace
    workspace = "/tmp/overcr-rejection-loop-test"
    if os.path.exists(workspace):
        shutil.rmtree(workspace)
    os.makedirs(workspace, exist_ok=True)
    orch_dir = os.path.join(workspace, "orchestration", "tasks")
    os.makedirs(orch_dir, exist_ok=True)
    with open(os.path.join(workspace, "orchestration", "task_counter.json"), "w") as f:
        json.dump({"last_task_id": "0000", "last_updated": datetime.now(timezone.utc).isoformat()}, f)

    # Copy the validator into the workspace
    tools_dir = os.path.join(workspace, "tools")
    os.makedirs(tools_dir, exist_ok=True)
    shutil.copy2(
        str(CORE_DIR / "tools" / "validate_packet.py"),
        os.path.join(tools_dir, "validate_packet.py"),
    )

    banner("OverCR v0.1.0 — Rejection-Loop Test")
    print(f"  Workspace : {workspace}")
    print(f"  Time       : {datetime.now(timezone.utc).isoformat()}")
    print(f"  Purpose    : Operator rejects PypER outreach — test rejection loop,")
    print(f"               revision routing, and final abandonment")
    print(f"  Scenario   : Normal CryER→PypER, then operator REJECTS at approval gate")

    rt = OverCRRuntime(workspace)
    gate = ApprovalGate()

    # ═══════════════════════════════════════════════════════════
    # PHASE 1: Create and complete CryER recon task (normal flow)
    # ═══════════════════════════════════════════════════════════
    section("Phase 1: Create CryER Recon Task (upstream)")
    task1 = rt.create_task(
        domain="recon",
        description="Public signal reconnaissance on Example Business Group",
        instruction="Conduct public signal reconnaissance on Example Business Group.",
        input_context={"entity": "Example Business Group", "type": "business"},
    )
    task1 = rt.simulate_acknowledge(task1["task_id"])
    cryer_packet = make_cryer_recon_packet(task1["task_id"])
    task1 = rt.receive_response(task1["task_id"], cryer_packet)
    v1 = rt.validate_response(task1["task_id"])
    assert_test("CryER packet validates", v1["valid"], f"Errors: {v1['errors']}")
    routing1 = rt.route(task1["task_id"])
    assert_test("CryER routes to PypER", routing1["routing_target"] == "pyper",
                 f"Got {routing1['routing_target']}")
    task1 = rt.get_task(task1["task_id"])
    # CryER doesn't need approval — complete it
    if not gate.check_approval_required(task1):
        task1 = rt.complete_task(task1["task_id"], "CryER recon completed — routed to PypER")
    print(f"  CryER task: {task1['task_id']}  state={task1['state']}")

    # ═══════════════════════════════════════════════════════════
    # PHASE 2: Create PypER downstream task (normal flow)
    # ═══════════════════════════════════════════════════════════
    section("Phase 2: Create PypER Downstream Task")
    task2 = rt.create_downstream_task(
        upstream_task_id=task1["task_id"],
        routing_target="pyper",
    )
    task2 = rt.simulate_acknowledge(task2["task_id"])
    pyper_packet = make_pyper_approval_packet(task2["task_id"], task1["task_id"])
    task2 = rt.receive_response(task2["task_id"], pyper_packet)
    print(f"  PypER task: {task2['task_id']}  state={task2['state']}")

    # ═══════════════════════════════════════════════════════════
    # PHASE 3: Validate and route PypER — should hit approval_pending
    # ═══════════════════════════════════════════════════════════
    section("Phase 3: Validate and Route PypER Packet")
    v2 = rt.validate_response(task2["task_id"])
    assert_test("PypER packet validates", v2["valid"], f"Errors: {v2['errors']}")

    routing2 = rt.route(task2["task_id"])
    task2 = rt.get_task(task2["task_id"])
    print(f"  Routing target : {routing2['routing_target']}")
    print(f"  Task state     : {task2['state']}")

    assert_test(
        "PypER task enters approval_pending (approval gate enforced)",
        task2["state"] == "approval_pending",
        f"Expected 'approval_pending', got '{task2['state']}'",
    )

    # Outbound must be blocked at this stage
    blocked, reason = rt.check_outbound_block(task2["task_id"])
    assert_test(
        "Outbound blocked before operator decision",
        blocked,
        f"Outbound not blocked: {reason}",
    )

    # ═══════════════════════════════════════════════════════════
    # PHASE 4: OPERATOR REJECTS (1st rejection)
    # ═══════════════════════════════════════════════════════════
    section("Phase 4: Operator REJECTS PypER Outreach (1st rejection)")
    print("  Operator decision: REJECTED")
    print("  Reason: Outreach tone too generic — needs stronger personalization")

    task2 = rt.process_approval(
        task2["task_id"],
        decision="rejected",
        reason="Outreach tone too generic — needs stronger personalization and local references",
        operator="test_operator",
    )
    print(f"  Task state after rejection: {task2['state']}")
    revision_count = task2.get("revision_count", 0)
    print(f"  Revision count: {revision_count}")

    # ── ASSERTION: Task enters 'assigned' state (revision loop) ──
    # The rejection flow goes: approval_pending -> rejected -> assigned
    assert_test(
        "Task enters 'assigned' state (revision loop, rev 1)",
        task2["state"] == "assigned",
        f"Expected 'assigned', got '{task2['state']}'",
    )

    assert_test(
        "Revision count is 1",
        revision_count == 1,
        f"Expected revision_count=1, got {revision_count}",
    )

    # Outbound must STILL be blocked
    blocked_after_reject, reason_after = rt.check_outbound_block(task2["task_id"])
    assert_test(
        "Outbound still blocked after rejection",
        blocked_after_reject,
        f"Outbound not blocked after rejection: {reason_after}",
    )

    # ── AUDIT: Check that rejection is recorded ──
    audit_entries = rt.get_audit_trail(task_id=task2["task_id"], limit=100)
    approval_entries = [e for e in audit_entries if e.get("entry_type") == "approval_action"]
    revision_entries = [e for e in audit_entries if e.get("entry_type") == "revision_loop"]

    assert_test(
        "Audit records approval_action entry",
        len(approval_entries) > 0,
        "No approval_action entries in audit log",
    )

    if approval_entries:
        reject_entry = approval_entries[-1]
        assert_test(
            "Audit records rejection decision",
            reject_entry["details"].get("decision") == "rejected",
            f"Expected decision='rejected', got '{reject_entry['details'].get('decision')}'",
        )
        assert_test(
            "Audit records rejection reason",
            "generic" in (reject_entry["details"].get("reason") or "").lower(),
            f"Reason not recorded or doesn't match: '{reject_entry['details'].get('reason')}'",
        )
        assert_test(
            "Audit records operator identity",
            reject_entry["details"].get("operator") == "test_operator",
            f"Expected operator='test_operator', got '{reject_entry['details'].get('operator')}'",
        )

    assert_test(
        "Audit records revision_loop entry",
        len(revision_entries) > 0,
        "No revision_loop entries in audit log",
    )

    if revision_entries:
        rev_entry = revision_entries[-1]
        assert_test(
            "Revision entry shows count=1",
            rev_entry["details"].get("revision_count") == 1,
            f"Expected revision_count=1, got {rev_entry['details'].get('revision_count')}",
        )

    # ── AUDIT: State transition includes rejected state ──
    state_transitions = [e for e in audit_entries if e.get("entry_type") == "state_transition"]
    rejected_transitions = [e for e in state_transitions if e["details"].get("to_state") == "rejected"]
    assert_test(
        "Audit records transition to 'rejected' state",
        len(rejected_transitions) > 0,
        "No 'rejected' state transition found in audit log",
    )

    # ═══════════════════════════════════════════════════════════
    # PHASE 5: Simulate revision — PypER resubmits (2nd attempt)
    # ═══════════════════════════════════════════════════════════
    section("Phase 5: PypER Resubmits After 1st Rejection (revision)")
    task2 = rt.simulate_acknowledge(task2["task_id"])
    # Simulate revised packet (better tone)
    pyper_packet_v2 = make_pyper_approval_packet(task2["task_id"], task1["task_id"])
    # Modify the summary to indicate revision
    pyper_packet_v2["summary"] = (
        "REVISED: Outreach draft for Example Business Group — personalized approach "
        "with local market references and specific hiring signal citations."
    )
    pyper_packet_v2["draft_data"]["prospects"][0]["drafts"][0]["body"] = (
        "Hi [First Name],\n\n"
        "I saw Example Business Group is actively hiring for Operations Coordinator "
        "and Marketing Associate — looks like your team is scaling fast. Organizations "
        "at your growth stage often find that streamlining digital ops creates the "
        "capacity to serve more customers without adding overhead.\n\n"
        "Would a 15-minute chat make sense this week?\n\n"
        "Best,\n[Sender]"
    )
    task2 = rt.receive_response(task2["task_id"], pyper_packet_v2)
    v2_rev = rt.validate_response(task2["task_id"])
    assert_test("Revised PypER packet validates", v2_rev["valid"],
                 f"Errors: {v2_rev['errors']}")

    # Route again
    routing2_rev = rt.route(task2["task_id"])
    task2 = rt.get_task(task2["task_id"])
    print(f"  Task state after re-routing: {task2['state']}")
    assert_test(
        "PypER task back at approval_pending after revision",
        task2["state"] == "approval_pending",
        f"Expected 'approval_pending', got '{task2['state']}'",
    )

    # ═══════════════════════════════════════════════════════════
    # PHASE 6: OPERATOR REJECTS AGAIN (2nd rejection)
    # ═══════════════════════════════════════════════════════════
    section("Phase 6: Operator REJECTS Again (2nd rejection)")
    print("  Operator decision: REJECTED")
    print("  Reason: Still too salesy — needs genuine consultative framing")

    task2 = rt.process_approval(
        task2["task_id"],
        decision="rejected",
        reason="Still too salesy — needs genuine consultative framing and case study reference",
        operator="test_operator",
    )
    print(f"  Task state after 2nd rejection: {task2['state']}")
    revision_count = task2.get("revision_count", 0)
    print(f"  Revision count: {revision_count}")

    assert_test(
        "Task enters 'assigned' state (revision loop, rev 2)",
        task2["state"] == "assigned",
        f"Expected 'assigned', got '{task2['state']}'",
    )

    assert_test(
        "Revision count is 2",
        revision_count == 2,
        f"Expected revision_count=2, got {revision_count}",
    )

    # Outbound still blocked
    blocked_2, reason_2 = rt.check_outbound_block(task2["task_id"])
    assert_test(
        "Outbound still blocked after 2nd rejection",
        blocked_2,
        f"Outbound not blocked after 2nd rejection: {reason_2}",
    )

    # ═══════════════════════════════════════════════════════════
    # PHASE 7: 3rd revision cycle — PypER resubmits, operator rejects (3rd)
    # ═══════════════════════════════════════════════════════════
    section("Phase 7: 3rd Revision Cycle — PypER Resubmits, Operator Rejects (3rd)")
    task2 = rt.simulate_acknowledge(task2["task_id"])

    pyper_packet_v3 = make_pyper_approval_packet(task2["task_id"], task1["task_id"])
    pyper_packet_v3["summary"] = (
        "REVISED v3: Outreach draft — consultative framing with case study."
    )

    task2 = rt.receive_response(task2["task_id"], pyper_packet_v3)
    v3 = rt.validate_response(task2["task_id"])
    assert_test("3rd PypER packet validates", v3["valid"], f"Errors: {v3['errors']}")

    routing3 = rt.route(task2["task_id"])
    task2 = rt.get_task(task2["task_id"])
    assert_test(
        "3rd attempt also goes to approval_pending",
        task2["state"] == "approval_pending",
        f"Expected 'approval_pending', got '{task2['state']}'",
    )

    # ═══════════════════════════════════════════════════════════
    # PHASE 8: OPERATOR REJECTS 3rd TIME — revision limit reached
    # ═══════════════════════════════════════════════════════════
    section("Phase 8: Operator REJECTS 3rd Time — Revision Limit Exceeded")
    print("  Operator decision: REJECTED (3rd time)")
    print("  Reason: Outreach not converging — abandon this lead for now")

    task2 = rt.process_approval(
        task2["task_id"],
        decision="rejected",
        reason="Outreach not converging after 3 revisions — abandon this lead",
        operator="test_operator",
    )
    print(f"  Task state after 3rd rejection: {task2['state']}")
    revision_count = task2.get("revision_count", 0)

    assert_test(
        "Task enters 'abandoned' state (revision limit exceeded)",
        task2["state"] == "abandoned",
        f"Expected 'abandoned', got '{task2['state']}'",
    )

    assert_test(
        "Revision count is 3 at abandonment",
        revision_count == 3,
        f"Expected revision_count=3, got {revision_count}",
    )

    # ═══════════════════════════════════════════════════════════
    # PHASE 9: Verify no outbound was ever possible
    # ═══════════════════════════════════════════════════════════
    section("Phase 9: Verify No Outbound Action Was Ever Possible")
    blocked_final, reason_final = rt.check_outbound_block(task2["task_id"])
    assert_test(
        "Outbound blocked in abandoned state",
        blocked_final,
        f"Outbound not blocked in abandoned state: {reason_final}",
    )

    # Verify operator_summary reflects the rejection
    summary = rt.operator_summary(task2["task_id"])
    gov = summary.get("governance", {})

    assert_test(
        "Operator summary shows state = abandoned",
        summary.get("state") == "abandoned",
        f"Summary state is '{summary.get('state')}', expected 'abandoned'",
    )

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
        "governance.execution_authority restricts action",
        gov.get("execution_authority") in ("outbound_blocked_no_approval", "operator_decision_required"),
        f"governance.execution_authority={gov.get('execution_authority')}, expected restricted",
    )

    # Packet claims should reflect the legitimate packet (approval_required=True)
    claims = summary.get("packet_claims", {})
    assert_test(
        "packet_claims.approval_required = True (legitimate packet)",
        claims.get("approval_required") is True,
        f"packet_claims.approval_required={claims.get('approval_required')}",
    )

    # ═══════════════════════════════════════════════════════════
    # PHASE 10: Comprehensive Audit Trail Verification
    # ═══════════════════════════════════════════════════════════
    section("Phase 10: Comprehensive Audit Trail")
    audit_entries = rt.get_audit_trail(task_id=task2["task_id"], limit=200)
    print(f"  Total audit entries for {task2['task_id']}: {len(audit_entries)}")

    # Count rejection events
    rejection_entries = [e for e in audit_entries
                         if e.get("entry_type") == "approval_action"
                         and e.get("details", {}).get("decision") == "rejected"]
    print(f"  Rejection events: {len(rejection_entries)}")

    assert_test(
        "Audit records 3 rejection events",
        len(rejection_entries) == 3,
        f"Expected 3 rejection events, found {len(rejection_entries)}",
    )

    # Count revision loop entries
    revision_entries = [e for e in audit_entries if e.get("entry_type") == "revision_loop"]
    print(f"  Revision loop entries: {len(revision_entries)}")

    assert_test(
        "Audit records 3 revision loop entries",
        len(revision_entries) == 3,
        f"Expected 3 revision_loop entries, found {len(revision_entries)}",
    )

    # Verify 'rejected' state transitions
    rejected_transitions = [e for e in audit_entries
                             if e.get("entry_type") == "state_transition"
                             and e.get("details", {}).get("to_state") == "rejected"]
    print(f"  'rejected' state transitions: {len(rejected_transitions)}")

    assert_test(
        "Audit records 3 transitions to 'rejected' state",
        len(rejected_transitions) == 3,
        f"Expected 3 rejected transitions, found {len(rejected_transitions)}",
    )

    # Verify 'assigned' state transitions (revision loops)
    assigned_transitions = [e for e in audit_entries
                            if e.get("entry_type") == "state_transition"
                            and e.get("details", {}).get("to_state") == "assigned"]
    print(f"  'assigned' state transitions (revisions): {len(assigned_transitions)}")

    assert_test(
        "Audit records transitions back to 'assigned' for revision",
        len(assigned_transitions) >= 2,
        f"Expected >= 2 assigned transitions (revisions), found {len(assigned_transitions)}",
    )

    # Verify 'abandoned' state transition
    abandoned_transitions = [e for e in audit_entries
                              if e.get("entry_type") == "state_transition"
                              and e.get("details", {}).get("to_state") == "abandoned"]
    assert_test(
        "Audit records final transition to 'abandoned'",
        len(abandoned_transitions) > 0,
        "No 'abandoned' transition found in audit log",
    )

    # Verify no 'completed' state transition exists
    completed_transitions = [e for e in audit_entries
                              if e.get("entry_type") == "state_transition"
                              and e.get("details", {}).get("to_state") == "completed"]
    assert_test(
        "No 'completed' state transition exists (task never completed)",
        len(completed_transitions) == 0,
        f"Found unexpected 'completed' transitions: {len(completed_transitions)}",
    )

    # No task_abandoned entry type in audit
    abandon_entries = [e for e in audit_entries if e.get("entry_type") == "task_abandoned"]
    assert_test(
        "Audit records task_abandoned entry",
        len(abandon_entries) > 0,
        f"No task_abandoned entry found",
    )

    # ═══════════════════════════════════════════════════════════
    # PHASE 11: State machine integrity — 'abandoned' is terminal
    # ═══════════════════════════════════════════════════════════
    section("Phase 11: State Machine Integrity — 'abandoned' Is Terminal")
    try:
        rt.task_store.advance_state(task2["task_id"], "assigned", "Attempt to revive abandoned task")
        assert_test("State machine blocks transition from 'abandoned'", False,
                     "State machine allowed illegal transition from 'abandoned'!")
    except ValueError as e:
        print(f"  State machine correctly REJECTED: {e}")
        assert_test("State machine blocks transition from 'abandoned'", True,
                     f"ValueError: {e}")

    # Verify task record on disk
    task_on_disk = rt.get_task(task2["task_id"])
    assert_test(
        "Task record on disk shows state=abandoned",
        task_on_disk["state"] == "abandoned",
        f"Task on disk state='{task_on_disk['state']}', expected 'abandoned'",
    )
    assert_test(
        "Task record on disk shows revision_count=3",
        task_on_disk["revision_count"] == 3,
        f"Task on disk revision_count={task_on_disk['revision_count']}, expected 3",
    )

    # ── Verify operator_approval record ──
    approval_record = task_on_disk.get("operator_approval")
    assert_test(
        "Operator approval record exists on task",
        approval_record is not None,
        "No operator_approval record on task",
    )
    if approval_record:
        assert_test(
            "Last operator_approval shows decision=rejected",
            approval_record.get("decision") == "rejected",
            f"Expected decision='rejected', got '{approval_record.get('decision')}'",
        )
        assert_test(
            "Last operator_approval records operator identity",
            approval_record.get("operator") == "test_operator",
            f"Expected operator='test_operator', got '{approval_record.get('operator')}'",
        )
        assert_test(
            "Last operator_approval records rejection reason",
            "not converging" in (approval_record.get("reason") or "").lower(),
            f"Reason doesn't match: '{approval_record.get('reason')}'",
        )

    # ═══════════════════════════════════════════════════════════
    # PHASE 12: CryER upstream task should still be 'completed'
    # ═══════════════════════════════════════════════════════════
    section("Phase 12: Upstream CryER Task Unaffected")
    task1_check = rt.get_task(task1["task_id"])
    assert_test(
        "Upstream CryER task still in 'completed' state",
        task1_check["state"] == "completed",
        f"CryER task state='{task1_check['state']}', expected 'completed'",
    )

    # ═══════════════════════════════════════════════════════════
    # FULL AUDIT TRAIL PRINT
    # ═══════════════════════════════════════════════════════════
    section("Full Audit Trail (PypER Task)")
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
            note = f"{details.get('decision', '?')} by {details.get('operator', '?')}: {details.get('reason', '')[:50]}"
        elif etype == "revision_loop":
            note = f"rev={details.get('revision_count')} reason={details.get('reason', '')[:40]}"
        elif etype == "routing_decision":
            note = f"-> {details.get('routing_target', '?')} ({details.get('reason', '')[:40]})"
        else:
            note = str(details)[:60]
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
        rev = t.get("revision_count", 0)
        downstream = t.get("upstream_task_id") or ""
        print(f"  {tid}  state={state:<20} subagent={sub:<8} domain={domain:<16} revisions={rev}  upstream={downstream}")

    # ═══════════════════════════════════════════════════════════
    # FINAL RESULTS
    # ═══════════════════════════════════════════════════════════
    banner("Rejection-Loop Test Results")

    if FAILED:
        print("\n  SOME TESTS FAILED — rejection loop may not be fully functional!\n")
        print("  Review the FAIL entries above.\n")
        return 1
    else:
        print("""
  ALL TESTS PASSED — rejection loop is correctly functional:

    1. PypER task enters 'rejected' state on operator rejection
    2. No outbound action occurs at any stage (always blocked)
    3. Audit trail records each operator rejection with reason and identity
    4. Task routes back to 'assigned' for revision (under 3-revision limit)
    5. Revision count increments correctly (1, 2, 3)
    6. 2nd rejection also routes back to 'assigned' (rev 2)
    7. 3rd rejection at limit triggers 'abandoned' state (clean stop)
    8. Operator summary correctly reflects governance throughout
    9. Outbound action remains blocked at every stage
   10. State machine blocks transitions from 'abandoned' (terminal state)
   11. CryER upstream task completes normally, unaffected by PypER rejection
   12. Task records persist correctly on filesystem

  Conclusion: The rejection loop works correctly. Operator rejection halts
  outbound, records audit, routes for revision, and abandons when the limit
  is reached. Governance is enforced at every layer.""")

    # Clean up
    print(f"\n  Workspace (preserved for inspection): {workspace}")
    print(f"  Audit log:  {workspace}/runtime/audit.jsonl")
    print(f"  Task files: {workspace}/orchestration/tasks/")
    print()

    return 0


if __name__ == "__main__":
    exit_code = run_rejection_loop_test()
    sys.exit(exit_code)