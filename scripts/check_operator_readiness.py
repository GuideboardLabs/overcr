#!/usr/bin/env python3
"""
OverCR v2.10.0 — Operator Readiness Check

Validates documentation completeness, demo script integrity,
governance documentation, and operator usability.

Usage:
    python3 scripts/check_operator_readiness.py

Exits 0 if ready, 1 if gaps found.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from release import OperatorReadiness


def main():
    print("=" * 72)
    print("OverCR v2.10.0 — Operator Readiness Check")
    print("=" * 72)
    print()

    checker = OperatorReadiness(str(ROOT))
    report = checker.check_all()

    passes = 0
    fails = 0
    warns = 0

    for r in report.results:
        if r["status"] == "FAIL":
            fails += 1
            print(f"  [FAIL] {r['check']}: {r.get('detail', '')}")
        elif r["status"] == "WARN":
            warns += 1
            print(f"  [WARN] {r['check']}: {r.get('detail', '')}")
        else:
            passes += 1

    print()
    print(f"  RESULTS: {passes} PASS, {fails} FAIL, {warns} WARN "
          f"(of {passes + fails + warns} checks)")

    if report.missing_docs:
        print(f"\n  MISSING DOCS ({len(report.missing_docs)}):")
        for md in report.missing_docs:
            print(f"    - {md}")

    if report.stale_examples:
        print(f"\n  STALE EXAMPLES ({len(report.stale_examples)}):")
        for se in report.stale_examples:
            print(f"    - {se}")

    print()

    if fails == 0:
        print("  OPERATOR READINESS: PASSED")
        print()
        return 0
    else:
        print("  OPERATOR READINESS: FAILED")
        print()
        return 1


if __name__ == "__main__":
    sys.exit(main())
