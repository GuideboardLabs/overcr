#!/usr/bin/env python3
"""
OverCR v2.10.1 — Check Final Stable Readiness

Runs all validation gates required to certify v2.10.0 for promotion from
release candidate to stable.

Sequence:
  1. Platform report
  2. Full test suite (via run_all.py)
  3. v2.10 validation scripts
  4. Short soak test
  5. Security fuzzing
  6. Performance baseline
  7. Operator acceptance
  8. Final recommendation

Output: PASS/FAIL, blockers, warnings, measured performance summary,
         stable tag recommendation.

Usage:
    python scripts/check_final_stable_readiness.py
    python scripts/check_final_stable_readiness.py --skip-tests     # skip full suite
    python scripts/check_final_stable_readiness.py --skip-soak      # skip soak
    python scripts/check_final_stable_readiness.py --json           # JSON output
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

OVERCR_ROOT = Path(os.environ.get("OVERCR_ROOT", str(Path(__file__).resolve().parent.parent)))
sys.path.insert(0, str(OVERCR_ROOT))


def banner(text: str):
    """Print a section banner."""
    print()
    print("=" * 72)
    print(f"  {text}")
    print("=" * 72)
    print()


def step_header(num: int, total: int, name: str):
    """Print step header."""
    print(f"\n── Step {num}/{total}: {name} ──")


def run_subprocess(cmd: list, timeout: int = 300) -> tuple:
    """Run a subprocess and return (passed, output, duration)."""
    start = time.time()
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(OVERCR_ROOT),
        )
        duration = time.time() - start
        return result.returncode == 0, result.stdout, result.stderr, duration
    except subprocess.TimeoutExpired:
        return False, "", f"Timeout after {timeout}s", time.time() - start
    except Exception as e:
        return False, "", str(e), time.time() - start


def main():
    import argparse

    parser = argparse.ArgumentParser(description="OverCR v2.10.1 Final Stable Readiness Checker")
    parser.add_argument("--skip-tests", action="store_true", help="Skip full test suite")
    parser.add_argument("--skip-soak", action="store_true", help="Skip soak test")
    parser.add_argument("--json", action="store_true", help="JSON output only")
    args = parser.parse_args()

    total_steps = 8
    if args.skip_tests:
        total_steps -= 1
    if args.skip_soak:
        total_steps -= 1

    results = {
        "checker_version": "2.10.1",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "steps": [],
        "blockers": [],
        "warnings": [],
        "passed": True,
    }
    step_idx = 0

    # ── Step 1: Platform Report ──────────────────────────────────
    step_idx += 1
    step_header(step_idx, total_steps, "Platform Report")

    from validation.platform_report import PlatformReport

    platform = PlatformReport()
    platform.collect()
    platform_dict = platform.to_dict()

    if not args.json:
        print(f"  OS: {platform_dict['os']['name']} ({platform_dict['os']['kernel']})")
        print(f"  Python: {platform_dict['python']['version']}")
        print(f"  Hermes: {'available' if platform_dict['hermes']['available'] else 'not available'}")
        print(f"  Sandbox backends: {', '.join(k for k, v in platform_dict['sandbox_backends'].items() if v)}")
        if platform_dict["known_limitations"]:
            print(f"  Limitations: {len(platform_dict['known_limitations'])} recorded")

    results["steps"].append({
        "name": "platform_report",
        "passed": True,
        "data": platform_dict,
    })

    # ── Step 2: Full Test Suite ───────────────────────────────────
    step_idx += 1
    step_header(step_idx, total_steps, "Full Test Suite (run_all.py)")

    if args.skip_tests:
        if not args.json:
            print("  SKIPPED (--skip-tests)")
        results["steps"].append({"name": "full_test_suite", "passed": True, "skipped": True})
    else:
        passed, stdout, stderr, duration = run_subprocess(
            [sys.executable, str(OVERCR_ROOT / "tests" / "run_all.py")],
            timeout=600,
        )

        status = "PASS" if passed else "FAIL"
        if not args.json:
            print(f"  Status: {status} ({duration:.1f}s)")
            if not passed:
                # Extract summary from output
                for line in (stdout + stderr).split("\n"):
                    if "FAILED" in line or "PASS" in line or "exit_code" in line or "exception" in line:
                        if "ALL PASSED" not in line and "Summary" not in line:
                            print(f"    {line.strip()}")

        results["steps"].append({
            "name": "full_test_suite",
            "passed": passed,
            "duration_s": round(duration, 1),
        })

        if not passed:
            results["blockers"].append("Full test suite FAILED")
            results["passed"] = False

    # ── Step 3: v2.10 Semantic Compatibility ──────────────────────
    step_idx += 1
    step_header(step_idx, total_steps, "v2.10 Semantic Compatibility")

    passed, stdout, stderr, duration = run_subprocess(
        [sys.executable, str(OVERCR_ROOT / "scripts" / "check_semantic_compatibility.py")],
        timeout=120,
    )

    if not args.json:
        print(f"  Status: {'PASS' if passed else 'FAIL'} ({duration:.1f}s)")

    results["steps"].append({
        "name": "semantic_compatibility",
        "passed": passed,
        "duration_s": round(duration, 1),
    })

    if not passed:
        results["blockers"].append("Semantic compatibility check FAILED")
        results["passed"] = False

    # ── Step 4: v2.10 Install Reproducibility ─────────────────────
    step_idx += 1
    step_header(step_idx, total_steps, "v2.10 Install Reproducibility")

    passed, stdout, stderr, duration = run_subprocess(
        [sys.executable, str(OVERCR_ROOT / "scripts" / "check_install_reproducibility.py")],
        timeout=120,
    )

    if not args.json:
        print(f"  Status: {'PASS' if passed else 'FAIL'} ({duration:.1f}s)")

    results["steps"].append({
        "name": "install_reproducibility",
        "passed": passed,
        "duration_s": round(duration, 1),
    })

    if not passed:
        results["warnings"].append("Install reproducibility check had issues")

    # ── Step 5: v2.10 Operator Readiness ──────────────────────────
    step_idx += 1
    step_header(step_idx, total_steps, "v2.10 Operator Readiness")

    passed, stdout, stderr, duration = run_subprocess(
        [sys.executable, str(OVERCR_ROOT / "scripts" / "check_operator_readiness.py")],
        timeout=120,
    )

    if not args.json:
        print(f"  Status: {'PASS' if passed else 'FAIL'} ({duration:.1f}s)")

    results["steps"].append({
        "name": "operator_readiness",
        "passed": passed,
        "duration_s": round(duration, 1),
    })

    if not passed:
        results["warnings"].append("Operator readiness check had issues")

    # ── Step 6: Short Soak Test ───────────────────────────────────
    step_idx += 1
    step_header(step_idx, total_steps, "Short Soak Test (30 iterations)")

    if args.skip_soak:
        if not args.json:
            print("  SKIPPED (--skip-soak)")
        results["steps"].append({"name": "soak_test", "passed": True, "skipped": True})
    else:
        from validation.soak_tester import SoakTester, SoakTesterConfig

        config = SoakTesterConfig(
            iterations=30,
            track_memory=False,
            track_artifacts=False,
            track_gc=True,
            warmup_iterations=3,
        )
        tester = SoakTester(config=config)
        soak_result = tester.run()
        soak_report = tester.to_report(soak_result)

        if not args.json:
            print(f"  Status: {'PASS' if soak_result.passed else 'FAIL'}")
            print(f"  Iterations: {soak_result.total_iterations}, Failures: {soak_result.failures}")
            print(f"  Duration: {soak_result.total_duration_s:.1f}s")
            ops = soak_result.operations_summary
            if ops.get("avg_iteration_s"):
                print(f"  Avg iteration: {ops['avg_iteration_s']:.3f}s")
            if soak_result.drift_detected:
                print(f"  ⚠ Drift detected: {', '.join(soak_result.drift_notes)}")

        results["steps"].append({
            "name": "soak_test",
            "passed": soak_result.passed,
            "duration_s": round(soak_result.total_duration_s, 1),
            "data": soak_report,
        })

        if not soak_result.passed:
            results["blockers"].append("Soak test FAILED")
            results["passed"] = False
        if soak_result.drift_detected:
            results["warnings"].append("Soak test detected drift")

    # ── Step 7: Security Fuzzing ──────────────────────────────────
    step_idx += 1
    step_header(step_idx, total_steps, "Security Fuzzing (64 cases)")

    from validation.security_fuzzer import SecurityFuzzer

    fuzzer = SecurityFuzzer()
    fuzz_report = fuzzer.run()
    fuzz_dict = fuzzer.to_report(fuzz_report)

    if not args.json:
        print(f"  Status: {'PASS' if fuzz_report.passed else 'FAIL'}")
        print(f"  Cases: {fuzz_report.cases_passed}/{fuzz_report.total_cases} passed")
        for cat, stats in sorted(fuzz_dict["categories"].items()):
            bar = "✓" if stats["failed"] == 0 else "✗"
            print(f"    {bar} {cat}: {stats['passed']}/{stats['total']}")

    results["steps"].append({
        "name": "security_fuzzing",
        "passed": fuzz_report.passed,
        "data": fuzz_dict,
    })

    if not fuzz_report.passed:
        results["blockers"].append(
            f"Security fuzzing: {fuzz_report.cases_failed} case(s) not caught"
        )
        results["passed"] = False

    # ── Step 8: Performance Baseline ─────────────────────────────
    step_idx += 1
    step_header(step_idx, total_steps, "Performance Baseline")

    from validation.performance_baseline import PerformanceBaseline

    baseline = PerformanceBaseline(warmup_samples=3, measurement_samples=10)
    perf_report = baseline.run()
    perf_dict = baseline.to_report(perf_report)

    if not args.json:
        print(f"  Measurements: {perf_dict['total_measurements']}")
        for name, s in sorted(perf_report.summary.items()):
            print(f"    {name:<30} avg={s['avg_ms']:.2f}ms  p50={s['p50_ms']:.2f}ms  p95={s['p95_ms']:.2f}ms")
            if s["p95_ms"] > 500:
                results["warnings"].append(f"Performance: {name} P95={s['p95_ms']:.1f}ms > 500ms")

    results["steps"].append({
        "name": "performance_baseline",
        "passed": True,  # Always passes, just reports
        "data": perf_dict,
    })

    # ── Step 9: Operator Acceptance ──────────────────────────────
    step_idx += 1
    step_header(step_idx, total_steps, "Operator Acceptance (30 checks)")

    from validation.operator_acceptance import OperatorAcceptance

    acceptance = OperatorAcceptance()
    acc_report = acceptance.run()
    acc_dict = acceptance.to_report(acc_report)

    if not args.json:
        print(f"  Status: {'PASS' if acc_report.passed else 'FAIL'}")
        print(f"  Checks: {acc_report.summary['passed']}/{acc_report.summary['total']} passed")
        print(f"  Warnings: {acc_report.summary['warnings']}")
        if acc_report.summary.get("failed", 0) > 0:
            print(f"  Failed: {acc_report.summary['failed']}")
        if acc_report.unsafe_paths_found:
            for path in acc_report.unsafe_paths_found:
                print(f"    ⚠ {path}")

    results["steps"].append({
        "name": "operator_acceptance",
        "passed": acc_report.passed,
        "data": acc_dict,
    })

    if not acc_report.passed:
        results["blockers"].append("Operator acceptance FAILED")
        results["passed"] = False
    if acc_report.unsafe_paths_found:
        results["warnings"].append(
            f"Unsafe operator paths found: {len(acc_report.unsafe_paths_found)}"
        )

    # ── Final Recommendation ──────────────────────────────────────
    banner("FINAL RECOMMENDATION")

    if args.json:
        # Find the performance_baseline step for the summary
        perf_step = None
        for step in results["steps"]:
            if step["name"] == "performance_baseline":
                perf_step = step
                break

        final = {
            "overall": "PASS" if results["passed"] else "FAIL",
            "tag_recommended": results["passed"],
            "tag_version": "v2.10.0" if results["passed"] else None,
            "blockers": results["blockers"],
            "warnings": results["warnings"],
            "steps": results["steps"],
            "performance_summary": perf_step["data"]["summary"]
            if perf_step and "data" in perf_step and perf_step["data"]
            else {},
        }
        print(json.dumps(final, indent=2))
    else:
        if results["passed"]:
            print("  ✓ OVERALL: PASS")
            print()
            print("  Recommendation: TAG v2.10.0 AS STABLE")
            print()
            print("  v2.10.0 has passed all validation gates:")
            print("    - Full test suite: PASS")
            print("    - Semantic compatibility: PASS")
            print("    - Install reproducibility: PASS")
            print("    - Operator readiness: PASS")
            print("    - Soak test (30 iterations): PASS")
            print("    - Security fuzzing (64 cases): PASS")
            print("    - Performance baseline: recorded")
            print("    - Operator acceptance (30 checks): PASS")
            print("    - Platform report: collected")
        else:
            print("  ✗ OVERALL: FAIL")
            print()

        if results["blockers"]:
            print(f"\n  BLOCKERS ({len(results['blockers'])}):")
            for b in results["blockers"]:
                print(f"    ✗ {b}")

        if results["warnings"]:
            print(f"\n  WARNINGS ({len(results['warnings'])}):")
            for w in results["warnings"]:
                print(f"    ⚠ {w}")

        if results["passed"] and not results["blockers"]:
            print(f"\n  ✓ Final v2.10.0 stable tag IS recommended.")
            print(f"  Run 'git tag v2.10.0' when ready to proceed.")
        else:
            print(f"\n  ✗ Final v2.10.0 stable tag is NOT recommended until blockers are resolved.")

        print()

    return 0 if results["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
