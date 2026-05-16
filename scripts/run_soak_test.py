#!/usr/bin/env python3
"""
OverCR v2.10.1 — Run Soak Test

Short CI-safe soak test: 30 iterations, no tracemalloc overhead.
For long soak, import SoakTester directly and configure duration.

Usage:
    python scripts/run_soak_test.py
    python scripts/run_soak_test.py --iterations 100
    python scripts/run_soak_test.py --long  # 1000 iterations with memory tracking
"""

import json
import os
import sys
import time
from pathlib import Path

OVERCR_ROOT = Path(os.environ.get("OVERCR_ROOT", str(Path(__file__).resolve().parent.parent)))
sys.path.insert(0, str(OVERCR_ROOT))

from validation.soak_tester import SoakTester, SoakTesterConfig


def main():
    import argparse

    parser = argparse.ArgumentParser(description="OverCR v2.10.1 Soak Test")
    parser.add_argument("--iterations", type=int, default=30, help="Number of iterations")
    parser.add_argument("--duration", type=int, default=0, help="Max duration in seconds (0=unlimited)")
    parser.add_argument("--long", action="store_true", help="Long mode: 1000 iters + memory tracking")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    parser.add_argument("--fail-fast", action="store_true", help="Stop on first failure")
    parser.add_argument("--json", action="store_true", help="JSON output only")
    args = parser.parse_args()

    if args.long:
        config = SoakTesterConfig(
            iterations=1000,
            track_memory=True,
            track_artifacts=True,
            track_gc=True,
            warmup_iterations=5,
            verbose=args.verbose,
            fail_fast=args.fail_fast,
        )
    else:
        config = SoakTesterConfig(
            iterations=args.iterations,
            duration_seconds=args.duration,
            track_memory=False,
            track_artifacts=False,
            track_gc=True,
            warmup_iterations=3,
            verbose=args.verbose,
            fail_fast=args.fail_fast,
        )

    tester = SoakTester(config=config)

    if not args.json:
        mode = "LONG (1000 iters + memory)" if args.long else f"SHORT ({args.iterations} iters)"
        print(f"OverCR v2.10.1 Soak Test — {mode}")
        print(f"Start: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        print("-" * 60)

    result = tester.run()
    report = tester.to_report(result)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        status = "PASS" if result.passed else "FAIL"
        print(f"\nResult: {status}")
        print(f"Iterations: {result.total_iterations}")
        print(f"Failures: {result.failures}")
        print(f"Duration: {result.total_duration_s:.2f}s")

        ops = result.operations_summary
        if ops.get("avg_iteration_s"):
            print(f"Avg iteration: {ops['avg_iteration_s']:.3f}s")
            print(f"P50 iteration: {ops.get('p50_iteration_s', 0):.3f}s")
            print(f"Min/Max: {ops.get('min_iteration_s', 0):.3f}s / {ops.get('max_iteration_s', 0):.3f}s")

        if result.drift_detected:
            print(f"\n⚠ DRIFT DETECTED:")
            for note in result.drift_notes:
                print(f"  - {note}")

        if result.errors:
            print(f"\nErrors ({len(result.errors)}):")
            for err in result.errors[:10]:
                print(f"  - {err}")
            if len(result.errors) > 10:
                print(f"  ... and {len(result.errors) - 10} more")

        if result.passed:
            print("\n✓ Soak test PASSED — no failures, no drift")
        else:
            print(f"\n✗ Soak test FAILED — {result.failures} failure(s)")

    return 0 if result.passed else 1


if __name__ == "__main__":
    sys.exit(main())
