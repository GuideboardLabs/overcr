#!/usr/bin/env python3
"""
OverCR v2.10.0 — Semantic Compatibility Check

Validates packet field compatibility across versions,
detects semantic drift, and classifies breaking vs compatible changes.

Usage:
    python3 scripts/check_semantic_compatibility.py

Exits 0 if all compatible, 1 if incompatibilities found.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from release import SemanticCompatibility


def main():
    print("=" * 72)
    print("OverCR v2.10.0 — Semantic Compatibility Check")
    print("=" * 72)
    print()

    checker = SemanticCompatibility(str(ROOT))
    report = checker.validate_all()

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

    if report.incompatible_fields:
        print(f"\n  INCOMPATIBLE FIELDS ({len(report.incompatible_fields)}):")
        for inc in report.incompatible_fields:
            print(f"    {inc['field']}: {inc['from']} -> {inc['to']}: {inc['reason']}")

    if report.compatible_evolutions:
        print(f"\n  COMPATIBLE EVOLUTIONS ({len(report.compatible_evolutions)}):")
        for ev in report.compatible_evolutions[:10]:
            print(f"    {ev['field']}: {ev['from']} -> {ev['to']}: {ev['change']}")

    if report.drift_detections:
        print(f"\n  DRIFT DETECTIONS ({len(report.drift_detections)}):")
        for d in report.drift_detections:
            print(f"    {d['schema']}: {d['detail']}")

    print()

    if fails == 0:
        print("  SEMANTIC COMPATIBILITY: PASSED")
        print()
        return 0
    else:
        print("  SEMANTIC COMPATIBILITY: FAILED")
        print()
        return 1


if __name__ == "__main__":
    sys.exit(main())
