#!/usr/bin/env python3
"""
OverCR v0.1.0 Cold-Start Reconstruction Test

Tests the core CAG principle: runtime state can be rebuilt entirely from
filesystem state. No chat history, no in-memory caches, no external state.

Procedure:
  1. Phase 1 — Populate: Drive the runtime through a multi-task lifecycle
     creating tasks in various states (created, in_progress, approval_pending,
     approved, completed, abandoned, etc.)
  2. Phase 1.5 — Capture: Snapshot all filesystem state (task_counter, task
     records, audit log) as a reference baseline.
  3. Phase 2 — Terminate: Simulate a cold start by destroying all in-memory
     object state (new OverCRRuntime instance from the same root).
  4. Phase 3 — Reconstruct: Using ONLY the new runtime instance (which reads
     from disk), reconstruct:
     - Task counter
     - Latest task states
     - Audit trail
     - Pending approvals
     - Blocked outbound actions
  5. Phase 4 — Verify: Assert reconstructed state matches the captured baseline.

Expected result:
  - Runtime state can be rebuilt from disk
  - No chat history is required
  - All governance-enforced states (approvals, outbound blocks) survive
"""

import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# Add the parent directory to the path so we can import runtime modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from runtime.overcr_runtime import OverCRRuntime
from runtime.task_store import TaskStore, DOMAIN_SUBAGENT_MAP
from runtime.approval_gate import ApprovalGate


# ── Helpers ──────────────────────────────────────────────────────────

def make_cryer_recon_packet(task_id: str, yield_score: int = 85) -> dict:
    """Generate a valid CryER recon packet that passes all 6 validation levels."""
    return {
        "packet_type": "cryer_recon",
        "version": "1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "cryer",
        "target": "overcr",
        "task_id": task_id,
        "summary": f"Recon complete. Yield score: {yield_score}.",
        "recon_data": {
            "region": "Region X",
            "targets": [
                {
                    "entity": "Example Business Name",
                    "type": "business",
                    "signals": {
                        "reputation": {
                            "yield_score": yield_score,
                            "confidence": 75,
                            "risk_flags": [],
                        }
                    },
                    "raw_sources": ["public_directory_listing"],
                }
            ],
        },
        "audit_trail": {
            "collection_timestamps": [datetime.now(timezone.utc).isoformat()],
            "methods_used": ["public_directory_scan"],
        },
        "approval_required": False,
        "next_steps_recommendation": "Submit to OverCR for outreach routing.",
        "outbound_contact": None,
    }


def make_pyper_approval_packet(task_id: str, entity: str = "Example Business Name",
                                upstream_task_id: str = None) -> dict:
    """Generate a valid PypER approval packet (always requires approval)."""
    return {
        "packet_type": "pyper_approval",
        "version": "1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "pyper",
        "target": "overcr",
        "task_id": task_id,
        "summary": f"Outreach draft ready for {entity}",
        "draft_data": {
            "prospects": [
                {
                    "entity": entity,
                    "approach_type": "warm_intro",
                    "drafts": [
                        {
                            "body": f"Dear {entity}, we would like to introduce ourselves.",
                            "evidence_citations": ["Public business directory listing"],
                        }
                    ],
                }
            ],
        },
        "audit_trail": {
            "upstream_sources": [upstream_task_id or "task-0000"],
        },
        "approval_required": True,
        "next_steps_recommendation": "Review and approve for outbound",
        "outbound_contact": {"entity": entity, "channel": "email"},
    }


def make_knower_research_packet(task_id: str) -> dict:
    """Generate a valid KnowER research packet."""
    return {
        "packet_type": "knower_research",
        "version": "1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "knower",
        "target": "overcr",
        "task_id": task_id,
        "summary": "Research analysis complete. Industry trends support outreach.",
        "research_data": {
            "topic": "technology_sector_growth",
            "findings": [
                {
                    "claim": "Industry growing 15% YoY",
                    "confidence": 3,
                    "sources": ["industry_report_A"],
                    "gaps": [],
                }
            ],
        },
        "audit_trail": {
            "sources_consulted": ["industry_report_A", "public_data_B"],
        },
        "approval_required": False,
        "next_steps_recommendation": "Submit to OverCR for outreach routing.",
        "outbound_contact": None,
    }


