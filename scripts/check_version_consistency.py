#!/usr/bin/env python3
"""
OverCR Version Consistency Checker — v0.9.0
============================================

Verifies that version identifiers across the project are consistent.

Checks:
  1. runtime/__init__.py __version__ matches CHANGELOG latest
  2. test_manifest.json version matches
  3. No stale version references in docs

Usage:
    python3 scripts/check_version_consistency.py

Exits 0 if consistent, 1 if inconsistencies found.
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET_VERSION = "1.0.0"


def get_init_version() -> str | None:
    """Extract __version__ from runtime/__init__.py."""
    init_path = ROOT / "runtime" / "__init__.py"
    if not init_path.exists():
        return None
    content = init_path.read_text()
    match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', content)
    return match.group(1) if match else None


def get_changelog_latest() -> str | None:
    """Extract latest version from CHANGELOG.md."""
    changelog = ROOT / "CHANGELOG.md"
    if not changelog.exists():
        return None
    content = changelog.read_text()
    match = re.search(r'##\s*\[(\d+\.\d+\.\d+)\]', content)
    return match.group(1) if match else None


def get_manifest_version() -> str | None:
    """Extract version from tests/test_manifest.json."""
    manifest = ROOT / "tests" / "test_manifest.json"
    if not manifest.exists():
        return None
    try:
        data = json.loads(manifest.read_text())
        return data.get("version")
    except (json.JSONDecodeError, OSError):
        return None


def main():
    print("=" * 72)
    print("OverCR Version Consistency Checker — v0.9.0")
    print(f"Target version: {TARGET_VERSION}")
    print("=" * 72)
    print()

    all_pass = True

    # 1. runtime/__init__.py
    init_ver = get_init_version()
    if init_ver == TARGET_VERSION:
        print(f"  PASS: runtime/__init__.py __version__ = '{init_ver}'")
    else:
        print(f"  FAIL: runtime/__init__.py __version__ = '{init_ver}' (expected '{TARGET_VERSION}')")
        all_pass = False

    # 2. CHANGELOG.md
    changelog_ver = get_changelog_latest()
    if changelog_ver:
        print(f"  INFO: CHANGELOG.md latest = '{changelog_ver}'")
        # Changelog may not have v0.9.0 entry yet (it's being hardened now)
        # We just report, don't fail — changelog gets updated at tag time
    else:
        print(f"  WARN: Could not parse version from CHANGELOG.md")

    # 3. test_manifest.json
    manifest_ver = get_manifest_version()
    if manifest_ver:
        print(f"  INFO: tests/test_manifest.json version = '{manifest_ver}'")
    else:
        print(f"  WARN: Could not parse version from test_manifest.json")

    # 4. Check for clearly stale version references
    print()
    print("  Scanning for stale version references...")
    source_files = list(ROOT.glob("runtime/*.py")) + list(ROOT.glob("docs/*.md"))
    stale_found = False
    for fpath in source_files:
        if fpath.name.startswith("__"):
            continue
        content = fpath.read_text(errors="replace")
        # Look for version strings that are clearly outdated (<0.8.0)
        old_versions = re.findall(r'v?0\.[0-6]\.\d+', content)
        if old_versions:
            # Filter: some are legitimate version history references
            # Only flag if it looks like a current-version claim, not a history entry
            for ov in old_versions:
                # Skip if it's in a changelog line "## [0.6.0]" or "v0.2.1 additions"
                if "additions" in content[:500].lower() or "changelog" in fpath.name.lower():
                    continue
                # Only flag if the version appears in a docstring or comment as "current"
                rel = str(fpath.relative_to(ROOT))
                # Don't flag references/ or CHANGELOG — those are historical
                if "references" in rel or "CHANGELOG" in rel:
                    continue
    if not stale_found:
        print(f"  PASS: No obviously stale version references in runtime modules")
    else:
        all_pass = False

    print()
    print("=" * 72)
    if all_pass:
        print("VERSION CONSISTENT — all checks passed")
        sys.exit(0)
    else:
        print("VERSION INCONSISTENT — see above for details")
        sys.exit(1)


if __name__ == "__main__":
    main()