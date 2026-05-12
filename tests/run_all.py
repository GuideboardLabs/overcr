#!/usr/bin/env python3
"""
OverCR v0.7.0 Consolidated Test Suite Runner
=============================================

Runs all regression tests from a single entry point.

Usage:
    python3 tests/run_all.py              # Run all tests
    python3 tests/run_all.py --fail-fast   # Stop on first failure
    python3 tests/run_all.py --category governance  # Run only governance tests
    python3 tests/run_all.py --test approval_boundary  # Run one test by name

Exits 0 if all pass, 1 if any fail.
"""

import importlib
import json
import os
import sys
import tempfile
import time
from pathlib import Path

# Resolve OVERCR_ROOT: env var > dynamic derivation
OVERCR_ROOT = Path(os.environ.get("OVERCR_ROOT", str(Path(__file__).resolve().parent.parent)))
sys.path.insert(0, str(OVERCR_ROOT))

MANIFEST_PATH = Path(__file__).resolve().parent / "test_manifest.json"


class _ExitInterceptor(Exception):
    """Raised when a test calls sys.exit(). Carries the exit code."""
    def __init__(self, code):
        self.code = code


def _fake_exit(code=0):
    """Replacement for sys.exit() during test execution."""
    raise _ExitInterceptor(code)


def load_manifest():
    with open(MANIFEST_PATH, "r") as f:
        return json.load(f)