def make_coder_completion_packet(task_id: str) -> dict:
    """Generate a valid CodER completion packet."""
    return {
        "packet_type": "coder_completion",
        "version": "1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "coder",
        "target": "overcr",
        "task_id": task_id,
        "summary": "Code task completed successfully.",
        "completion_data": {
            "deliverables": [
                {
                    "type": "script",
                    "path": "/opt/scripts/data_extraction.py",
                    "reversible": True,
                }
            ],
            "breaking_changes": False,
        },
        "audit_trail": {
            "files_modified": ["/opt/scripts/data_extraction.py"],
            "rollback_instructions": "Delete /opt/scripts/data_extraction.py",
        },
        "approval_required": False,
        "next_steps_recommendation": "Archive",
        "outbound_contact": None,
    }


# ── Phase 1: Populate ────────────────────────────────────────────────

def phase1_populate(runtime: OverCRRuntime) -> dict:
    """Drive the runtime through multiple task lifecycles."""
    print("=" * 72)
    print("PHASE 1: POPULATE — Creating tasks across multiple lifecycle states")
    print("=" * 72)

    task_states = {}

    # ── Task A: CryER recon → validation_passed → routed ──
    print("\n[1a] Task A: CryER recon — validated, routed to PypER")
    task_a = runtime.create_task(
        domain="recon",
        description="Recon: Region X technology sector",
        instruction="Scan public signals in Region X tech sector",
        input_context={"region": "Region X", "sector": "technology"},
    )
    task_a_id = task_a["task_id"]
    runtime.simulate_acknowledge(task_a_id)
    print(f"  {task_a_id}: -> in_progress")

    packet_a = make_cryer_recon_packet(task_a_id, yield_score=72)
    runtime.receive_response(task_a_id, packet_a)
    result_a = runtime.validate_response(task_a_id)
    print(f"  {task_a_id}: validated (valid={result_a['valid']})")

    if result_a['valid']:
        routing_a = runtime.route(task_a_id)
        task_states[task_a_id] = routing_a['final_state']
        print(f"  {task_a_id}: routed to {routing_a['routing_target']} (state={routing_a['final_state']})")
    else:
        task_states[task_a_id] = result_a['state']
        print(f"  {task_a_id}: WARNING — validation failed")

    # ── Task B: PypER outreach — approval_pending ──
    print("\n[1b] Task B: PypER outreach — stuck in approval_pending")
    task_b = runtime.create_task(
        domain="outreach",
        description="Outreach: Example Business Name introduction",
        instruction="Draft personalized outreach for Example Business Name",
        input_context={"entity": "Example Business Name", "approach": "introduction"},
    )
    task_b_id = task_b["task_id"]
    runtime.simulate_acknowledge(task_b_id)

    packet_b = make_pyper_approval_packet(task_b_id, upstream_task_id=task_a_id)
    runtime.receive_response(task_b_id, packet_b)
    result_b = runtime.validate_response(task_b_id)
    if result_b['valid']:
        routing_b = runtime.route(task_b_id)
        task_states[task_b_id] = routing_b['final_state']
        print(f"  {task_b_id}: {routing_b['final_state']} (PypER always approval_pending)")
    else:
        task_states[task_b_id] = result_b['state']
        print(f"  {task_b_id}: WARNING — validation errors: {result_b.get('errors',[])}")

    # ── Task C: KnowER research → routed ──
    print("\n[1c] Task C: KnowER research — routed")
    task_c = runtime.create_task(
        domain="research",
        description="Research: Industry growth analysis",
        instruction="Analyze technology sector growth patterns",
        input_context={"domain": "technology", "focus": "growth_patterns"},
    )
    task_c_id = task_c["task_id"]
    runtime.simulate_acknowledge(task_c_id)

    packet_c = make_knower_research_packet(task_c_id)
    runtime.receive_response(task_c_id, packet_c)
    result_c = runtime.validate_response(task_c_id)
    if result_c['valid']:
        routing_c = runtime.route(task_c_id)
        task_states[task_c_id] = routing_c['final_state']
        print(f"  {task_c_id}: routed to {routing_c['routing_target']} (state={routing_c['final_state']})")
    else:
        task_states[task_c_id] = result_c['state']
        print(f"  {task_c_id}: WARNING — errors: {result_c.get('errors',[])}")

    # ── Task D: PypER — approved then completed ──
    print("\n[1d] Task D: PypER outreach — approved and completed")
    task_d = runtime.create_task(
        domain="outreach",
        description="Outreach: Approved draft for Entity D",
        instruction="Prepare outreach draft for Entity D",
        input_context={"entity": "Entity D", "approach": "follow-up"},
    )
    task_d_id = task_d["task_id"]
    runtime.simulate_acknowledge(task_d_id)

    packet_d = make_pyper_approval_packet(task_d_id, entity="Entity D")
    runtime.receive_response(task_d_id, packet_d)
    result_d = runtime.validate_response(task_d_id)
    if result_d['valid']:
        routing_d = runtime.route(task_d_id)
        if routing_d['final_state'] == 'approval_pending':
            runtime.process_approval(task_d_id, "approved", "Looks good")
            task_d_updated = runtime.task_store.load_task(task_d_id)
            task_states[task_d_id] = task_d_updated['state']
            print(f"  {task_d_id}: {task_d_updated['state']} (after approval)")
        else:
            task_states[task_d_id] = routing_d['final_state']
    else:
        task_states[task_d_id] = result_d['state']

    # ── Task E: PypER — rejected, revision loop ──
    print("\n[1e] Task E: PypER outreach — rejected (revision loop)")
    task_e = runtime.create_task(
        domain="outreach",
        description="Outreach: Rejected draft for Entity E",
        instruction="Draft outreach for Entity E",
        input_context={"entity": "Entity E", "approach": "cold_email"},
    )
    task_e_id = task_e["task_id"]
    runtime.simulate_acknowledge(task_e_id)

    packet_e = make_pyper_approval_packet(task_e_id, entity="Entity E")
    runtime.receive_response(task_e_id, packet_e)
    result_e = runtime.validate_response(task_e_id)
    if result_e['valid']:
        routing_e = runtime.route(task_e_id)
        if routing_e['final_state'] == 'approval_pending':
            runtime.process_approval(task_e_id, "rejected", "Tone too aggressive")
            task_e_updated = runtime.task_store.load_task(task_e_id)
            task_states[task_e_id] = task_e_updated['state']
            print(f"  {task_e_id}: {task_e_updated['state']} (revision_count={task_e_updated['revision_count']})")
        else:
            task_states[task_e_id] = routing_e['final_state']
    else:
        task_states[task_e_id] = result_e['state']

    # ── Task F: stuck in 'created' ──
    print("\n[1f] Task F: CryER recon — stuck in 'created' (never acknowledged)")
    task_f = runtime.create_task(
        domain="recon",
        description="Recon: Never-acknowledged task",
        instruction="Gather reputation data for Never Acknowledged Corp",
        input_context={"entity": "Never Acknowledged Corp"},
    )
    task_f_id = task_f["task_id"]
    task_states[task_f_id] = "created"
    print(f"  {task_f_id}: created (stays here)")

    # ── Task G: CodER completion → completed ──
    print("\n[1g] Task G: CodER completion — completed")
    task_g = runtime.create_task(
        domain="code",
        description="Code: Script for data extraction",
        instruction="Write a data extraction script",
        input_context={"task_type": "script", "language": "python"},
    )
    task_g_id = task_g["task_id"]
    runtime.simulate_acknowledge(task_g_id)

    packet_g = make_coder_completion_packet(task_g_id)
    runtime.receive_response(task_g_id, packet_g)
    result_g = runtime.validate_response(task_g_id)
    if result_g['valid']:
        routing_g = runtime.route(task_g_id)
        task_g_updated = runtime.task_store.load_task(task_g_id)
        task_states[task_g_id] = task_g_updated['state']
        print(f"  {task_g_id}: {task_g_updated['state']} (routing: {routing_g['routing_target']})")
    else:
        task_states[task_g_id] = result_g['state']
        print(f"  {task_g_id}: WARNING — validation errors: {result_g.get('errors',[])}")

    print(f"\n  Phase 1 complete. {len(task_states)} tasks created.")
    print(f"  Task states: {json.dumps(task_states, indent=2)}")
    return task_states


