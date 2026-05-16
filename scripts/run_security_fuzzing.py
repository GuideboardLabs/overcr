#!/usr/bin/env python3
"""
OverCR v2.10.1 — Run Security Fuzzing

Fuzzes all 10 categories of validators/guards with 64 adversarial inputs.
Report-only — no mutation, no network, no shell execution.

Usage:
    python scripts/run_security_fuzzing.py
    python scripts/run_security_fuzzing.py --category prompt_injection
    python scripts/run_security_fuzzing.py --json
"""

import json
import os
import sys
from pathlib import Path

OVERCR_ROOT = Path(os.environ.get("OVERCR_ROOT", str(Path(__file__).resolve().parent.parent)))
sys.path.insert(0, str(OVERCR_ROOT))

from validation.security_fuzzer import SecurityFuzzer


def main():
    import argparse

    parser = argparse.ArgumentParser(description="OverCR v2.10.1 Security Fuzzing")
    parser.add_argument("--category", type=str, default=None, help="Run single category only")
    parser.add_argument("--json", action="store_true", help="JSON output only")
    parser.add_argument("--verbose", action="store_true", help="Show all cases")
    args = parser.parse_args()

    categories = [args.category] if args.category else None
    fuzzer = SecurityFuzzer(categories=categories)
    report = fuzzer.run()
    report_dict = fuzzer.to_report(report)

    if args.json:
        print(json.dumps(report_dict, indent=2))
    else:
        print("OverCR v2.10.1 Security Fuzzing")
        print(f"Timestamp: {report.timestamp}")
        print("=" * 60)

        for cat, stats in sorted(report_dict["categories"].items()):
            bar = "✓" if stats["failed"] == 0 else "✗"
            print(f"  {bar} {cat:<30} {stats['passed']}/{stats['total']} passed ({stats['pass_rate']}%)")

        print("-" * 60)
        total_failed = report_dict["cases_failed"]
        if total_failed == 0:
            print(f"  ✓ ALL {report_dict['total_cases']} CASES PASSED — no adversarial input slipped through")
        else:
            print(f"  ✗ {total_failed} CASE(S) FAILED — adversarial inputs not caught:")
            for case in report_dict["failed_cases"]:
                print(f"    [{case['category']}] {case['name']}: {case['detail']}")
                print(f"      Payload: {case['payload_preview']}")

        if report_dict["notes"]:
            print(f"\n  Notes: {', '.join(report_dict['notes'])}")

        print()

    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
