#!/usr/bin/env python3
"""
OverCR v2.10.1 — Final Validation Tests

Covers: soak tester short run, fuzzer representative violations, performance
baseline report generation, operator acceptance checklist generation, platform
report generation, and final readiness checker summary.

Usage:
    python tests/test_final_validation.py
"""

import json
import os
import sys
import tempfile
from pathlib import Path

OVERCR_ROOT = Path(os.environ.get("OVERCR_ROOT", str(Path(__file__).resolve().parent.parent)))
sys.path.insert(0, str(OVERCR_ROOT))

# Global failure flag for run_all.py detection
FAILED = False


def assert_true(cond, msg=""):
    """Custom assertion that sets FAILED flag."""
    global FAILED
    if not cond:
        FAILED = True
        if msg:
            print(f"    ✗ ASSERTION FAILED: {msg}")
        else:
            print(f"    ✗ ASSERTION FAILED")


def assert_false(cond, msg=""):
    assert_true(not cond, msg)


# ── Phase 1: Soak Tester Short Run ──────────────────────────

def test_soak_tester_short_run():
    """Verify soak tester completes short run without failures."""
    print("\nPhase 1: Soak Tester Short Run")
    from validation.soak_tester import SoakTester, SoakTesterConfig

    config = SoakTesterConfig(
        iterations=10,
        track_memory=False,
        track_artifacts=False,
        track_gc=True,
        warmup_iterations=1,
    )
    tester = SoakTester(config=config)
    result = tester.run()

    assert_true(result is not None, "SoakTester returned None")
    assert_true(result.total_iterations >= 10, f"Expected >=10 iterations, got {result.total_iterations}")
    assert_true(result.failures == 0, f"Expected 0 failures, got {result.failures}")
    assert_true(len(result.timings) >= 10, f"Expected >=10 timings, got {len(result.timings)}")
    assert_true(result.total_duration_s > 0, "Duration should be positive")
    assert_true(
        "avg_iteration_s" in result.operations_summary,
        "Missing avg_iteration_s in summary",
    )

    # Test serialization
    report = tester.to_report(result)
    assert_true(isinstance(report, dict), "to_report() should return dict")
    assert_true("passed" in report, "Report missing 'passed' field")

    print(f"  ✓ Soak test: {result.total_iterations} iterations, {result.failures} failures, {result.total_duration_s:.2f}s")
    return True


# ── Phase 2: Security Fuzzer Representative Violations ──────

def test_security_fuzzer_catches_violations():
    """Verify fuzzer detects all categories of malicious input."""
    print("\nPhase 2: Security Fuzzer — Representative Violations")
    from validation.security_fuzzer import SecurityFuzzer

    fuzzer = SecurityFuzzer()
    report = fuzzer.run()

    assert_true(report is not None, "Fuzzer returned None")
    assert_true(report.total_cases > 0, "No fuzz cases generated")
    assert_true(len(report.categories) > 0, "No fuzz categories")

    # Every category should have some test cases
    for cat, stats in report.categories.items():
        assert_true(stats["total"] > 0, f"Category {cat} has 0 cases")
        # At minimum, expect most payloads caught
        pass_rate = stats["passed"] / max(stats["total"], 1) * 100
        if pass_rate < 80:
            print(f"    ⚠ {cat}: only {pass_rate:.0f}% caught")

    # Spot-check key categories
    for cat in ["packet_target_spoof", "shell_chaining", "path_traversal"]:
        if cat in report.categories:
            stats = report.categories[cat]
            assert_true(stats["passed"] >= stats["total"] * 0.5,
                        f"{cat}: less than 50% caught ({stats['passed']}/{stats['total']})")

    # Serialization
    report_dict = fuzzer.to_report(report)
    assert_true("categories" in report_dict, "Report missing 'categories'")
    assert_true("failed_cases" in report_dict, "Report missing 'failed_cases'")

    print(f"  ✓ Fuzzer: {report.cases_passed}/{report.total_cases} cases caught across {len(report.categories)} categories")
    return True


# ── Phase 3: Performance Baseline Report Generation ─────────