def phase1_5_capture(task_store: TaskStore, audit_path: Path) -> dict:
    """Snapshot all filesystem state for later comparison."""
    print("\n" + "=" * 72)
    print("PHASE 1.5: CAPTURE — Snapshotting filesystem state for baseline")
    print("=" * 72)

    counter_data = json.loads((task_store.counter_path).read_text())
    task_counter = int(counter_data["last_task_id"])
    print(f"  Task counter: {task_counter}")

    all_tasks = task_store.list_tasks()
    task_states = {}
    task_records = {}
    pending_approvals = []
    blocked_outbound = []
    gate = ApprovalGate()

    for task in all_tasks:
        tid = task["task_id"]
        task_states[tid] = task["state"]
        task_records[tid] = task

        if task["state"] == "approval_pending":
            pending_approvals.append(tid)
            print(f"  Pending approval: {tid} ({task['assigned_subagent']}/{task['domain']})")

        blocked, reason = gate.should_block_outbound(task)
        if blocked:
            blocked_outbound.append(tid)
            print(f"  Outbound blocked: {tid} ({reason})")

    print(f"  Total tasks: {len(all_tasks)}")
    print(f"  Pending approvals: {pending_approvals}")
    print(f"  Blocked outbound: {blocked_outbound}")

    audit_entries = []
    with open(audit_path) as f:
        for line in f:
            line = line.strip()
            if line:
                audit_entries.append(json.loads(line))
    print(f"  Audit entries: {len(audit_entries)}")

    return {
        "task_counter": task_counter,
        "task_states": task_states,
        "task_records": task_records,
        "audit_count": len(audit_entries),
        "pending_approvals": pending_approvals,
        "blocked_outbound": blocked_outbound,
    }


