#!/usr/bin/env python3
"""
OverCR v2.9.0 — Replay Consistency Check

Verifies replay determinism, audit reconstruction, branch trace
consistency, and receipt replayability across all workflow templates.

Usage:
    python3 scripts/check_replay_consistency.py

Exits 0 if all pass, 1 if any failures.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from integration import ReplayValidator

def main():
    print("=" * 72)
    print("OverCR v2.9.0 — Replay Consistency Check")
    print("=" * 72)
    print()

    validator = ReplayValidator(str(ROOT))

    # 1. Replay determinism
    print("  Phase 1: Replay determinism...")
    report1 = validator.validate_replay_determinism()
    for r in report1.results:
        if r["status"] != "PASS":
            print(f"    [{r['status']}] {r['check']}: {r.get('detail', '')}")

    print()

    # 2. Audit reconstruction
    print("  Phase 2: Audit reconstruction...")
    report2 = validator.validate_audit_reconstruction()
    for r in report2.results:
        if r["status"] != "PASS":
            print(f"    [{r['status']}] {r['check']}: {r.get('detail', '')}")

    print()

    # 3. Branch trace consistency
    print("  Phase 3: Branch trace consistency...")
    report3 = validator.validate_branch_trace_consistency()
    for r in report3.results:
        if r["status"] != "PASS":
            print(f"    [{r['status']}] {r['check']}: {r.get('detail', '')}")

    print()

    # 4. Receipt replayability
    print("  Phase 4: Receipt replayability...")
    report4 = validator.validate_receipt_replayability()
    for r in report4.results:
        if r["status"] != "PASS":
            print(f"    [{r['status']}] {r['check']}: {r.get('detail', '')}")

    # Combine results
    all_reports = [report1, report2, report3, report4]
    total_pass = sum(
        sum(1 for r in rep.results if r["status"] == "PASS")
        for rep in all_reports
    )
    total_fail = sum(
        sum(1 for r in rep.results if r["status"] == "FAIL")
        for rep in all_reports
    )
    total_warn = sum(
        sum(1 for r in rep.results if r["status"] == "WARN")
        for rep in all_reports
    )

    print("=" * 72)
    print(f"  RESULTS: {total_pass} PASS, {total_fail} FAIL, {total_warn} WARN "
          f"(of {total_pass + total_fail + total_warn} checks)")
    print()

    all_errors = []
    for rep in all_reports:
        all_errors.extend(rep.errors)

    if total_fail == 0 and not all_errors:
        print("  REPLAY CONSISTENCY: PASSED")
        print()
        return 0
    else:
        print("  REPLAY CONSISTENCY: FAILED")
        if all_errors:
            print("  Errors:")
            for e in all_errors:
                print(f"    - {e}")
        print()
        return 1


if __name__ == "__main__":
    sys.exit(main())
