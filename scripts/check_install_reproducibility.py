#!/usr/bin/env python3
"""
OverCR v2.10.0 — Install Reproducibility Check

Validates clean extraction from the release archive and
verifies the installation process is reproducible.

Usage:
    python3 scripts/check_install_reproducibility.py

Exits 0 if install validates, 1 if issues found.
"""

import sys, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from release import InstallValidator


def main():
    print("=" * 72)
    print("OverCR v2.10.0 — Install Reproducibility Check")
    print("=" * 72)
    print()

    print("  Phase 1: Environment validation...")
    validator = InstallValidator(str(ROOT))
    env_report = validator.validate_environment()
    for r in env_report.results:
        if r["status"] != "PASS":
            print(f"    [{r['status']}] {r['check']}: {r.get('detail', '')}")

    print()
    print("  Phase 2: Clean extraction simulation...")
    extract_report = validator.validate_clean_extraction()
    p = sum(1 for r in extract_report.results if r["status"] == "PASS")
    f = sum(1 for r in extract_report.results if r["status"] == "FAIL")
    w = sum(1 for r in extract_report.results if r["status"] == "WARN")
    print(f"  Extraction: {p} PASS, {f} FAIL, {w} WARN")

    for r in extract_report.results:
        if r["status"] == "FAIL":
            print(f"    [FAIL] {r['check']}: {r.get('detail', '')}")
        elif r["status"] == "WARN":
            print(f"    [WARN] {r['check']}: {r.get('detail', '')}")

    # Save report
    report_path = ROOT / "runtime" / "install_validation_report_v2.10.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    combined = {
        "environment": env_report.to_dict(),
        "extraction": extract_report.to_dict(),
    }
    report_path.write_text(json.dumps(combined, indent=2))
    print(f"\n  Report saved to: {report_path}")

    if env_report.passed and extract_report.passed:
        print("\n  INSTALL REPRODUCIBILITY: PASSED\n")
        return 0
    else:
        print("\n  INSTALL REPRODUCIBILITY: FAILED\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