def phase3_reconstruct(root: str) -> dict:
    """Simulate a cold start: fresh instance from filesystem only."""
    print("\n" + "=" * 72)
    print("PHASE 3: RECONSTRUCT — Fresh runtime instance from filesystem only")
    print("  (No in-memory state. No chat history. Disk = canonical truth.)")
    print("=" * 72)

    runtime = OverCRRuntime(root)
    task_store = TaskStore(root)

    counter_data = json.loads((task_store.counter_path).read_text())
    task_counter = int(counter_data["last_task_id"])
    print(f"  [RECONSTRUCTED] Task counter: {task_counter}")

    all_tasks = task_store.list_tasks()
    task_states = {}
    task_records = {}
    pending_approvals = []
    blocked_outbound = []

    gate = ApprovalGate()

    for task in all_tasks:
        tid = task["task_id"]
        task_states[tid] = task["state"]
        task_records[tid] = task

        if task["state"] == "approval_pending":
            pending_approvals.append(tid)

        blocked, reason = gate.should_block_outbound(task)
        if blocked:
            blocked_outbound.append(tid)

    print(f"  [RECONSTRUCTED] {len(all_tasks)} task states from disk:")
    for tid, state in sorted(task_states.items()):
        print(f"    {tid}: {state}")

    audit_entries = runtime.get_audit_trail(limit=10000)
    print(f"  [RECONSTRUCTED] Audit trail: {len(audit_entries)} entries")

    print(f"  [RECONSTRUCTED] Pending approvals: {pending_approvals}")
    print(f"  [RECONSTRUCTED] Blocked outbound: {blocked_outbound}")

    summaries = {}
    for tid in pending_approvals:
        try:
            summary = runtime.operator_summary(tid)
            summaries[tid] = summary
            print(f"\n  [RECONSTRUCTED] Operator summary for {tid}:")
            print(f"    State: {summary['state']}")
            gov = summary['governance']
            print(f"    Governance: approval_required={gov['approval_required']}, "
                  f"outbound_blocked={gov['outbound_blocked']}, "
                  f"execution_authority={gov['execution_authority']}")
            print(f"    Next steps: {summary['next_steps']}")
            pc = summary.get('packet_claims', {})
            print(f"    Packet claims (untrusted): approval_required={pc.get('approval_required')}, "
                  f"outbound_contact={pc.get('outbound_contact')}")
        except Exception as e:
            print(f"  [ERROR] Failed to reconstruct summary for {tid}: {e}")

    blocked_details = {}
    for tid in blocked_outbound:
        try:
            summary = runtime.operator_summary(tid)
            blocked_details[tid] = {
                "state": summary["state"],
                "outbound_blocked": summary["governance"]["outbound_blocked"],
                "outbound_block_reason": summary["governance"]["outbound_block_reason"],
                "execution_authority": summary["governance"]["execution_authority"],
            }
        except Exception as e:
            blocked_details[tid] = {"error": str(e)}

    if blocked_details:
        print(f"\n  [RECONSTRUCTED] Blocked outbound details:")
        for tid, details in blocked_details.items():
            print(f"    {tid}: {details}")

    return {
        "task_counter": task_counter,
        "task_states": task_states,
        "task_records": task_records,
        "audit_count": len(audit_entries),
        "pending_approvals": pending_approvals,
        "blocked_outbound": blocked_outbound,
        "blocked_details": blocked_details,
        "summaries": summaries,
    }


