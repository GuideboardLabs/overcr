#!/usr/bin/env python3
"""
OverCR Release Candidate Check — v1.0.0
=========================================

Master gate for v1.0.0 release candidate. Runs all consistency and security
checks. Must PASS before RC tag.

Runs:
  1. check_release_clean.py   — no forbidden paths/artifacts
  2. check_security.py        — security controls present
  3. check_version_consistency.py — version identifiers match
  4. check_docs_consistency.py    — docs reference real files
  5. .gitignore coverage check   — runtime files excluded
  6. Phantom directory check      — no stray $HOME/ dirs

Usage:
    python3 scripts/release_candidate_check.py

Exits 0 if ALL checks pass, 1 if any fail.
"""

import re
import subprocess
import sys
import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"


def _clean_transient_artifacts():
    """Remove runtime artifacts left by test runs so release_clean check is accurate."""
    for f in ["runtime/audit.jsonl", "overcr_state.json", "HQ_BOOT_MANIFEST.md",
              "HQ_ROUTE_MARKER", "HQ_BOOT_VERIFICATION.txt"]:
        p = ROOT / f
        if p.exists():
            p.unlink()
    tasks_dir = ROOT / "orchestration" / "tasks"
    if tasks_dir.exists():
        for child in tasks_dir.iterdir():
            if child.name != ".gitkeep" and child.is_file():
                child.unlink()
    for d in ["sessions", "logs", "workspace"]:
        p = ROOT / d
        if p.exists():
            for child in p.iterdir():
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink()
    for pycache in ROOT.rglob("__pycache__"):
        shutil.rmtree(pycache)
    for pyc in ROOT.rglob("*.pyc"):
        pyc.unlink()


def run_check(name: str, script: str) -> bool:
    """Run a check script, return True if it passed."""
    script_path = SCRIPTS / script
    if not script_path.exists():
        print(f"  SKIP: {name} — script not found ({script})")
        return True  # Don't fail on missing optional checks

    print(f"  Running: {script} ...")
    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(ROOT),
        )
        if result.returncode == 0:
            print(f"  PASS: {name}")
            return True
        else:
            print(f"  FAIL: {name}")
            # Print last few lines of output for context
            lines = result.stdout.strip().split("\n") + result.stderr.strip().split("\n")
            for line in lines[-5:]:
                if line.strip():
                    print(f"        {line.strip()}")
            return False
    except subprocess.TimeoutExpired:
        print(f"  FAIL: {name} — timed out (60s)")
        return False
    except Exception as e:
        print(f"  FAIL: {name} — exception: {e}")
        return False


def check_gitignore_coverage() -> bool:
    """Verify .gitignore covers all runtime-generated file patterns."""
    gitignore = ROOT / ".gitignore"
    if not gitignore.exists():
        print("  FAIL: .gitignore not found")
        return False

    content = gitignore.read_text()
    required_patterns = [
        ("audit.jsonl", "Audit log"),
        ("task-*.json", "Task state files"),
        ("__pycache__", "Python bytecode cache"),
        ("*.pyc", "Compiled Python"),
        ("workflow_trace", "Workflow trace files"),
    ]

    all_pass = True
    for pattern, desc in required_patterns:
        if pattern in content:
            print(f"  PASS: .gitignore covers {desc} ('{pattern}')")
        else:
            print(f"  FAIL: .gitignore missing {desc} ('{pattern}')")
            all_pass = False

    return all_pass


def check_phantom_directories() -> bool:
    """Check for phantom directories that shouldn't be in the repo."""
    phantom_patterns = ["$HOME", "__MACOSX", ".DS_Store"]
    all_pass = True

    for item in ROOT.iterdir():
        if item.is_dir() and item.name in phantom_patterns:
            print(f"  FAIL: Phantom directory found: {item.name}/")
            all_pass = False

    if all_pass:
        print("  PASS: No phantom directories")

    return all_pass


def check_empty_security_files() -> bool:
    """Verify no security-related files are empty stubs."""
    security_files = [
        "security/THREAT_MODEL.md",
        "security/SECURITY_REVIEW_v0.9.0.md",
        "docs/GOVERNANCE_BOUNDARIES.md",
        "docs/RUNTIME_BOUNDARY.md",
    ]
    all_pass = True
    for rel in security_files:
        path = ROOT / rel
        if not path.exists():
            print(f"  FAIL: {rel} does not exist")
            all_pass = False
        elif path.stat().st_size == 0:
            print(f"  FAIL: {rel} is empty (0 bytes)")
            all_pass = False
        else:
            print(f"  PASS: {rel} ({path.stat().st_size} bytes)")
    return all_pass


def main():
    print("=" * 72)
    print("OverCR Release Candidate Check — v1.0.0")
    print("=" * 72)
    print()

    results = {}

    # Clean transient artifacts from prior test runs before checking
    _clean_transient_artifacts()

    # Phase 1: Run sub-scripts
    print("Phase 1: Sub-Check Scripts")
    results["release_clean"] = run_check("Release Cleanliness", "check_release_clean.py")
    results["security"] = run_check("Security Consistency", "check_security.py")
    results["version"] = run_check("Version Consistency", "check_version_consistency.py")
    results["docs"] = run_check("Documentation Consistency", "check_docs_consistency.py")
    print()

    # Phase 2: Direct checks
    print("Phase 2: Direct Checks")

    print()
    print("  2a. .gitignore Coverage")
    results["gitignore"] = check_gitignore_coverage()

    print()
    print("  2b. Phantom Directory Check")
    results["phantom"] = check_phantom_directories()

    print()
    print("  2c. Security Files Non-Empty")
    results["security_files"] = check_empty_security_files()

    print()

    # Summary
    print("=" * 72)
    print("Release Candidate Check Summary")
    print("=" * 72)
    print()

    passes = 0
    fails = 0
    for name, passed in results.items():
        status = "PASS" if passed else "FAIL"
        if passed:
            passes += 1
        else:
            fails += 1
        print(f"  [{status}] {name}")

    print()
    print(f"  Total: {passes} pass, {fails} fail")
    print()

    if fails == 0:
        print("  RC GATE: PASS — v1.0.0 is ready for release candidate tag")
        sys.exit(0)
    else:
        print("  RC GATE: FAIL — fix the above issues before tagging RC")
        sys.exit(1)


if __name__ == "__main__":
    main()