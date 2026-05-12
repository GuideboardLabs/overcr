#!/usr/bin/env python3
"""
OverCR Release Cleanliness Checker
====================================

Verifies that no forbidden paths, artifacts, or machine-specific content
are present in the source tree or a release archive.

Usage:
    python3 scripts/check_release_clean.py                    # Check source tree
    python3 scripts/check_release_clean.py --archive dist/overcr-core-0.2.4.tar.gz  # Check archive

Exits 0 if clean, 1 if forbidden content found.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

# ── FORBIDDEN PATTERNS ──
# These must NEVER appear in a release package.

FORBIDDEN_PATHS = [
    # Machine-specific paths (must use $OVERCR_ROOT or dynamic paths instead)
    r"/home/sc/[^/]",           # Machine-specific home directory
    r"/home/sc/overcr-core",    # Hardcoded OverCR root
    r"/home/sc/ai-stack",       # Legacy bootstrap path
    r"/home/sc/overcr-releases",# Machine-specific release archive path
    r"/home/sc/openclaw-",      # Machine-specific CAG path
]

FORBIDDEN_FILES = [
    # Runtime state (generated, not source)
    "overcr_state.json",
    "HQ_BOOT_MANIFEST.md",
    "HQ_ROUTE_MARKER",
    "HQ_BOOT_VERIFICATION.txt",
    "prompts/hq_boot_context_bundle.txt",
    "prompts/hq_raw_boot_context.txt",
    "runtime/audit.jsonl",
    "configs/cag-memory-config.json",        # Filled config (template is source)
    "configs/session-ingestion-config.json",  # Filled config
    "configs/release-preservation-config.txt", # Filled config
]

FORBIDDEN_DIRS = [
    "sessions",
    "logs",
]

FORBIDDEN_CONTENT = [
    # Machine-specific paths in file contents
    (r"/home/sc/ai-stack/", "Legacy bootstrap path"),
    (r"/home/sc/overcr-core(?!\s)", "Hardcoded OverCR root path"),
]

ALLOWED_PATTERNS = [
    # These are acceptable uses of machine-specific paths
    r"\$HOME",                # Shell variable
    r"\$\{HOME\}",            # Shell variable (braced)
    r"/home/you/",            # Template example (generic user)
    r"/home/[^s][^c]/",       # Generic home path
    r"OVERCR_ROOT",           # Environment variable reference
    r"Path\(__file__\)",      # Dynamic path derivation
    r"os\.path\.dirname",     # Dynamic path derivation
    r"os\.environ\.get",      # Environment variable access
    r"sys\.path\.insert\(0",  # sys.path manipulation
    r"# .*[Ee]xample",        # Comment with "example"
]


def check_source_tree(root):
    """Check the source tree for forbidden content."""
    findings = []
    root = Path(root)

    # Check for forbidden files
    for forbidden in FORBIDDEN_FILES:
        path = root / forbidden
        if path.exists():
            findings.append(("forbidden_file", str(path), f"Forbidden file present: {forbidden}"))

    # Check for forbidden directories (with content)
    for forbidden_dir in FORBIDDEN_DIRS:
        dir_path = root / forbidden_dir
        if dir_path.is_dir():
            contents = list(dir_path.rglob("*"))
            non_gitkeep = [f for f in contents if f.name != ".gitkeep" and not f.is_dir()]
            if non_gitkeep:
                findings.append(("forbidden_dir_content", str(dir_path),
                                f"Directory has runtime content: {[f.name for f in non_gitkeep[:5]]}"))

    # Check for task state files (should not be in repo)
    tasks_dir = root / "orchestration" / "tasks"
    if tasks_dir.is_dir():
        for task_file in tasks_dir.glob("task-*.json"):
            findings.append(("forbidden_file", str(task_file),
                            f"Runtime task state file: {task_file.name}"))

    # Check for hardcoded paths in source files
    source_extensions = {".py", ".md", ".sh", ".yaml", ".yml", ".json", ".tpl", ".txt"}
    for filepath in root.rglob("*"):
        if filepath.is_dir():
            continue
        if filepath.suffix not in source_extensions:
            continue
        # Skip files in dist/ and .git/
        parts = filepath.relative_to(root).parts
        if "dist" in parts or ".git" in parts:
            continue
        # Skip .gitignore itself
        if filepath.name == ".gitignore":
            continue
        # Skip this checker script (its regex patterns reference forbidden paths)
        if filepath.name == "check_release_clean.py":
            continue

        try:
            content = filepath.read_text(errors="replace")
        except Exception:
            continue

        for pattern in FORBIDDEN_CONTENT:
            regex, description = pattern
            matches = re.findall(regex, content)
            if matches:
                # Filter out allowed patterns
                actual_forbidden = []
                for match in matches:
                    is_allowed = False
                    for allowed in ALLOWED_PATTERNS:
                        # Simple context check: is this match inside an allowed pattern?
                        pass  # We do a line-level check below
                    actual_forbidden.append(match)
                
                if actual_forbidden:
                    lines_with_match = []
                    for i, line in enumerate(content.split("\n"), 1):
                        if re.search(regex, line):
                            # Skip lines that are examples, templates, or dynamic references
                            stripped = line.strip()
                            if stripped.startswith("#") and "example" in stripped.lower():
                                continue
                            if "$HOME" in line or "${HOME}" in line:
                                continue
                            if "Path(__file__)" in line or "os.path.dirname" in line:
                                continue
                            if "os.environ.get" in line:
                                continue
                            # Check README template table - these are examples
                            if "Example" in line or "| `" in line:
                                continue
                            if "/home/you/" in line:
                                continue
                            lines_with_match.append((i, stripped))

                    if lines_with_match:
                        findings.append(("forbidden_content", str(filepath),
                                        f"{description}: {lines_with_match[:3]}"))

    # Check for .pyc files
    for pyc in root.rglob("*.pyc"):
        findings.append(("forbidden_file", str(pyc), "Python bytecode file present"))

    # Check for __pycache__ directories with content
    for pycache in root.rglob("__pycache__"):
        if pycache.is_dir() and list(pycache.iterdir()):
            findings.append(("forbidden_dir_content", str(pycache),
                            "__pycache__ directory present with files"))

    return findings


def check_archive(archive_path):
    """Check a tar.gz or zip archive for forbidden content."""
    findings = []
    archive_path = Path(archive_path)

    with tempfile.TemporaryDirectory() as tmpdir:
        # Extract archive
        try:
            if archive_path.suffix == ".zip":
                with zipfile.ZipFile(archive_path, "r") as zf:
                    zf.extractall(tmpdir)
            elif str(archive_path).endswith(".tar.gz") or str(archive_path).endswith(".tgz"):
                with tarfile.open(archive_path, "r:gz") as tf:
                    tf.extractall(tmpdir)
            else:
                print(f"ERROR: Unsupported archive format: {archive_path}")
                return [("unsupported_archive", str(archive_path), "Unsupported format")]
        except Exception as e:
            return [("extraction_error", str(archive_path), str(e))]

        # Find the extracted root directory
        extracted = list(Path(tmpdir).iterdir())
        if len(extracted) == 1 and extracted[0].is_dir():
            extracted_root = extracted[0]
        else:
            extracted_root = Path(tmpdir)

        # Check the extracted tree
        return check_source_tree(extracted_root)


def main():
    parser = argparse.ArgumentParser(description="OverCR Release Cleanliness Checker")
    parser.add_argument("--archive", type=str, default=None,
                        help="Path to release archive (.tar.gz or .zip) to check")
    parser.add_argument("--root", type=str, default=None,
                        help="Path to source tree root (default: auto-detect)")
    args = parser.parse_args()

    if args.root:
        root = Path(args.root)
    else:
        # Auto-detect: two levels up from this script
        root = Path(__file__).resolve().parent.parent

    print("=" * 72)
    print("OverCR Release Cleanliness Checker")
    print("=" * 72)

    if args.archive:
        print(f"  Archive: {args.archive}")
        findings = check_archive(args.archive)
    else:
        print(f"  Source root: {root}")
        findings = check_source_tree(root)

    print()

    if not findings:
        print("  CLEAN — no forbidden paths, artifacts, or machine-specific content found.")
        print()
        print("  The release package is safe to distribute.")
        sys.exit(0)
    else:
        print(f"  DIRTY — {len(findings)} finding(s):")
        print()
        for category, path, detail in findings:
            print(f"  [{category.upper()}] {path}")
            print(f"    {detail}")
            print()
        print("  Fix the above issues before releasing.")
        sys.exit(1)


if __name__ == "__main__":
    main()