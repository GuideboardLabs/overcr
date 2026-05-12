#!/usr/bin/env python3
"""
OverCR v0.1.0 Audit Integrity Test

Tests that the AuditIntegrityVerifier correctly detects tampering and
missing audit entries when the audit log is modified or corrupted —
and that live state is never damaged by the verification process.

Procedure:
  1. Phase 1 — Build: Populate a workspace using the runtime, creating
     multiple tasks across diverse lifecycle states.
  2. Phase 2 — Baseline: Run the integrity verifier on the pristine
     workspace. Assert integrity_risk = "none".
  3. Phase 3 — Tamper: Copy the audit log, then apply specific mutations
     to the copy (not the original):
     a. Remove an audit entry (simulating deletion)
     b. Alter an audit entry (simulating tampering with state transitions)
     c. Insert an invalid state transition
  4. Phase 4 — Verify on tampered copy: Run the verifier against the
     tampered copy. Assert it detects each mutation category.
  5. Phase 5 — Verify original intact: Re-run the verifier against the
     original (live) workspace. Assert integrity_risk = "none" — the
     live state was not damaged by the tampering or verification process.
  6. Phase 6 — Post-verification operations: Confirm the runtime can
     continue normal operations after verification (new tasks, transitions).

Expected result:
  - Audit verification detects inconsistencies in the tampered copy
  - Live state is not damaged (original workspace stays clean)
  - Runtime reports integrity risk levels correctly
"""

import json
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from runtime.overcr_runtime import OverCRRuntime
from runtime.task_store import TaskStore
from runtime.audit_integrity import AuditIntegrityVerifier


# ── Packet helpers (L6-valid) ────────────────────────────────────────

def make_cryer_recon_packet(task_id: str, yield_score: int = 72) -> dict:
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
            "targets": [{
                "entity": "Test Business Corp",
                "type": "business",
                "signals": {"reputation": {"yield_score": yield_score, "confidence": 75, "risk_flags": []}},
                "raw_sources": ["public_directory_listing"],
            }],
        },
        "audit_trail": {
            "collection_timestamps": [datetime.now(timezone.utc).isoformat()],
            "methods_used": ["public_directory_scan"],
        },
        "approval_required": False,
        "next_steps_recommendation": "Submit to OverCR for routing.",
        "outbound_contact": None,
    }


def make_pyper_approval_packet(task_id: str, entity: str = "Test Business Corp") -> dict:
    return {
        "packet_type": "pyper_approval",
        "version": "1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "pyper",
        "target": "overcr",
        "task_id": task_id,
        "summary": f"Outreach draft for {entity}",
        "draft_data": {
            "prospects": [{
                "entity": entity,
                "approach_type": "warm_intro",
                "drafts": [{"body": f"Dear {entity}, ...", "evidence_citations": ["Public directory"]}],
            }],
        },
        "audit_trail": {"upstream_sources": ["task-0000"]},
        "approval_required": True,
        "next_steps_recommendation": "Review and approve",
        "outbound_contact": {"entity": entity, "channel": "email"},
    }


def make_knower_research_packet(task_id: str) -> dict:
    return {
        "packet_type": "knower_research",
        "version": "1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "knower",
        "target": "overcr",
        "task_id": task_id,
        "summary": "Research complete.",
        "research_data": {
            "topic": "tech_growth",
            "findings": [{"claim": "Industry growing 15%", "confidence": 3, "sources": ["report_A"], "gaps": []}],
        },
        "audit_trail": {"sources_consulted": ["report_A"]},
        "approval_required": False,
        "next_steps_recommendation": "Submit to OverCR for routing.",
        "outbound_contact": None,
    }


# ── Test runner ──────────────────────────────────────────────────────

