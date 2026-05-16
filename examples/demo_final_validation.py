#!/usr/bin/env python3
"""
OverCR v2.10.1 — Demo: Final Validation End-to-End

Demonstrates the complete final validation workflow:
  1. Platform Report
  2. Short Soak Test
  3. Security Fuzzing
  4. Performance Baseline
  5. Operator Acceptance
  6. Final Readiness Summary

Usage:
    python examples/demo_final_validation.py
"""

import json
import os
import sys
import time
from pathlib import Path

OVERCR_ROOT = Path(os.environ.get("OVERCR_ROOT", str(Path(__file__).resolve().parent.parent)))
sys.path.insert(0, str(OVERCR_ROOT))

from validation.soak_tester import SoakTester, SoakTesterConfig
from validation.security_fuzzer import SecurityFuzzer
from validation.performance_baseline import PerformanceBaseline
from validation.operator_acceptance import OperatorAcceptance
from validation.platform_report import PlatformReport, collect_report


def section(title: str):
    print()
    print("─" * 60)
    print(f"  {title}")
    print("─" * 60)


def main():
    print("=" * 60)
    print("  OverCR v2.10.1 — Final Validation Demo")
    print("  Validating v2.10.0 release candidate readiness")
    print("=" * 60)

    overall_start = time.time()

    # ── 1. Platform Report ────────────────────────────────
    section("1. Platform Report")

    platform_dict = collect_report()
    print(f"  OS:        {platform_dict['os']['name']} ({platform_dict['os']['kernel']})")
    print(f"  Python:    {platform_dict['python']['version']}")
    print(f"  Hermes:    {'✓ available' if platform_dict['hermes']['available'] else '✗ not available'}")
    backends = [k for k, v in platform_dict['sandbox_backends'].items() if v]
    print(f"  Backends:  {', '.join(backends) if backends else '(none)'}")
    if platform_dict['known_limitations']:
        print(f"  Limitations ({len(platform_dict['known_limitations'])}):")
        for lim in platform_dict['known_limitations']:
            print(f"    - {lim}")
    print(f"  Notes:     {platform_dict['notes']}")

    # ── 2. Short Soak Test ────────────────────────────────
    section("2. Soak Test (Short — 20 iterations)")

    config = SoakTesterConfig(
        iterations=20,
        track_memory=False,
        track_artifacts=False,
        warmup_iterations=2,
    )
    soak = SoakTester(config=config)
    soak_result = soak.run()
    soak_report = soak.to_report(soak_result)

    status = "✓ PASS" if soak_result.passed else "✗ FAIL"
    print(f"  Status:     {status}")
    print(f"  Iterations: {soak_result.total_iterations}")
    print(f"  Failures:   {soak_result.failures}")
    print(f"  Duration:   {soak_result.total_duration_s:.2f}s")
    ops = soak_result.operations_summary
    if ops.get("avg_iteration_s"):
        print(f"  Avg/iter:   {ops['avg_iteration_s']:.3f}s")
        print(f"  P50/iter:   {ops.get('p50_iteration_s', 0):.3f}s")
    if soak_result.drift_detected:
        print(f"  ⚠ Drift:    detected")
        for note in soak_result.drift_notes:
            print(f"    - {note}")
    else:
        print(f"  Drift:      none detected")

    # ── 3. Security Fuzzing ───────────────────────────────
    section("3. Security Fuzzing (10 categories, 64 cases)")

    fuzzer = SecurityFuzzer()
    fuzz_result = fuzzer.run()
    fuzz_dict = fuzzer.to_report(fuzz_result)

    status = "✓ ALL PASSED" if fuzz_result.passed else "✗ FAILURES FOUND"
    print(f"  Status:     {status}")
    print(f"  Total:      {fuzz_result.total_cases} cases across {len(fuzz_result.categories)} categories")
    print()
    print(f"  {'Category':<28} {'Passed':>7} {'Total':>7} {'Rate':>7}")
    print(f"  {'-'*28} {'-'*7} {'-'*7} {'-'*7}")
    for cat, stats in sorted(fuzz_dict["categories"].items()):
        rate = f"{stats['pass_rate']:.0f}%"
        bar = "✓" if stats["failed"] == 0 else "✗"
        print(f"  {bar} {cat:<26} {stats['passed']:>7} {stats['total']:>7} {rate:>7}")

    if fuzz_dict["failed_cases"]:
        print(f"\n  Failed cases ({len(fuzz_dict['failed_cases'])}):")
        for case in fuzz_dict["failed_cases"][:5]:
            print(f"    [{case['category']}] {case['name']}: {case['detail']}")

    # ── 4. Performance Baseline ───────────────────────────
    section("4. Performance Baseline")

    baseline = PerformanceBaseline(warmup_samples=3, measurement_samples=10)
    perf_result = baseline.run()

    print(f"  {'Operation':<30} {'Avg ms':>8} {'P50 ms':>8} {'P95 ms':>8} {'Min ms':>8} {'Max ms':>8}")
    print(f"  {'-'*30} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*8}")
    for name, s in sorted(perf_result.summary.items()):
        print(f"  {name:<30} {s['avg_ms']:>8.2f} {s['p50_ms']:>8.2f} {s['p95_ms']:>8.2f} {s['min_ms']:>8.2f} {s['max_ms']:>8.2f}")

    print(f"\n  Environment: Python {perf_result.environment.get('python_version', '?')}")

    # ── 5. Operator Acceptance ────────────────────────────
    section("5. Operator Acceptance (30 checks)")

    acceptance = OperatorAcceptance()
    acc_result = acceptance.run()
    acc_dict = acceptance.to_report(acc_result)

    status = "✓ PASS" if acc_result.passed else "✗ FAIL"
    print(f"  Overall:    {status}")
    print(f"  Passed:     {acc_result.summary['passed']}/{acc_result.summary['total']}")
    print(f"  Warnings:   {acc_result.summary['warnings']}")
    if acc_result.summary.get("failed", 0) > 0:
        print(f"  Failed:     {acc_result.summary['failed']}")
        for item in acc_result.checklist:
            if item["status"] == "FAIL":
                print(f"    ✗ {item['id']}: {item['description']}")
    if acc_result.unsafe_paths_found:
        print(f"\n  ⚠ Unsafe paths found:")
        for path in acc_result.unsafe_paths_found:
            print(f"    - {path}")
    if acc_result.warnings:
        print(f"\n  Warnings:")
        for w in acc_result.warnings[:5]:
            print(f"    ⚠ {w}")

    # ── 6. Summary ────────────────────────────────────────
    overall_duration = time.time() - overall_start
    section("6. Final Summary")

    all_passed = (
        soak_result.passed
        and fuzz_result.passed
        and acc_result.passed
    )

    print(f"  Duration:   {overall_duration:.1f}s")
    print(f"  Soak:       {'PASS' if soak_result.passed else 'FAIL'}")
    print(f"  Fuzzing:    {'PASS' if fuzz_result.passed else 'FAIL'} ({fuzz_result.cases_passed}/{fuzz_result.total_cases})")
    print(f"  Operator:   {'PASS' if acc_result.passed else 'FAIL'} ({acc_result.summary['passed']}/{acc_result.summary['total']})")
    print(f"  Platform:   {platform_dict['os']['name']}, Python {platform_dict['python']['version']}")
    print()

    if all_passed:
        print("  ✓ v2.10.0 is READY for stable tag promotion.")
        print("  Recommendation: TAG v2.10.0 AS STABLE")
    else:
        print("  ✗ v2.10.0 is NOT ready for stable tag.")
        print("  Resolve failures above before promoting.")

    print()
    print("─" * 60)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