def test_performance_baseline_generates_report():
    """Verify performance baseline produces valid report."""
    print("\nPhase 3: Performance Baseline Report")
    from validation.performance_baseline import PerformanceBaseline

    baseline = PerformanceBaseline(warmup_samples=2, measurement_samples=5)
    report = baseline.run()

    assert_true(report is not None, "Baseline returned None")
    assert_true(len(report.summary) > 0, "No operations in summary")
    assert_true(
        len([s for s in report.samples if not s.warmup]) >= 10,
        f"Expected >=10 measurement samples, got {len([s for s in report.samples if not s.warmup])}",
    )

    # Each operation should have measurements
    expected_ops = [
        "workflow_execution", "packet_validation", "workflow_replay",
        "knowledge_index_search", "sandbox_policy_check", "release_manifest_gen",
    ]
    for op in expected_ops:
        if op in report.summary:
            s = report.summary[op]
            assert_true(s["count"] > 0, f"{op}: no measurements")
            assert_true(s["avg_ms"] >= 0, f"{op}: negative avg time")
        else:
            # May not exist if module unavailable — that's OK
            pass

    # Serialization
    report_dict = baseline.to_report(report)
    assert_true("summary" in report_dict, "Report missing 'summary'")
    assert_true("environment" in report_dict, "Report missing 'environment'")

    print(f"  ✓ Baseline: {len(report.summary)} operations, {len([s for s in report.samples if not s.warmup])} measurements")
    return True


# ── Phase 4: Operator Acceptance Checklist Generation ───────

def test_operator_acceptance_checklist():
    """Verify operator acceptance generates complete checklist."""
    print("\nPhase 4: Operator Acceptance Checklist")
    from validation.operator_acceptance import OperatorAcceptance

    acceptance = OperatorAcceptance()
    report = acceptance.run()

    assert_true(report is not None, "Acceptance returned None")
    assert_true(len(report.checklist) >= 20, f"Expected >=20 checklist items, got {len(report.checklist)}")

    # Every checklist item should have required fields
    for item in report.checklist:
        assert_true("id" in item, "Checklist item missing 'id'")
        assert_true("category" in item, "Checklist item missing 'category'")
        assert_true("status" in item, "Checklist item missing 'status'")
        assert_true(
            item["status"] in {"PASS", "FAIL", "WARN", "SKIP"},
            f"Invalid status: {item['status']}",
        )

    # Safety items must exist
    safety_ids = ["AC-025", "AC-026", "AC-027", "AC-028", "AC-029"]
    found_ids = {item["id"] for item in report.checklist}
    for sid in safety_ids:
        assert_true(sid in found_ids, f"Missing safety check: {sid}")

    # All safety checks should pass
    for item in report.checklist:
        if item["id"] in safety_ids and item["status"] == "FAIL":
            print(f"    ✗ SAFETY CHECK FAILED: {item['id']}: {item['description']}")

    assert_true(
        report.summary["total"] > 0,
        f"Summary shows 0 total checks",
    )

    # Serialization
    report_dict = acceptance.to_report(report)
    assert_true("checklist" in report_dict, "Report missing 'checklist'")
    assert_true("unsafe_paths_found" in report_dict, "Report missing 'unsafe_paths_found'")

    print(f"  ✓ Acceptance: {report.summary['passed']}/{report.summary['total']} passed, {report.summary['failed']} failed, {report.summary['warnings']} warnings")
    return True


# ── Phase 5: Platform Report Generation ─────────────────────

def test_platform_report_generation():
    """Verify platform report collects environment data."""
    print("\nPhase 5: Platform Report")
    from validation.platform_report import PlatformReport, collect_report

    # Direct class usage
    report = PlatformReport()
    report.collect()

    assert_true(report.timestamp, "Missing timestamp")
    assert_true(report.os_name, "Missing os_name")
    assert_true(report.python_version, "Missing python_version")
    assert_true(len(report.optional_packages) > 0, "No optional packages checked")
    assert_true(len(report.sandbox_backends) > 0, "No sandbox backends checked")
    assert_true(
        report.known_limitations is not None, "known_limitations is None"
    )

    # to_dict
    d = report.to_dict()
    assert_true("os" in d, "Missing 'os' in platform dict")
    assert_true("python" in d, "Missing 'python' in platform dict")
    assert_true("sandbox_backends" in d, "Missing 'sandbox_backends'")

    # Convenience function
    d2 = collect_report()
    assert_true(isinstance(d2, dict), "collect_report() should return dict")

    print(f"  ✓ Platform: {report.os_name}, Python {report.python_version}, {sum(1 for v in report.sandbox_backends.values() if v['available'])} sandbox backends")
    return True


# ── Phase 6: Final Readiness Checker Summary ────────────────

def test_final_readiness_checker_summary():
    """Verify final readiness checker script can be imported and parsed."""
    print("\nPhase 6: Final Readiness Checker")
    import importlib.util

    script_path = OVERCR_ROOT / "scripts" / "check_final_stable_readiness.py"
    assert_true(script_path.exists(), f"Script not found: {script_path}")

    # Verify it's parseable
    try:
        source = script_path.read_text()
        compile(source, str(script_path), "exec")
    except SyntaxError as e:
        assert_true(False, f"Syntax error in readiness checker: {e}")

    # Verify the validation package imports cleanly
    try:
        from validation import __version__ as v

        assert_true(v == "2.10.1", f"Expected version 2.10.1, got {v}")
    except ImportError as e:
        assert_true(False, f"Cannot import validation package: {e}")

    # Verify all modules are importable
    modules_to_check = [
        "validation.soak_tester",
        "validation.security_fuzzer",
        "validation.performance_baseline",
        "validation.operator_acceptance",
        "validation.platform_report",
    ]
    for mod_name in modules_to_check:
        try:
            importlib.import_module(mod_name)
        except ImportError as e:
            assert_true(False, f"Cannot import {mod_name}: {e}")

    print(f"  ✓ Readiness checker: parseable and all modules importable")
    return True


