#!/usr/bin/env python3
"""
OverCR v2.9.0 — Schema Consistency Check

Verifies all schemas are present, parseable, and have valid
referential integrity.

Usage:
    python3 scripts/check_schema_consistency.py

Exits 0 if all pass, 1 if any failures.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from integration import SchemaRegistry

def main():
    print("=" * 72)
    print("OverCR v2.9.0 — Schema Consistency Check")
    print("=" * 72)
    print()

    registry = SchemaRegistry(str(ROOT))
    registry.discover_all()

    # List all schemas
    print("  Known schemas:")
    for s in registry.list_schemas():
        exists = "EXISTS" if s["exists"] else "MISSING"
        print(f"    [{exists}] {s['schema_id']:30s} v{s['version']:6s}  {s['schema_type']}")
    print()

    # Check completeness
    valid, errors = registry.validate_schema_completeness()
    if valid:
        print("  Schema completeness: PASSED")
    else:
        print("  Schema completeness: FAILED")
        for e in errors:
            print(f"    - {e}")

    # Check referential integrity
    valid2, ref_errors = registry.verify_referential_integrity()
    if valid2:
        print("  Referential integrity: PASSED")
    else:
        print("  Referential integrity: FAILED")
        for e in ref_errors:
            print(f"    - {e}")

    print()

    all_errors = errors + ref_errors
    if not all_errors:
        print("  SCHEMA CONSISTENCY: PASSED")
        print()
        return 0
    else:
        print(f"  SCHEMA CONSISTENCY: FAILED ({len(all_errors)} issues)")
        print()
        return 1


if __name__ == "__main__":
    sys.exit(main())
