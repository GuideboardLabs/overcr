#!/usr/bin/env python3
"""
OverCR v2.9.0 — System Integrity Check

Validates the entire OverCR system structure, schemas, workflow
templates, sandbox backends, audit logs, package versions, replay
prerequisites, and frozen workflow immutability.

Usage:
    python3 scripts/check_v2_integrity.py

Exits 0 if all pass, 1 if any failures.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from integration import SystemValidator

def main():
    print("=" * 72)
    print("OverCR v2.9.0 — System Integrity Check")
    print("=" * 72)
    print()

    validator = SystemValidator(str(ROOT))
    report = validator.validate_all()

    # Print results
    passes = 0
    fails = 0
    warns = 0

    for r in report.results:
        status = r["status"]
        check = r["check"]
        detail = r.get("detail", "")

        if status == "PASS":
            passes += 1
        elif status == "FAIL":
            fails += 1
            print(f"  [FAIL] {check}")
            print(f"         {detail}")
        elif status == "WARN":
            warns += 1
            print(f"  [WARN] {check}: {detail}")

    # Summary
    total = passes + fails + warns
    print()
    print("=" * 72)
    print(f"  RESULTS: {passes} PASS, {fails} FAIL, {warns} WARN  (of {total} checks)")
    print()

    if report.errors:
        print("  ERRORS:")
        for err in report.errors:
            print(f"    - {err}")
        print()

    if report.passed and not report.errors:
        print("  SYSTEM INTEGRITY: PASSED")
        print()
        return 0
    else:
        print("  SYSTEM INTEGRITY: FAILED")
        print()
        return 1


if __name__ == "__main__":
    sys.exit(main())
