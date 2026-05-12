#!/usr/bin/env python3
"""
OverCR v0.1.0 Direct-Subagent-Routing Sovereignty Test
=======================================================

Simulates packets that attempt direct subagent addressing — where source and
target are both subagent identifiers instead of the OverCR runtime itself.

In OverCR, subagents NEVER address each other directly. All packets must
target "overcr" — the runtime is the sole routing authority. Direct addressing
is a sovereignty violation: it implies subagents can contract each other
without operator oversight, bypassing the approval gate and audit trail.

Test packets:
  1. CryER → PypER (source=cryer, target=pyper)
     A recon packet that tries to hand off directly to PypER, skipping
     the OverCR routing layer, approval gate, and operator review.

  2. KnowER → CodER (source=knower, target=coder)
     A research packet that tries to commission CodER directly.

  3. CryER → CryER (source=cryer, target=cryer)
     A self-addressing packet — nonsensical, but must also be rejected.

Expected results:
  1. Validator REJECTS at Level 1 (target must be 'overcr')
  2. Validator REJECTS at Level 5 (direct subagent addressing is forbidden)
  3. Runtime routes task to validation_failed — no further progress
  4. No routing, no downstream task creation, no approval
  5. Audit records sovereignty violation with both Level 1 and Level 5 errors
  6. Outbound remains blocked at every stage
  7. State machine blocks all forward transitions from validation_failed
  8. Operator summary shows validation_failed with governance.blocked
  9. Positive control: same packet with target=overcr passes validation
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
from runtime.task_store import TaskStore, VALID_TRANSITIONS

# ── Helpers ──────────────────────────────────────────────────

FAILED = False

def banner(text: str, width: int = 72):
    print(f"\n{'=' * width}")
    print(f"  {text}")
    print(f"{'=' * width}")

def section(text: str):
    print(f"\n--- {text} ---")

def assert_test(condition: bool, label: str, detail: str = ""):
    global FAILED
    status = "[PASS]" if condition else "[FAIL]"
    if not condition:
        FAILED = True
    print(f"  {status} {label}")
    if detail:
        print(f"         {detail}")

def make_sovereignty_violation_packet(
    task_id: str,
    source: str = "cryer",
    target: str = "pyper",
    packet_type: str = "cryer_recon",
) -> dict:
    """
    Construct a packet that directly addresses another subagent
    instead of targeting OverCR as the routing authority.

    The key violation: target != "overcr"
    """
    recon_data = {
        "targets": [
            {
                "entity": "Northeast Manufacturing Corp",
                "type": "business",
                "signals": {
                    "reputation": {"yield_score": 72, "confidence": 85},
                    "intent_signals": ["hiring expansion", "new facility"],
                },
                "raw_sources": ["public_records", "industry_directory"],
            }
        ],
    }
    audit_trail = {
        "collection_timestamps": [datetime.now(timezone.utc).isoformat()],
        "methods_used": ["osint", "directory_scan"],
    }

    summary = (
        f"SOVEREIGNTY VIOLATION: {source} addressing {target} directly — "
        f"bypassing OverCR routing authority"
    )

    return {
        "packet_type": packet_type,
        "version": "1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "target": target,  # ← THE VIOLATION: should be "overcr"
        "task_id": task_id,
        "summary": summary,
        "recon_data": recon_data,
        "audit_trail": audit_trail,
        # PypER-targeting packets also try to skip approval
        "approval_required": True,
        "next_steps_recommendation": (
            f"Route directly to {target} — skip OverCR oversight for speed"
        ),
    }


def make_valid_pyper_packet(task_id: str, upstream_task_id: str = "task-0001") -> dict:
    """
    Construct a valid PypER approval packet (target=overcr, approval_required=true).
    Used as positive control to confirm valid packets still pass.
    """
    return {
        "packet_type": "pyper_approval",
        "version": "1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "pyper",
        "target": "overcr",
        "task_id": task_id,
        "upstream_task_id": upstream_task_id,
        "summary": "Valid PypER outreach draft for operator approval",
        "draft_data": {
            "prospects": [
                {
                    "entity": "Acme Industrial",
                    "approach_type": "cold_email",
                    "personalization_signals": ["hiring expansion"],
                    "drafts": [
                        {
                            "channel": "email",
                            "subject": "Collaboration opportunity",
                            "body": "Dear Acme Industrial team, ...",
                            "evidence_citations": ["public hiring data"],
                        }
                    ],
                }
            ],
        },
        "audit_trail": {
            "upstream_sources": [upstream_task_id],
        },
        "approval_required": True,
        "outbound_contact": False,
    }


# ── Main Test ────────────────────────────────────────────────

def main():
    global FAILED

    workspace = Path("/tmp/overcr-sovereignty-test")
    if workspace.exists():
        shutil.rmtree(workspace)
    workspace.mkdir(parents=True)

    rt = OverCRRuntime(root=str(workspace))
    assertion_count = 0

    banner("OverCR v0.1.0 Direct-Subagent-Routing Sovereignty Test")

    # ══════════════════════════════════════════════════════════
    # PHASE 1: Create upstream CryER task
    # ══════════════════════════════════════════════════════════
    section("Phase 1: Create Upstream CryER Task")

    cryer_task = rt.create_task(
        domain="recon",
        description="Reconnaissance for manufacturing leads",
        instruction="Scan public records for manufacturing companies",
        input_context={
            "entity": "Northeast Manufacturing Corp",
            "type": "business",
            "focus_areas": ["hiring", "expansion"],
            "upstream_task_id": None,
        },
    )
    cryer_id = cryer_task["task_id"]
    assert_test(cryer_id == "task-0001", "CryER task created", f"id={cryer_id}")
    assert_test(cryer_task["state"] == "created", "Initial state is 'created'")

    rt.simulate_acknowledge(cryer_id)
    rt.receive_response(
        cryer_id,
        {
            "packet_type": "cryer_recon",
            "version": "1.0",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": "cryer",
            "target": "overcr",  # ← correct
            "task_id": cryer_id,
            "summary": "Recon complete — 3 targets identified",
            "recon_data": {
                "targets": [
                    {
                        "entity": "Northeast Manufacturing Corp",
                        "type": "business",
                        "signals": {
                            "reputation": {"yield_score": 72, "confidence": 85},
                        },
                        "raw_sources": ["public_records"],
                    }
                ],
            },
            "audit_trail": {
                "collection_timestamps": [datetime.now(timezone.utc).isoformat()],
                "methods_used": ["osint"],
            },
            "approval_required": False,
        },
    )
    rt.validate_response(cryer_id)
    rt.route(cryer_id)
    rt.complete_task(cryer_id, "CryER recon complete")

    cryer_task = rt.get_task(cryer_id)
    assert_test(
        cryer_task["state"] == "completed",
        "CryER upstream task completed",
        f"state={cryer_task['state']}",
    )

    # ══════════════════════════════════════════════════════════
    # PHASE 2: Craft sovereignty-violating packet (CryER → PypER)
    # ══════════════════════════════════════════════════════════
    section("Phase 2: CryER → PypER Direct-Addressing Packet")

    pyper_task = rt.create_task(
        domain="outreach",
        description="Downstream outreach task from task-0001",
        instruction="Draft outreach for manufacturing leads",
        input_context={
            "entity": "Northeast Manufacturing Corp",
            "type": "business",
            "source_task_id": cryer_id,
        },
        upstream_task_id=cryer_id,
    )
    pyper_id = pyper_task["task_id"]
    assert_test(pyper_id == "task-0002", "PypER task created", f"id={pyper_id}")

    rt.simulate_acknowledge(pyper_id)
    rt.receive_response(
        pyper_id,
        make_sovereignty_violation_packet(
            task_id=pyper_id,
            source="cryer",
            target="pyper",  # ← DIRECT ADDRESSING — should be "overcr"
        ),
    )

    pyper_task = rt.get_task(pyper_id)
    assert_test(
        pyper_task["state"] == "response_received",
        "PypER task in response_received state before validation",
        f"state={pyper_task['state']}",
    )

    # ══════════════════════════════════════════════════════════
    # PHASE 3: Validate — sovereignty violation must be caught
    # ══════════════════════════════════════════════════════════
    section("Phase 3: Validate — Sovereignty Violation Catch")

    validation = rt.validate_response(pyper_id)
    assert_test(
        validation["valid"] is False,
        "Validator REJECTS direct-addressing packet",
        f"valid={validation['valid']}",
    )

    errors = validation["errors"]
    print(f"  Validation errors ({len(errors)}):")
    for e in errors:
        print(f"    - {e}")

    # Level 1 must catch target != overcr
    level1_target_errors = [e for e in errors if "Level 1" in e and "target" in e and "overcr" in e]
    assert_test(
        len(level1_target_errors) >= 1,
        "Level 1 catches target violation",
        f"errors: {level1_target_errors}",
    )

    # Level 5 must catch direct subagent addressing
    level5_errors = [e for e in errors if "Level 5" in e and "direct subagent addressing" in e]
    assert_test(
        len(level5_errors) >= 1,
        "Level 5 catches sovereignty violation (direct subagent addressing forbidden)",
        f"errors: {level5_errors}",
    )

    # Task must be in validation_failed state
    pyper_task = rt.get_task(pyper_id)
    assert_test(
        pyper_task["state"] == "validation_failed",
        "Task enters validation_failed state",
        f"state={pyper_task['state']}",
    )

    # ══════════════════════════════════════════════════════════
    # PHASE 4: Routing must be refused
    # ══════════════════════════════════════════════════════════
    section("Phase 4: Routing Refused (validation_failed → cannot route)")

    routing_refused = False
    try:
        rt.route(pyper_id)
        assert_test(False, "Routing MUST be refused from validation_failed state")
    except ValueError as e:
        routing_refused = True
        assert_test(
            True,
            "Routing refused — cannot route from validation_failed",
            f"error: {e}",
        )

    assert_test(routing_refused, "No routing occurs for sovereignty-violating packet")

    # ══════════════════════════════════════════════════════════
    # PHASE 5: Approval gate must block
    # ══════════════════════════════════════════════════════════
    section("Phase 5: Approval Gate Blocks (outbound remains blocked)")

    pyper_task = rt.get_task(pyper_id)
    blocked, block_reason = rt.gate.should_block_outbound(pyper_task)
    assert_test(
        blocked is True,
        "Outbound action is BLOCKED",
        f"blocked={blocked}, reason={block_reason}",
    )

    # ══════════════════════════════════════════════════════════
    # PHASE 6: Audit trail records sovereignty violation
    # ══════════════════════════════════════════════════════════
    section("Phase 6: Audit Trail Records Sovereignty Violation")

    audit = rt.get_audit_trail(task_id=pyper_id)
    print(f"  Audit entries for {pyper_id}: {len(audit)}")

    # Find validation_result entry
    validation_entries = [
        e for e in audit if e.get("entry_type") == "validation_result"
    ]
    assert_test(
        len(validation_entries) >= 1,
        "Audit contains validation_result entry",
        f"found {len(validation_entries)}",
    )

    if validation_entries:
        val_entry = validation_entries[0]
        val_details = val_entry.get("details", {})
        assert_test(
            val_details.get("valid") is False,
            "Validation result recorded as invalid",
            f"valid={val_details.get('valid')}",
        )
        val_errors = val_details.get("errors", [])
        # Check that Level 5 sovereignty violation is in the audit
        sovereignty_in_audit = any(
            "direct subagent addressing" in e for e in val_errors
        )
        assert_test(
            sovereignty_in_audit,
            "Audit records Level 5 sovereignty violation",
            f"Level 5 errors in audit: {[e for e in val_errors if 'Level 5' in e]}",
        )

    # Check state_transition to validation_failed
    state_transitions = [
        e for e in audit if e.get("entry_type") == "state_transition"
    ]
    val_fail_transitions = [
        t for t in state_transitions
        if t.get("details", {}).get("to_state") == "validation_failed"
    ]
    assert_test(
        len(val_fail_transitions) >= 1,
        "Audit records transition to validation_failed",
        f"transitions: {len(val_fail_transitions)}",
    )

    # ══════════════════════════════════════════════════════════
    # PHASE 7: State machine blocks forward progress
    # ══════════════════════════════════════════════════════════
    section("Phase 7: State Machine Blocks Forward Progress")

    assert_test(
        "approval_pending" not in VALID_TRANSITIONS.get("validation_failed", set()),
        "validation_failed cannot transition to approval_pending",
    )
    assert_test(
        "routed" not in VALID_TRANSITIONS.get("validation_failed", set()),
        "validation_failed cannot transition to routed",
    )
    assert_test(
        "completed" not in VALID_TRANSITIONS.get("validation_failed", set()),
        "validation_failed cannot transition to completed",
    )

    # Only valid transitions from validation_failed: assigned, abandoned
    allowed = VALID_TRANSITIONS.get("validation_failed", set())
    assert_test(
        allowed == {"assigned", "abandoned"},
        "validation_failed only allows assigned or abandoned",
        f"allowed={allowed}",
    )

    # ══════════════════════════════════════════════════════════
    # PHASE 8: Operator summary shows validation_failed governance
    # ══════════════════════════════════════════════════════════
    section("Phase 8: Operator Summary — Governance Blocks")

    summary = rt.operator_summary(pyper_id)
    assert_test(
        summary["state"] == "validation_failed",
        "Summary shows validation_failed state",
        f"state={summary['state']}",
    )

    governance = summary.get("governance", {})
    assert_test(
        governance.get("validation_passed") is False,
        "governance.validation_passed is False",
        f"validation_passed={governance.get('validation_passed')}",
    )
    assert_test(
        governance.get("outbound_blocked") is True,
        "governance.outbound_blocked is True",
        f"outbound_blocked={governance.get('outbound_blocked')}",
    )

    # ══════════════════════════════════════════════════════════
    # PHASE 9: Second violation — KnowER → CodER direct addressing
    # ══════════════════════════════════════════════════════════
    section("Phase 9: KnowER → CodER Direct-Addressing Packet")

    knower_task = rt.create_task(
        domain="research",
        description="Research task for manufacturing sector analysis",
        instruction="Analyze manufacturing sector trends",
        input_context={
            "topic": "Manufacturing automation trends",
            "upstream_task_id": None,
        },
    )
    knower_id = knower_task["task_id"]
    rt.simulate_acknowledge(knower_id)

    knower_packet = {
        "packet_type": "knower_research",
        "version": "1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "knower",
        "target": "coder",  # ← DIRECT ADDRESSING — should be "overcr"
        "task_id": knower_id,
        "summary": "Direct handoff: KnowER research → CodER implementation",
        "research_data": {
            "topic": "Manufacturing automation trends",
            "findings": [
                {
                    "claim": "Automation adoption accelerating",
                    "confidence": 3,
                    "sources": ["industry_reports"],
                    "gaps": [],
                }
            ],
        },
        "audit_trail": {
            "sources_consulted": ["industry_reports"],
        },
    }

    rt.receive_response(knower_id, knower_packet)
    knower_validation = rt.validate_response(knower_id)

    assert_test(
        knower_validation["valid"] is False,
        "Validator REJECTS KnowER → CodER direct addressing",
        f"valid={knower_validation['valid']}",
    )

    # Level 1 target error
    knower_l1 = [e for e in knower_validation["errors"] if "Level 1" in e and "target" in e]
    assert_test(
        len(knower_l1) >= 1,
        "Level 1 catches KnowER → CodER target violation",
        f"errors: {knower_l1}",
    )

    # Level 5 sovereignty error
    knower_l5 = [e for e in knower_validation["errors"] if "Level 5" in e and "direct subagent addressing" in e]
    assert_test(
        len(knower_l5) >= 1,
        "Level 5 catches KnowER → CodER sovereignty violation",
        f"errors: {knower_l5}",
    )

    knower_task = rt.get_task(knower_id)
    assert_test(
        knower_task["state"] == "validation_failed",
        "KnowER task enters validation_failed",
        f"state={knower_task['state']}",
    )

    # For KnowER (research domain), the approval gate doesn't block by default
    # because it's not an outreach/PypER domain. However, the task is stuck
    # in validation_failed state — the state machine prevents any outbound
    # action regardless of the approval gate.
    knower_task_check = rt.get_task(knower_id)
    assert_test(
        knower_task_check["state"] == "validation_failed",
        "KnowER task is in validation_failed — no outbound possible",
        f"state={knower_task_check['state']}",
    )

    # The approval gate may not block (research domain has no gate),
    # but the real enforcement is the state machine: validation_failed
    # cannot transition to any outbound state.
    # Verify the state machine prevents routing from validation_failed
    assert_test(
        "routed" not in VALID_TRANSITIONS.get("validation_failed", set()),
        "validation_failed cannot reach 'routed' state (state machine blocks it)",
    )

    # ══════════════════════════════════════════════════════════
    # PHASE 10: Third violation — CryER → CryER self-addressing
    # ══════════════════════════════════════════════════════════
    section("Phase 10: CryER → CryER Self-Addressing Packet")

    self_task = rt.create_task(
        domain="recon",
        description="Self-referencing recon task",
        instruction="Rescan targets",
        input_context={
            "entity": "Northeast Manufacturing Corp",
            "type": "business",
            "focus_areas": ["re-scan"],
            "upstream_task_id": None,
        },
    )
    self_id = self_task["task_id"]
    rt.simulate_acknowledge(self_id)

    self_packet = make_sovereignty_violation_packet(
        task_id=self_id,
        source="cryer",
        target="cryer",  # ← SELF-ADDRESSING — also forbidden
    )

    rt.receive_response(self_id, self_packet)
    self_validation = rt.validate_response(self_id)

    assert_test(
        self_validation["valid"] is False,
        "Validator REJECTS self-addressing packet (CryER → CryER)",
        f"valid={self_validation['valid']}",
    )

    self_l5 = [e for e in self_validation["errors"] if "Level 5" in e and "direct subagent addressing" in e]
    assert_test(
        len(self_l5) >= 1,
        "Level 5 catches CryER → CryER sovereignty violation",
        f"errors: {self_l5}",
    )

    self_task_obj = rt.get_task(self_id)
    assert_test(
        self_task_obj["state"] == "validation_failed",
        "Self-addressing task enters validation_failed",
        f"state={self_task_obj['state']}",
    )

    # ══════════════════════════════════════════════════════════
    # PHASE 11: Recovery paths — validation_failed → assigned (revision)
    # ══════════════════════════════════════════════════════════
    section("Phase 11: Recovery — validation_failed → assigned (Revision)")

    # The CryER → PypER task can be sent back for revision
    revised_task = rt.task_store.advance_state(
        pyper_id, "assigned", "Sent back for revision — fix target field"
    )
    assert_test(
        revised_task["state"] == "assigned",
        "Task can be revised: validation_failed → assigned",
        f"state={revised_task['state']}",
    )

    # ══════════════════════════════════════════════════════════
    # PHASE 12: Recovery — validation_failed → abandoned
    # ══════════════════════════════════════════════════════════
    section("Phase 12: Recovery — validation_failed → abandoned")

    abandoned_task = rt.task_store.advance_state(
        knower_id, "abandoned", "Sovereignty violation — direct subagent addressing"
    )
    assert_test(
        abandoned_task["state"] == "abandoned",
        "Task can be abandoned: validation_failed → abandoned",
        f"state={abandoned_task['state']}",
    )

    # Abandoned is terminal — no further transitions
    assert_test(
        len(VALID_TRANSITIONS.get("abandoned", set())) == 0,
        "Abandoned is a terminal state (no outgoing transitions)",
    )

    abandoned_again = False
    try:
        rt.task_store.advance_state(knower_id, "assigned", "Try to revive abandoned task")
        assert_test(False, "Must NOT be able to transition from abandoned")
    except ValueError:
        abandoned_again = True
        assert_test(True, "State machine blocks transition from abandoned")

    # ══════════════════════════════════════════════════════════
    # PHASE 13: Positive control — correct target passes validation
    # ══════════════════════════════════════════════════════════
    section("Phase 13: Positive Control — target='overcr' Passes Validation")

    valid_cryer_task = rt.create_task(
        domain="recon",
        description="Valid CryER recon with proper target",
        instruction="Reconnaissance scan",
        input_context={
            "entity": "Valid Target Corp",
            "type": "business",
            "focus_areas": ["reviews", "hiring"],
            "upstream_task_id": None,
        },
    )
    valid_cryer_id = valid_cryer_task["task_id"]
    rt.simulate_acknowledge(valid_cryer_id)

    valid_packet = make_sovereignty_violation_packet(
        task_id=valid_cryer_id,
        source="cryer",
        target="overcr",  # ← CORRECT — targets the runtime
    )
    rt.receive_response(valid_cryer_id, valid_packet)
    valid_validation = rt.validate_response(valid_cryer_id)

    assert_test(
        valid_validation["valid"] is True,
        "Packet with target=overcr passes validation",
        f"valid={valid_validation['valid']}",
    )

    valid_task = rt.get_task(valid_cryer_id)
    assert_test(
        valid_task["state"] == "validation_passed",
        "Valid packet reaches validation_passed",
        f"state={valid_task['state']}",
    )

    # Route and complete normally
    routing = rt.route(valid_cryer_id)
    assert_test(
        routing["routing_target"] in ("pyper", "knower"),
        "Valid packet routes normally through OverCR",
        f"routing_target={routing['routing_target']}",
    )
    assert_test(
        routing["creates_downstream_task"] is True,
        "Valid packet creates downstream task through proper routing",
        f"creates_downstream={routing['creates_downstream_task']}",
    )

    # ══════════════════════════════════════════════════════════
    # PHASE 14: Standalone Validator Test — Direct addressing
    # ══════════════════════════════════════════════════════════
    section("Phase 14: Standalone Validator — Direct Subagent Addressing")

    validator = rt.validator

    # Test all direct-addressing variants
    violation_variants = [
        ("cryer", "pyper"),
        ("cryer", "coder"),
        ("knower", "pyper"),
        ("knower", "coder"),
        ("pyper", "cryer"),  # PypER trying to commission CryER
        ("coder", "knower"),
        ("cryer", "cryer"),  # Self-addressing
        ("pyper", "pyper"),  # Self-addressing
    ]

    for src, tgt in violation_variants:
        packet = {
            "packet_type": "cryer_recon" if src == "cryer" else "knower_research",
            "version": "1.0",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": src,
            "target": tgt,
            "task_id": "task-0001",
            "summary": f"Direct addressing: {src} → {tgt}",
        }
        if src == "cryer":
            packet["recon_data"] = {"targets": [
                {"entity": "Test", "type": "business", "signals": {"reputation": {"yield_score": 50, "confidence": 80}}, "raw_sources": ["test"]}
            ]}
            packet["audit_trail"] = {"collection_timestamps": [datetime.now(timezone.utc).isoformat()], "methods_used": ["test"]}
        elif src == "knower":
            packet["research_data"] = {"topic": "Test", "findings": [{"claim": "test", "confidence": 3, "sources": ["test"], "gaps": []}]}
            packet["audit_trail"] = {"sources_consulted": ["test"]}

        valid, errors, warnings = validator.validate_packet(packet)
        assert_test(
            valid is False,
            f"Validator rejects {src} → {tgt}",
            f"valid={valid}, errors={len(errors)}",
        )

        l1_target = any("Level 1" in e and "target" in e and "overcr" in e for e in errors)
        l5_sovereignty = any("Level 5" in e and "direct subagent addressing" in e for e in errors)
        assert_test(
            l1_target,
            f"Level 1 catches {src} → {tgt} target violation",
        )
        assert_test(
            l5_sovereignty,
            f"Level 5 catches {src} → {tgt} sovereignty violation",
        )

    # Positive control: overcr target passes L1 and L5
    ok_packet = {
        "packet_type": "cryer_recon",
        "version": "1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "cryer",
        "target": "overcr",
        "task_id": "task-0001",
        "summary": "Valid: CryER → OverCR",
        "recon_data": {"targets": [
            {"entity": "Test", "type": "business", "signals": {"reputation": {"yield_score": 50, "confidence": 80}}, "raw_sources": ["test"]}
        ]},
        "audit_trail": {"collection_timestamps": [datetime.now(timezone.utc).isoformat()], "methods_used": ["test"]},
    }
    ok_valid, ok_errors, ok_warnings = validator.validate_packet(ok_packet)
    assert_test(
        ok_valid is True,
        "target=overcr passes full 6-level validation",
        f"valid={ok_valid}, errors={ok_errors}",
    )
    ok_l1 = [e for e in ok_errors if "target" in e]
    ok_l5 = [e for e in ok_errors if "direct subagent addressing" in e]
    assert_test(
        len(ok_l1) == 0,
        "No Level 1 target errors when target=overcr",
    )
    assert_test(
        len(ok_l5) == 0,
        "No Level 5 sovereignty errors when target=overcr",
    )

    # ══════════════════════════════════════════════════════════
    # PHASE 15: Audit trail — sovereignty violations recorded
    # ══════════════════════════════════════════════════════════
    section("Phase 15: Audit Trail — Full Sovereignty Violation Log")

    all_audit = rt.get_audit_trail()
    # Count validation failures across all tasks
    val_failures = [
        e for e in all_audit
        if e.get("entry_type") == "validation_result"
        and e.get("details", {}).get("valid") is False
    ]
    print(f"  Total validation failures across all tasks: {len(val_failures)}")

    # Count sovereignty-specific errors
    sovereignty_errors = 0
    for v in val_failures:
        for err in v.get("details", {}).get("errors", []):
            if "direct subagent addressing" in err:
                sovereignty_errors += 1
    assert_test(
        sovereignty_errors >= 3,
        f"At least 3 sovereignty violations recorded in audit (found {sovereignty_errors})",
        f"sovereignty_errors={sovereignty_errors}",
    )

    # Task records on disk
    section("Task Records on Disk")
    tasks = rt.list_tasks()
    for t in tasks:
        state = t.get("state", "?")
        sub = t.get("assigned_subagent", "?")
        domain = t.get("domain", "?")
        val = (t.get("validation_result") or {}).get("valid", "?")
        print(f"  {t['task_id']}  state={state:<22}  sub={sub:<6}  domain={domain:<12}  valid={val}")

    # ══════════════════════════════════════════════════════════
    # Summary
    # ══════════════════════════════════════════════════════════
    banner("Direct-Subagent-Routing Sovereignty Test Results")

    if not FAILED:
        print("""
  ALL TESTS PASSED — direct subagent addressing is correctly blocked:

    1.  Validator REJECTS packets with target != 'overcr' at Level 1
    2.  Validator REJECTS direct subagent addressing at Level 5 (sovereignty)
    3.  OverCR is the ONLY valid routing target — subagents cannot bypass it
    4.  Runtime routes sovereignty-violating tasks to validation_failed
    5.  No routing, no downstream task creation, no approval occurs
    6.  Outbound action remains BLOCKED for violated tasks
    7.  Audit trail records every sovereignty violation with Level 5 detail
    8.  State machine blocks all forward progress from validation_failed
    9.  Recovery paths work: validation_failed → assigned (revision) or abandoned
   10.  Positive control: target=overcr passes validation and routes normally
   11.  Self-addressing packets (CryER → CryER) are also rejected
   12.  All 8 direct-addressing variants are caught at both Level 1 and Level 5

  Conclusion: Subagent sovereignty is enforced. No packet can address another
  subagent directly — all communication flows through the OverCR runtime.
  The validator catches the violation at two independent levels, the state
  machine prevents routing, and the audit trail preserves evidence.
""")
    else:
        print("\n  SOME TESTS FAILED — review output above for details.\n")

    print(f"  Workspace (preserved for inspection): {workspace}")
    print(f"  Audit log:  {workspace}/runtime/audit.jsonl")
    print(f"  Task files: {workspace}/orchestration/tasks/")

    sys.exit(1 if FAILED else 0)


if __name__ == "__main__":
    main()