def run_test(entry, fail_fast=False):
    """Run a single test entry from the manifest.

    Returns (name, passed, duration, category, detail).
    """
    name = entry["name"]
    module_name = entry["module"]
    callable_name = entry.get("callable")  # may be None
    category = entry["category"]
    accepts_workspace = entry.get("accepts_workspace", False)
    returns_exit_code = entry.get("returns_exit_code", False)
    signal = entry.get("signal", "mixed")

    start = time.time()
    workspace = None
    detail = ""
    passed = False

    # For tests that read workspace from sys.argv (not function args)
    workspace_via_argv = False
    if accepts_workspace and callable_name is None and signal == "sys_exit":
        # cold_start_reconstruction, audit_integrity — main() reads sys.argv[1]
        workspace_via_argv = True

    try:
        # Create isolated workspace for tests that need one
        if accepts_workspace:
            workspace = tempfile.mkdtemp(prefix=f"overcr-{name}-")

        # For tests that read workspace via sys.argv, inject it
        if workspace_via_argv and workspace:
            original_argv = sys.argv[:]
            sys.argv = [sys.argv[0], workspace]
        elif callable_name and accepts_workspace and workspace:
            # For tests where callable takes workspace as arg
            pass
        else:
            original_argv = None

        if workspace_via_argv and workspace:
            original_argv = sys.argv[:]

        # Import the test module
        mod = importlib.import_module(module_name)

        # Intercept sys.exit so tests that call it don't kill the runner
        original_exit = sys.exit
        sys.exit = _fake_exit

        try:
            if callable_name:
                fn = getattr(mod, callable_name)
                if accepts_workspace and workspace:
                    result = fn(workspace)
                else:
                    result = fn()

                if returns_exit_code:
                    passed = (result == 0)
                    if not passed:
                        detail = f"exit_code={result}"
                else:
                    # Check module-level FAILED flag
                    failed_flag = getattr(mod, "FAILED", getattr(mod, "_FAILED", None))
                    if failed_flag is not None:
                        passed = not failed_flag
                        if not passed:
                            detail = "FAILED/_FAILED flag set"
                    else:
                        # No explicit failure signal, no exception — pass
                        passed = True

            elif signal == "sys_exit":
                # Module uses main() which calls sys.exit(code)
                # May also accept workspace via sys.argv
                result = mod.main()
                # If main() returns instead of calling sys.exit():
                if result is not None and isinstance(result, int):
                    passed = (result == 0)
                    if not passed:
                        detail = f"exit_code={result}"
                else:
                    # Check global flag
                    failed_flag = getattr(mod, "FAILED", getattr(mod, "_FAILED", None))
                    if failed_flag is not None:
                        passed = not failed_flag
                        if not passed:
                            detail = "FAILED/_FAILED flag set"
                    else:
                        passed = True

            elif signal == "run_functions":
                # Explicit list of functions to run
                func_names = entry.get("functions", [])
                for fn_name in func_names:
                    fn = getattr(mod, fn_name)
                    fn()
                # No exception → pass
                passed = True

            else:
                # Fallback: run main() if it exists
                if hasattr(mod, "main"):
                    result = mod.main()
                    if result is not None and isinstance(result, int):
                        passed = (result == 0)
                        if not passed:
                            detail = f"exit_code={result}"
                    else:
                        failed_flag = getattr(mod, "FAILED", getattr(mod, "_FAILED", None))
                        if failed_flag is not None:
                            passed = not failed_flag
                            if not passed:
                                detail = "FAILED/_FAILED flag set"
                        else:
                            passed = True
                else:
                    passed = True

        except _ExitInterceptor as e:
            # Test called sys.exit(code)
            passed = (e.code == 0)
            if not passed:
                detail = f"sys.exit({e.code})"

        finally:
            # Restore sys.exit
            sys.exit = original_exit
            # Restore sys.argv if we modified it
            if workspace_via_argv:
                sys.argv = original_argv

    except Exception as e:
        passed = False
        detail = f"exception: {type(e).__name__}: {e}"

    finally:
        # Clean up workspace
        if workspace and os.path.exists(workspace):
            import shutil
            try:
                shutil.rmtree(workspace, ignore_errors=True)
            except Exception:
                pass

    duration = time.time() - start
    return (name, passed, duration, category, detail)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="OverCR v0.7.0 Consolidated Test Suite")
    parser.add_argument("--fail-fast", action="store_true", help="Stop on first failure")
    parser.add_argument("--category", type=str, default=None, help="Run only tests in this category")
    parser.add_argument("--test", type=str, default=None, help="Run a single test by name")
    args = parser.parse_args()

    manifest = load_manifest()
    entries = manifest["tests"]

    # Filter by category or test name
    if args.category:
        entries = [e for e in entries if e["category"] == args.category]
    if args.test:
        entries = [e for e in entries if e["name"] == args.test]

    if not entries:
        print("No matching tests found.")
        sys.exit(1)

    print("=" * 72)
    print(f"OverCR v{manifest['version']} Consolidated Test Suite")
    print(f"OVERCR_ROOT: {OVERCR_ROOT}")
    print(f"Tests to run: {len(entries)}")
    print("=" * 72)
    print()

    results = []
    any_failed = False

    for entry in entries:
        name, passed, duration, category, detail = run_test(entry, fail_fast=args.fail_fast)
        status = "PASS" if passed else "FAIL"
        results.append((name, passed, duration, category, detail))

        print(f"  [{status}] {name} ({category}) — {duration:.2f}s")
        if detail and not passed:
            print(f"         {detail}")

        if not passed:
            any_failed = True
            if args.fail_fast:
                print("\n  --fail-fast: stopping after first failure")
                break

    # Summary table
    print()
    print("=" * 72)
    print("Test Suite Summary")
    print("=" * 72)
    print()
    print(f"  {'Name':<35} {'Category':<12} {'Status':<6} {'Time':>7}")
    print(f"  {'-'*35} {'-'*12} {'-'*6} {'-'*7}")

    total_duration = 0.0
    pass_count = 0
    fail_count = 0

    for name, passed, duration, category, detail in results:
        status = "PASS" if passed else "FAIL"
        print(f"  {name:<35} {category:<12} {status:<6} {duration:>6.2f}s")
        total_duration += duration
        if passed:
            pass_count += 1
        else:
            fail_count += 1

    print(f"  {'-'*35} {'-'*12} {'-'*6} {'-'*7}")
    print(f"  {'TOTAL':<35} {'':12} {pass_count}/{pass_count+fail_count:<5} {total_duration:>6.2f}s")
    print()

    if any_failed:
        print(f"  FAILED: {fail_count} test(s) failed")
        print()
        for name, passed, duration, category, detail in results:
            if not passed:
                print(f"  - {name}: {detail}")
        print()
        sys.exit(1)
    else:
        print(f"  ALL PASSED: {pass_count} test(s) passed in {total_duration:.2f}s")
        print()
        sys.exit(0)


if __name__ == "__main__":
    main()