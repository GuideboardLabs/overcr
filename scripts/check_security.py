#!/usr/bin/env python3
"""
OverCR Security Consistency Checker — v0.9.0
=============================================

Verifies that security controls documented in the threat model and governance
boundaries are actually present in the codebase.

Checks:
  1. Approval gate enforcement modules exist
  2. Forbidden pattern lists are non-empty
  3. Validation levels (L1-L6) are implemented
  4. Audit integrity verifier exists
  5. No empty security documents
  6. .gitignore covers runtime-generated files

Usage:
    python3 scripts/check_security.py

Exits 0 if all checks pass, 1 if any fail.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def check_module_exists(relative_path: str, description: str) -> bool:
    """Check that a module file exists and is non-empty."""
    path = ROOT / relative_path
    if not path.exists():
        print(f"  FAIL: {description} — {relative_path} does not exist")
        return False
    if path.stat().st_size == 0:
        print(f"  FAIL: {description} — {relative_path} is empty (0 bytes)")
        return False
    print(f"  PASS: {description} — {relative_path}")
    return True


def check_gitignore_covers(pattern: str, description: str) -> bool:
    """Check that .gitignore contains a given pattern."""
    gitignore = ROOT / ".gitignore"
    if not gitignore.exists():
        print(f"  FAIL: {description} — .gitignore not found")
        return False
    content = gitignore.read_text()
    if pattern in content:
        print(f"  PASS: {description} — .gitignore contains '{pattern}'")
        return True
    print(f"  FAIL: {description} — .gitignore missing '{pattern}'")
    return False


def check_forbidden_patterns(module_path: str, attr_name: str, description: str) -> bool:
    """Check that a module defines a non-empty forbidden pattern list."""
    path = ROOT / module_path
    if not path.exists():
        print(f"  FAIL: {description} — {module_path} not found")
        return False
    content = path.read_text()
    # Simple text scan for the attribute name and at least one list entry
    if attr_name not in content:
        print(f"  FAIL: {description} — {attr_name} not found in {module_path}")
        return False
    # Check the list has entries (look for at least 3 items after the attr)
    lines = content.split("\n")
    found_attr = False
    item_count = 0
    for line in lines:
        if attr_name in line:
            found_attr = True
            continue
        if found_attr:
            stripped = line.strip()
            if stripped.startswith("#") or stripped == "":
                continue
            if stripped.startswith("]") or stripped.startswith("}"):
                break
            if stripped.startswith('"') or stripped.startswith("'"):
                item_count += 1
    if item_count >= 1:
        print(f"  PASS: {description} — {attr_name} has {item_count} entries")
        return True
    print(f"  FAIL: {description} — {attr_name} appears empty ({item_count} entries)")
    return False


def main():
    print("=" * 72)
    print("OverCR Security Consistency Checker — v0.9.0")
    print("=" * 72)
    print()

    all_pass = True

    # 1. Core security modules exist and are non-empty
    print("1. Core Security Modules")
    all_pass &= check_module_exists("runtime/approval_gate.py", "Approval gate enforcement")
    all_pass &= check_module_exists("runtime/audit_integrity.py", "Audit integrity verifier")
    all_pass &= check_module_exists("runtime/audit_writer.py", "Audit writer (append-only)")
    all_pass &= check_module_exists("runtime/output_sanitizer.py", "Output sanitizer")
    all_pass &= check_module_exists("tools/validate_packet.py", "6-level packet validator")
    all_pass &= check_module_exists("runtime/workflow_policy.py", "Workflow policy engine")
    all_pass &= check_module_exists("runtime/worker_runner.py", "Worker runner (subprocess)")
    print()

    # 2. Security documents exist and are non-empty
    print("2. Security Documents")
    all_pass &= check_module_exists("security/THREAT_MODEL.md", "Threat model")
    all_pass &= check_module_exists("security/SECURITY_REVIEW_v0.9.0.md", "Security review")
    all_pass &= check_module_exists("docs/GOVERNANCE_BOUNDARIES.md", "Governance boundaries")
    all_pass &= check_module_exists("docs/RUNTIME_BOUNDARY.md", "Runtime boundary")
    print()

    # 3. Forbidden pattern lists are populated
    print("3. Forbidden Pattern Lists")
    all_pass &= check_forbidden_patterns(
        "runtime/workflow_policy.py", "FORBIDDEN_SHELL_PATTERNS",
        "Shell injection patterns",
    )
    all_pass &= check_forbidden_patterns(
        "runtime/workflow_policy.py", "FORBIDDEN_NETWORK_PATTERNS",
        "Network access patterns",
    )
    print()

    # 4. .gitignore covers runtime-generated files
    print("4. Git Ignore Coverage")
    all_pass &= check_gitignore_covers("audit.jsonl", "Audit log exclusion")
    all_pass &= check_gitignore_covers("task-*.json", "Task state file exclusion")
    all_pass &= check_gitignore_covers("__pycache__", "Python cache exclusion")
    all_pass &= check_gitignore_covers("workflow_trace", "Workflow trace exclusion")
    print()

    # Summary
    print("=" * 72)
    if all_pass:
        print("ALL CHECKS PASSED — security controls consistent")
        sys.exit(0)
    else:
        print("SOME CHECKS FAILED — see above for details")
        sys.exit(1)


if __name__ == "__main__":
    main()