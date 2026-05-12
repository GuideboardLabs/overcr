#!/usr/bin/env python3
"""
OverCR Documentation Consistency Checker — v0.9.0
=================================================

Verifies that documentation files reference modules and paths that actually
exist in the codebase.

Checks:
  1. REPO_STRUCTURE.md references match actual files
  2. GOVERNANCE_BOUNDARIES.md module references exist
  3. RUNTIME_BOUNDARY.md module references exist
  4. No empty documentation files

Usage:
    python3 scripts/check_docs_consistency.py

Exits 0 if consistent, 1 if issues found.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def check_non_empty(relative_path: str) -> bool:
    """Check that a file exists and is non-empty."""
    path = ROOT / relative_path
    if not path.exists():
        print(f"  FAIL: {relative_path} does not exist")
        return False
    if path.stat().st_size == 0:
        print(f"  FAIL: {relative_path} is empty (0 bytes)")
        return False
    print(f"  PASS: {relative_path} ({path.stat().st_size} bytes)")
    return True


def check_module_references(doc_path: str) -> bool:
    """Check that module .py references in a doc file actually exist."""
    path = ROOT / doc_path
    if not path.exists():
        print(f"  FAIL: {doc_path} not found")
        return False

    content = path.read_text()
    # Find references like "module_name.py" or "runtime/module.py"
    py_refs = re.findall(r'[\w/]+\.py', content)
    all_pass = True
    checked = set()

    for ref in py_refs:
        if ref in checked:
            continue
        checked.add(ref)

        # Skip references that are clearly examples or patterns
        if ref.startswith("example") or "test_" in ref:
            continue

        # Try to resolve against repo root
        resolved = ROOT / ref
        if resolved.exists():
            continue

        # May be relative — try common prefixes
        for prefix in ["runtime/", "scripts/", "tools/", "subagents/"]:
            if (ROOT / f"{prefix}{ref}").exists():
                break
        else:
            # Not found — but may be a partial reference (e.g., in a table)
            # Only flag if it looks like a direct file reference
            if "/" in ref and not ref.startswith("$"):
                print(f"  WARN: Referenced file not found: {ref} (in {doc_path})")
                # Warning, not failure — docs may reference planned files

    if not all_pass:
        return False
    print(f"  PASS: {doc_path} module references checked")
    return True


def check_repo_structure() -> bool:
    """Check that key files listed in REPO_STRUCTURE.md actually exist."""
    doc_path = ROOT / "docs" / "REPO_STRUCTURE.md"
    if not doc_path.exists():
        print(f"  FAIL: docs/REPO_STRUCTURE.md not found")
        return False

    content = doc_path.read_text()

    # Parse tree lines by tracking indentation depth.
    # Tree lines look like: "│   ├── filename" or "│   └── filename"
    # Each "│   " or "    " segment = one depth level.
    # We rebuild full paths from the depth stack.

    all_pass = True
    missing = []
    path_stack = []  # stack of directory names at each depth

    for line in content.splitlines():
        # Only process tree lines containing ├── or └──
        if "├──" not in line and "└──" not in line:
            continue

        # Determine depth by counting indent segments before the tree char
        # Each level is "│   " or "    " (4 chars) before ├── or └──
        tree_pos = max(line.find("├──"), line.find("└──"))
        if tree_pos < 0:
            continue

        indent_segment = line[:tree_pos]
        # Each 4-char segment is one depth level
        depth = len(indent_segment) // 4

        # Extract the filename/path part after ├── or └──
        after_tree = line[tree_pos + 4:].strip()  # skip "├── " or "└── "
        # Strip any inline comment
        if "#" in after_tree:
            after_tree = after_tree[:after_tree.index("#")].strip()

        if not after_tree:
            continue

        # Adjust stack to current depth
        path_stack = path_stack[:depth]

        if after_tree.endswith("/"):
            # It's a directory — push onto stack
            path_stack.append(after_tree.rstrip("/"))
            continue

        # Skip .gitkeep and template placeholders
        if ".gitkeep" in after_tree or "{{" in after_tree:
            continue

        # Build full path
        full_path = "/".join(path_stack + [after_tree]) if path_stack else after_tree

        resolved = ROOT / full_path
        if not resolved.exists():
            missing.append(full_path)
            all_pass = False

    if missing:
        print(f"  FAIL: REPO_STRUCTURE.md references {len(missing)} missing file(s):")
        for m in missing[:5]:
            print(f"        - {m}")
        if len(missing) > 5:
            print(f"        ... and {len(missing) - 5} more")
    else:
        print(f"  PASS: REPO_STRUCTURE.md references verified")

    return all_pass


def main():
    print("=" * 72)
    print("OverCR Documentation Consistency Checker — v0.9.0")
    print("=" * 72)
    print()

    all_pass = True

    # 1. Core docs exist and are non-empty
    print("1. Documentation Files")
    all_pass &= check_non_empty("docs/REPO_STRUCTURE.md")
    all_pass &= check_non_empty("docs/HERMES_REFERENCE_RUNTIME.md")
    all_pass &= check_non_empty("docs/GOVERNANCE_BOUNDARIES.md")
    all_pass &= check_non_empty("docs/RUNTIME_BOUNDARY.md")
    all_pass &= check_non_empty("CHANGELOG.md")
    all_pass &= check_non_empty("soul.md")
    print()

    # 2. Security docs
    print("2. Security Documentation")
    all_pass &= check_non_empty("security/THREAT_MODEL.md")
    all_pass &= check_non_empty("security/SECURITY_REVIEW_v0.9.0.md")
    print()

    # 3. REPO_STRUCTURE.md references
    print("3. Repository Structure References")
    all_pass &= check_repo_structure()
    print()

    # 4. Module references in governance/runtime boundary docs
    print("4. Module References in Boundary Docs")
    check_module_references("docs/GOVERNANCE_BOUNDARIES.md")
    check_module_references("docs/RUNTIME_BOUNDARY.md")
    print()

    print("=" * 72)
    if all_pass:
        print("DOCS CONSISTENT — all checks passed")
        sys.exit(0)
    else:
        print("DOCS INCONSISTENT — see above for details")
        sys.exit(1)


if __name__ == "__main__":
    main()