def main():
    workspace = sys.argv[1] if len(sys.argv) > 1 else None
    cleanup = False
    if workspace is None:
        workspace = tempfile.mkdtemp(prefix="overcr-audit-integrity-")
        cleanup = True

    root = Path(workspace)
    total_checks = 0
    passed_checks = 0
    all_pass = True

    def check(name, expected, actual, description=""):
        nonlocal total_checks, passed_checks, all_pass
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

    try:
        # ══════════════════════════════════════════════════════════════
        print("=" * 72)
        print("PHASE 1: BUILD — Populating workspace with task lifecycle data")
        print("=" * 72)

        runtime = OverCRRuntime(str(root))

        # Task A: Full lifecycle (created -> completed)
        task_a = runtime.create_task("recon", "Recon sector analysis", "Scan sector", {"region": "X"})
        runtime.simulate_acknowledge(task_a["task_id"])
        runtime.receive_response(task_a["task_id"], make_cryer_recon_packet(task_a["task_id"]))
        runtime.validate_response(task_a["task_id"])
        runtime.route(task_a["task_id"])

        # Task B: PypER -> approval_pending
        task_b = runtime.create_task("outreach", "Outreach draft", "Draft outreach", {"entity": "Test"})
        runtime.simulate_acknowledge(task_b["task_id"])
        runtime.receive_response(task_b["task_id"], make_pyper_approval_packet(task_b["task_id"]))
        runtime.validate_response(task_b["task_id"])
        runtime.route(task_b["task_id"])  # -> approval_pending

        # Task C: KnowER -> routed
        task_c = runtime.create_task("research", "Research topic", "Analyze", {"domain": "tech"})
        runtime.simulate_acknowledge(task_c["task_id"])
        runtime.receive_response(task_c["task_id"], make_knower_research_packet(task_c["task_id"]))
        runtime.validate_response(task_c["task_id"])
        runtime.route(task_c["task_id"])

        # Task D: Just created (never acknowledged)
        task_d = runtime.create_task("recon", "Idle recon task", "Gather data", {"entity": "Idle"})

        # Task E: PypER -> approved -> completed
        task_e = runtime.create_task("outreach", "Approved outreach", "Draft approved", {"entity": "Approved Co"})
        runtime.simulate_acknowledge(task_e["task_id"])
        runtime.receive_response(task_e["task_id"], make_pyper_approval_packet(task_e["task_id"], "Approved Co"))
        runtime.validate_response(task_e["task_id"])
        runtime.route(task_e["task_id"])
        runtime.process_approval(task_e["task_id"], "approved", "Good to go")

        print(f"  Created 5 tasks across diverse lifecycle states")

        # ══════════════════════════════════════════════════════════════
        print("\n" + "=" * 72)
        print("PHASE 2: BASELINE — Verify pristine workspace has integrity_risk=none")
        print("=" * 72)

        verifier = AuditIntegrityVerifier(str(root))
        baseline_report = verifier.verify()

        check("baseline_integrity_risk", "none", baseline_report["integrity_risk"],
              "Pristine workspace should have no integrity risk")
        check("baseline_findings_count", 0, len(baseline_report["findings"]),
              "Pristine workspace should have zero findings")

        # ══════════════════════════════════════════════════════════════
        print("\n" + "=" * 72)
        print("PHASE 3: TAMPER — Copy audit log and apply mutations")
        print("=" * 72)

        audit_path = root / "runtime" / "audit.jsonl"

        # Read the original audit log
        with open(audit_path) as f:
            original_lines = f.readlines()

        print(f"  Original audit log: {len(original_lines)} lines")

        # ── TAMPER 1: Remove an audit entry (simulate deletion) ──
        # Find the first state_transition entry for Task A and delete it
        tamper1_lines = []
        removed_entry = None
        removed_index = -1
        for i, line in enumerate(original_lines):
            entry = json.loads(line.strip())
            if (entry.get("entry_type") == "state_transition"
                    and entry.get("task_id") == task_a["task_id"]
                    and entry.get("details", {}).get("to_state") == "assigned"
                    and removed_entry is None):
                removed_entry = entry
                removed_index = i
                # Skip this line — simulate it being deleted
                print(f"  TAMPER 1: Removed line {i+1} — state_transition {task_a['task_id']} -> 'assigned'")
                continue
            tamper1_lines.append(line)

        tamper1_path = root / "runtime" / "audit_tamper1.jsonl"
        with open(tamper1_path, "w") as f:
            f.writelines(tamper1_lines)
        print(f"  Tamper 1 workspace written: {len(tamper1_lines)} lines (removed 1)")

        # ── TAMPER 2: Alter a state transition in the log ──
        # Change a valid transition "created -> assigned" to an invalid one "completed -> assigned"
        tamper2_lines = list(original_lines)  # fresh copy
        altered = False
        for i, line in enumerate(tamper2_lines):
            entry = json.loads(line.strip())
            if (entry.get("entry_type") == "state_transition"
                    and entry.get("task_id") == task_b["task_id"]
                    and entry.get("details", {}).get("to_state") == "approval_pending"
                    and not altered):
                # Mutate: change from_state from "routed" to "created" (impossible: created -> approval_pending)
                tamper2_lines[i] = json.dumps({
                    **entry,
                    "details": {
                        **entry["details"],
                        "from_state": "created",  # IMPOSSIBLE: created -> approval_pending
                        "to_state": "approval_pending",
                        "note": "TAMPERED: impossible transition",
                    }
                }) + "\n"
                print(f"  TAMPER 2: Altered line {i+1} — changed transition to impossible 'created -> approval_pending'")
                altered = True
                break

        tamper2_path = root / "runtime" / "audit_tamper2.jsonl"
        with open(tamper2_path, "w") as f:
            f.writelines(tamper2_lines)

        # ── TAMPER 3: Remove ALL audit entries for one task (severe deletion) ──
        tamper3_lines = []
        for line in original_lines:
            entry = json.loads(line.strip())
            if entry.get("task_id") == task_c["task_id"]:
                continue  # Remove all entries for Task C
            tamper3_lines.append(line)

        tamper3_path = root / "runtime" / "audit_tamper3.jsonl"
        with open(tamper3_path, "w") as f:
            f.writelines(tamper3_lines)
        print(f"  TAMPER 3: Removed all audit entries for {task_c['task_id']} ({len(original_lines) - len(tamper3_lines)} lines removed)")

        # ══════════════════════════════════════════════════════════════
        print("\n" + "=" * 72)
        print("PHASE 4: DETECT — Run verifier on each tampered copy")
        print("=" * 72)

        # ── TAMPER 1 Detection: Missing audit entry ──
        # Swap the audit log temporarily
        print("\n  --- Tamper 1: Missing audit entry ---")
        live_audit_backup = root / "runtime" / "audit_live_backup.jsonl"
        shutil.copy2(audit_path, live_audit_backup)
        shutil.copy2(tamper1_path, audit_path)

        verifier1 = AuditIntegrityVerifier(str(root))
        report1 = verifier1.verify()

        check("tamper1_risk_not_none", True, report1["integrity_risk"] != "none",
              "Missing entry should trigger integrity risk")
        check("tamper1_has_findings", True, len(report1["findings"]) > 0,
              "Missing entry should produce findings")
        missing_audit_findings = [f for f in report1["findings"] if f["category"] == "missing_audit_entry"]
        check("tamper1_missing_audit_found", True, len(missing_audit_findings) > 0,
              "Missing audit_entry finding should be detected")

        # Restore original
        shutil.copy2(live_audit_backup, audit_path)
        live_audit_backup.unlink()

        # ── TAMPER 2 Detection: Invalid state transition ──
        print("\n  --- Tamper 2: Altered state transition (invalid) ---")
        shutil.copy2(audit_path, live_audit_backup)
        shutil.copy2(tamper2_path, audit_path)

        verifier2 = AuditIntegrityVerifier(str(root))
        report2 = verifier2.verify()

        check("tamper2_risk_not_none", True, report2["integrity_risk"] != "none",
              "Impossible transition should trigger integrity risk")
        invalid_transitions = [f for f in report2["findings"] if f["category"] == "invalid_state_transition"]
        check("tamper2_invalid_transition_found", True, len(invalid_transitions) > 0,
              "Impossible state transition should be detected")

        # Restore original
        shutil.copy2(live_audit_backup, audit_path)
        live_audit_backup.unlink()

        # ── TAMPER 3 Detection: All entries for one task removed ──
        print("\n  --- Tamper 3: Entire task audit trail removed ---")
        shutil.copy2(audit_path, live_audit_backup)
        shutil.copy2(tamper3_path, audit_path)

        verifier3 = AuditIntegrityVerifier(str(root))
        report3 = verifier3.verify()

        check("tamper3_risk_not_none", True, report3["integrity_risk"] != "none",
              "Removed task audit should trigger integrity risk")

        # Task C's state_log has entries but no audit entries at all
        missing_findings = [f for f in report3["findings"] if f["category"] == "missing_audit_entry"]
        check("tamper3_missing_audit_found", True, len(missing_findings) > 0,
              "Missing audit entries for task C should be detected")
        task_c_missing = [f for f in missing_findings if f["task_id"] == task_c["task_id"]]
        check("tamper3_task_c_missing", True, len(task_c_missing) > 0,
              f"Task C ({task_c['task_id']}) should have missing audit findings")

        # Also check for terminal state missing completion audit
        # and verify the task existed but all its audit entries are gone

        # Restore original
        shutil.copy2(live_audit_backup, audit_path)
        live_audit_backup.unlink()

        # ══════════════════════════════════════════════════════════════
        print("\n" + "=" * 72)
        print("PHASE 5: LIVE INTACT — Verify original workspace still has no findings")
        print("=" * 72)

        # Verify the original audit log was not damaged
        original_check = AuditIntegrityVerifier(str(root))
        original_report = original_check.verify()

        check("live_intact_risk", "none", original_report["integrity_risk"],
              "Live workspace should still have no integrity risk after all tampering")
        check("live_intact_findings", 0, len(original_report["findings"]),
              "Live workspace should have zero findings after all tampering")

        # Verify the original audit log line count is unchanged
        with open(audit_path) as f:
            post_lines = f.readlines()
        check("live_intact_line_count", len(original_lines), len(post_lines),
              "Original audit log line count should be unchanged")

        # ══════════════════════════════════════════════════════════════
        print("\n" + "=" * 72)
        print("PHASE 6: POST-VERIFICATION — Runtime continues normal operations")
        print("=" * 72)

        # Create a new task after verification to confirm runtime still works
        task_new = runtime.create_task("research", "Post-verification task", "Check runtime works", {"test": True})
        runtime.simulate_acknowledge(task_new["task_id"])
        task_after = runtime.task_store.load_task(task_new["task_id"])

        check("post_verify_task_state", "in_progress", task_after["state"],
              "Runtime should create and acknowledge tasks after verification")

        # Run integrity check again — should still be clean
        post_verify_report = AuditIntegrityVerifier(str(root)).verify()
        check("post_verify_integrity_risk", "none", post_verify_report["integrity_risk"],
              "Integrity risk should remain 'none' after post-verification operations")

        # ══════════════════════════════════════════════════════════════
        print("\n" + "=" * 72)
        print("PHASE 7: DETAILED CATEGORY COVERAGE")
        print("  Verify each finding category is produced by at least one tamper")
        print("=" * 72)

        all_findings = (
            report1["findings"]
            + report2["findings"]
            + report3["findings"]
        )
        all_categories = set(f["category"] for f in all_findings)

        required_categories = {
            "missing_audit_entry",
            "invalid_state_transition",
        }
        for cat in required_categories:
            check(f"category_{cat}", True, cat in all_categories,
                  f"Finding category '{cat}' should be produced by at least one tamper scenario")

        # ══════════════════════════════════════════════════════════════
        print("\n" + "-" * 72)
        print(f"RESULTS: {passed_checks}/{total_checks} checks passed")
        if all_pass:
            print("STATUS: ALL CHECKS PASSED — Audit integrity verification verified")
        else:
            print("STATUS: SOME CHECKS FAILED — Audit integrity verification incomplete")
        print("-" * 72)

        # Clean up tamper files
        for tamper_file in [tamper1_path, tamper2_path, tamper3_path]:
            if tamper_file.exists():
                tamper_file.unlink()

        if not all_pass:
            sys.exit(1)

    finally:
        if cleanup:
            print(f"\nCleaning up workspace: {root}")
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    main()