def phase4_verify(captured: dict, reconstructed: dict) -> bool:
    """Compare captured baseline with reconstructed state."""
    print("\n" + "=" * 72)
    print("PHASE 4: VERIFY — Comparing baseline vs reconstructed state")
    print("=" * 72)

    all_pass = True
    total_checks = 0
    passed_checks = 0

    def check(name, expected, actual, description=""):
        nonlocal all_pass, total_checks, passed_checks
        total_checks += 1
        if expected == actual:
            passed_checks += 1
            print(f"  [PASS] {name}")
        else:
            all_pass = False
            print(f"  [FAIL] {name}")
            print(f"         Expected: {expected}")
            print(f"         Actual:   {actual}")
            if description:
                print(f"         ({description})")

    # ── Task Counter ──
    check("task_counter", captured["task_counter"], reconstructed["task_counter"],
          "Sequential task ID counter must persist across cold start")

    # ── Task count ──
    check("task_count", len(captured["task_states"]), len(reconstructed["task_states"]),
          "Number of tasks must match after cold start")

    # ── Individual task states ──
    for tid, expected_state in sorted(captured["task_states"].items()):
        actual_state = reconstructed["task_states"].get(tid, "MISSING")
        check(f"state({tid})", expected_state, actual_state,
              f"Task {tid} state must survive cold start")

    # ── Audit trail ──
    check("audit_entry_count", captured["audit_count"], reconstructed["audit_count"],
          "Audit trail entry count must match after cold start")

    # ── Pending approvals ──
    check("pending_approval_count",
          len(captured["pending_approvals"]), len(reconstructed["pending_approvals"]),
          "Number of pending approvals must match")

    for tid in captured["pending_approvals"]:
        check(f"pending_approval({tid})", True, tid in reconstructed["pending_approvals"],
              f"Pending approval for {tid} must survive cold start")

    # ── Blocked outbound ──
    check("blocked_outbound_count",
          len(captured["blocked_outbound"]), len(reconstructed["blocked_outbound"]),
          "Number of blocked outbound tasks must match")

    for tid in captured["blocked_outbound"]:
        check(f"blocked_outbound({tid})", True, tid in reconstructed["blocked_outbound"],
              f"Outbound block for {tid} must survive cold start")

    # ── Task record field integrity ──
    critical_fields = [
        "task_id", "state", "assigned_subagent", "domain",
        "description", "revision_count",
    ]

    for tid, expected_record in sorted(captured["task_records"].items()):
        actual_record = reconstructed["task_records"].get(tid)
        if actual_record is None:
            total_checks += 1
            all_pass = False
            print(f"  [FAIL] task_record_missing({tid}) -- task not found after cold start")
            continue

        for field in critical_fields:
            expected_val = expected_record.get(field)
            actual_val = actual_record.get(field)
            total_checks += 1
            if expected_val == actual_val:
                passed_checks += 1
            else:
                all_pass = False
                print(f"  [FAIL] {tid}.{field}")
                print(f"         Expected: {expected_val}")
                print(f"         Actual:   {actual_val}")

        # state_log length (timestamps differ, but count must match)
        expected_len = len(expected_record.get("state_log", []))
        actual_len = len(actual_record.get("state_log", []))
        total_checks += 1
        if expected_len == actual_len:
            passed_checks += 1
            print(f"  [PASS] {tid}.state_log_length ({actual_len} entries)")
        else:
            all_pass = False
            print(f"  [FAIL] {tid}.state_log_length")
            print(f"         Expected {expected_len} entries, got {actual_len}")

    # ── Governance reconstruction ──
    for tid in captured["pending_approvals"]:
        if tid in reconstructed["summaries"]:
            gov = reconstructed["summaries"][tid]["governance"]
            check(f"governance_approval_required({tid})", True, gov["approval_required"],
                  "Approval gate must be reconstructed from disk state")
            check(f"governance_outbound_blocked({tid})", True, gov["outbound_blocked"],
                  "Outbound block must be reconstructed from disk state")

    # ── Summary ──
    print("\n" + "-" * 72)
    print(f"RESULTS: {passed_checks}/{total_checks} checks passed")
    if all_pass:
        print("STATUS: ALL CHECKS PASSED -- Cold-start reconstruction verified")
    else:
        print("STATUS: SOME CHECKS FAILED -- Cold-start reconstruction incomplete")
    print("-" * 72)

    return all_pass


