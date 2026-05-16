#!/usr/bin/env python3
"""
OverCR v2.9.0 — Release Cleanliness Check

Verifies the source tree has no pycache leakage, .pyc files,
transient debris, orphaned receipts, stale snapshots, missing
docs, version inconsistencies, or mutable artifacts.

Usage:
    python3 scripts/check_release_cleanliness.py

Exits 0 if clean, 1 if issues found.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from integration import ReleaseIntegrity

def main():
    print("=" * 72)
    print("OverCR v2.9.0 — Release Cleanliness Check")
    print("=" * 72)
    print()

    checker = ReleaseIntegrity(str(ROOT))
    report = checker.check_all()

    # Print findings
    if report.findings:
        print("  Findings:")
        for f in report.findings:
            print(f"    [{f['category'].upper()}] {f['path']}")
            print(f"      {f['detail']}")
        print()

    # Print results
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

    if fails:
        print(f"  Findings: {len(report.findings)}")

    if report.warnings and not fails:
        print(f"  Warnings: {len(report.warnings)} (non-blocking)")
        for w in report.warnings:
            print(f"    - {w}")

    print()

    if report.passed and not fails:
        print("  RELEASE CLEANLINESS: PASSED")
        print()
        return 0
    else:
        print("  RELEASE CLEANLINESS: FAILED")
        print()
        return 1


if __name__ == "__main__":
    sys.exit(main())
