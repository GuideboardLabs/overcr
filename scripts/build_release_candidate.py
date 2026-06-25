#!/usr/bin/env python3
"""
OverCR v2.10.0 — Build Release Candidate

Builds a clean release archive with SHA256 manifest and metadata.

Usage:
    python3 scripts/build_release_candidate.py

Outputs: dist/overcr-2.10.0.tar.gz + .sha256 + .meta.json
Exits 0 on success, 1 on failure.
"""

import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from release import ReleaseBuilder


def main():
    print("=" * 72)
    print("OverCR v2.10.0 — Build Release Candidate")
    print("=" * 72)
    print()

    builder = ReleaseBuilder(str(ROOT))
    build = builder.build()

    for r in build.results:
        status = r["status"]
        if status == "PASS":
            print(f"  [{status}] {r['check']}: {r.get('detail', '')}")
        else:
            print(f"  [{status}] {r['check']}: {r.get('detail', r.get('detail', ''))}")

    print()
    print(f"  Archive: {build.archive_path}")
    print(f"  Files:   {build.file_count}")
    print(f"  Size:    {build.archive_size:,} bytes")
    print(f"  SHA256:  {build.sha256}")

    # Save build report
    report_path = ROOT / "dist" / "release_build_report_v2.10.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(build.to_dict(), indent=2))
    print(f"\n  Build report saved to: {report_path}")

    if not build.errors:
        print("\n  RELEASE BUILD: SUCCESS\n")
        return 0
    else:
        print("\n  RELEASE BUILD: FAILED\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