def main():
    workspace = sys.argv[1] if len(sys.argv) > 1 else None
    cleanup = False

    if workspace is None:
        workspace = tempfile.mkdtemp(prefix="overcr-coldstart-")
        cleanup = True

    root = Path(workspace)
    print(f"OverCR v0.1.0 Cold-Start Reconstruction Test")
    print(f"Workspace: {root}")
    print()

    try:
        # Phase 1: Populate
        runtime = OverCRRuntime(str(root))
        task_states_populated = phase1_populate(runtime)

        # Phase 1.5: Capture
        task_store = runtime.task_store
        audit_path = root / "runtime" / "audit.jsonl"
        captured = phase1_5_capture(task_store, audit_path)

        # Phase 2: Terminate (simulate by dropping runtime)
        print("\n" + "=" * 72)
        print("PHASE 2: TERMINATE -- Dropping in-memory runtime instance")
        print("  (Filesystem state persists. No in-memory state carried forward.)")
        print("=" * 72)
        del runtime
        del task_store

        # Phase 3: Reconstruct
        reconstructed = phase3_reconstruct(str(root))

        # Phase 4: Verify
        success = phase4_verify(captured, reconstructed)

        # Phase 5: Post-reconstruction operations
        print("\n" + "=" * 72)
        print("PHASE 5: POST-RECONSTRUCTION OPERATIONS")
        print("  Verify that the reconstructed runtime can continue normal operations")
        print("=" * 72)

        runtime2 = OverCRRuntime(str(root))
        task_new = runtime2.create_task(
            domain="research",
            description="Post-reconstruction: Verify continued operation",
            instruction="Verify runtime works after cold start",
            input_context={"test": "post-reconstruction"},
        )
        print(f"  Created {task_new['task_id']} after cold start")
        print(f"  State: {task_new['state']}")

        # Verify task counter continued correctly
        expected_next_id = captured["task_counter"] + 1
        actual_id_num = int(task_new["task_id"].split("-")[1])
        counter_ok = actual_id_num >= expected_next_id
        print(f"  Task counter continuity: expected >= {expected_next_id:04d}, "
              f"got {actual_id_num:04d} -> {'PASS' if counter_ok else 'FAIL'}")

        # Verify the new task can go through lifecycle
        runtime2.simulate_acknowledge(task_new["task_id"])
        t = runtime2.task_store.load_task(task_new["task_id"])
        print(f"  After acknowledge: state={t['state']}")

        post_recon_ok = t["state"] == "in_progress" and counter_ok
        print(f"  Post-reconstruction operations: {'PASS' if post_recon_ok else 'FAIL'}")

        if not success:
            sys.exit(1)

    finally:
        if cleanup:
            print(f"\nCleaning up workspace: {root}")
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    main()
