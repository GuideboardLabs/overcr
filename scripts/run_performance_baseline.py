#!/usr/bin/env python3
"""
OverCR v2.10.1 — Run Performance Baseline

Measures deterministic latency for 6 core operations. JSON output.
No network. No performance claims beyond measured environment.

Usage:
    python scripts/run_performance_baseline.py
    python scripts/run_performance_baseline.py --samples 50 --warmup 5
    python scripts/run_performance_baseline.py --json
"""

import json
import os
import sys
from pathlib import Path

OVERCR_ROOT = Path(os.environ.get("OVERCR_ROOT", str(Path(__file__).resolve().parent.parent)))
sys.path.insert(0, str(OVERCR_ROOT))

from validation.performance_baseline import PerformanceBaseline


def main():
    import argparse

    parser = argparse.ArgumentParser(description="OverCR v2.10.1 Performance Baseline")
    parser.add_argument("--samples", type=int, default=10, help="Measurement samples per operation")
    parser.add_argument("--warmup", type=int, default=3, help="Warmup samples per operation")
    parser.add_argument("--json", action="store_true", help="JSON output only")
    args = parser.parse_args()

    baseline = PerformanceBaseline(
        warmup_samples=args.warmup,
        measurement_samples=args.samples,
    )
    report = baseline.run()
    report_dict = baseline.to_report(report)

    if args.json:
        print(json.dumps(report_dict, indent=2))
    else:
        print("OverCR v2.10.1 Performance Baseline")
        print(f"Timestamp: {report.timestamp}")
        env = report.environment
        print(f"Python: {env.get('python_version', 'unknown')}")
        print(f"Platform: {env.get('platform', env.get('os', 'unknown'))}")
        print("=" * 70)
        print(f"  {'Operation':<30} {'Avg ms':>8} {'Min ms':>8} {'Max ms':>8} {'P50 ms':>8} {'P95 ms':>8}")
        print(f"  {'-'*30} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*8}")

        summary = report.summary
        for name in sorted(summary):
            s = summary[name]
            print(
                f"  {name:<30} {s['avg_ms']:>8.2f} {s['min_ms']:>8.2f} "
                f"{s['max_ms']:>8.2f} {s['p50_ms']:>8.2f} {s['p95_ms']:>8.2f}"
            )

        print()
        total_samples = sum(v["count"] for v in summary.values())
        print(f"  Total measurements: {total_samples} ({len(summary)} operations × {args.samples} samples)")

        # Flag any pathological outliers
        for name, s in summary.items():
            if s["max_ms"] > s["avg_ms"] * 10:
                print(f"  ⚠ {name}: max={s['max_ms']:.2f}ms is {s['max_ms']/max(s['avg_ms'],0.01):.0f}x avg — possible outlier")
            if s["p95_ms"] > 500:
                print(f"  ⚠ {name}: P95={s['p95_ms']:.2f}ms — exceeds 500ms threshold")

        print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