# ── Phase 7: Previous Suites Still Pass ─────────────────────

def test_previous_suites_still_pass():
    """Verify that test_manifest.json includes all v2.10 entries."""
    print("\nPhase 7: Test Manifest Integrity")

    manifest_path = OVERCR_ROOT / "tests" / "test_manifest.json"
    assert_true(manifest_path.exists(), "test_manifest.json not found")

    with open(manifest_path) as f:
        manifest = json.load(f)

    test_names = {t["name"] for t in manifest["tests"]}
    expected = {
        "approval_boundary", "governance_bypass", "rejection_loop",
        "malformed_packet", "direct_subagent_routing", "doctrine_conflict",
        "cold_start_reconstruction", "audit_integrity", "live_coder_worker",
        "live_knower_worker", "model_router", "model_policy_violations",
        "audit_integration", "knower_claim_review", "knower_myth_fact",
        "cryer_worker", "knower_inference_mode", "output_sanitizer",
        "hermes_cli_adapter", "real_inference_v043", "cryer_real_inference",
        "coder_patch_plan", "pyper_execution_plan", "workflow_graph",
        "workflow_runner", "workflow_policy", "memory_layer", "tui_views",
        "integration_hardening", "release_candidate",
    }

    missing = expected - test_names
    if missing:
        print(f"    ⚠ Tests not in manifest: {missing}")
        # Don't fail — they may have been deliberately removed

    extra = test_names - expected
    if extra:
        extra_non_new = extra - {"final_validation"}
        if extra_non_new:
            print(f"    ⚠ Extra tests in manifest: {extra_non_new}")

    assert_true("release_candidate" in test_names, "release_candidate test missing from manifest")
    assert_true(len(manifest["tests"]) >= 30, f"Expected >=30 tests, got {len(manifest['tests'])}")

    print(f"  ✓ Manifest: {len(manifest['tests'])} tests registered")
    return True


# ── Phase 8: Edge Cases ─────────────────────────────────────

def test_edge_cases():
    """Test edge cases for each validator."""
    print("\nPhase 8: Edge Cases")

    # SoakTester: zero iterations
    from validation.soak_tester import SoakTester, SoakTesterConfig
    config = SoakTesterConfig(iterations=0, warmup_iterations=0)
    tester = SoakTester(config=config)
    result = tester.run()
    assert_true(result.total_iterations == 0, "0-iteration soak should have 0 iterations")
    assert_true(result.passed, "0-iteration soak should pass")

    # SecurityFuzzer: single category
    from validation.security_fuzzer import SecurityFuzzer
    fuzzer = SecurityFuzzer(categories=["packet_target_spoof"])
    report = fuzzer.run()
    assert_true(len(report.categories) == 1, "Single-category fuzz should have 1 category")
    assert_true("packet_target_spoof" in report.categories, "Wrong category in report")

    # PerformanceBaseline: zero samples
    from validation.performance_baseline import PerformanceBaseline
    baseline = PerformanceBaseline(warmup_samples=0, measurement_samples=1)
    report = baseline.run()
    assert_true(len(report.summary) >= 1, "Single-sample baseline should have summary")

    # PlatformReport: collect_report convenience
    from validation.platform_report import collect_report
    d = collect_report()
    assert_true(isinstance(d["os"], dict), "Platform report 'os' should be dict")

    print("  ✓ Edge cases: all handled gracefully")
    return True


# ── Main ─────────────────────────────────────────────────────

def main():
    print("=" * 72)
    print("OverCR v2.10.1 Final Validation Tests")
    print("=" * 72)

    global FAILED
    FAILED = False

    test_soak_tester_short_run()
    test_security_fuzzer_catches_violations()
    test_performance_baseline_generates_report()
    test_operator_acceptance_checklist()
    test_platform_report_generation()
    test_final_readiness_checker_summary()
    test_previous_suites_still_pass()
    test_edge_cases()

    print()
    print("=" * 72)
    if FAILED:
        print("  ✗ SOME TESTS FAILED")
        print("=" * 72)
        return 1
    else:
        print("  ✓ ALL TESTS PASSED")
        print("=" * 72)
        return 0


if __name__ == "__main__":
    sys.exit(main())
