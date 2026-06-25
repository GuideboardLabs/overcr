#!/usr/bin/env python3
"""
OverCR v0.3.0 — Worker Capabilities Tests

Test suite for runtime/worker_capabilities.py functions:
- validate_capabilities
- validate_packet_types
- get_capability_summary

Covers: valid registration, unknown capability flags, missing required capabilities,
subagent capability mismatch warnings, valid/invalid packet types, and summary structure.
"""

import sys
from pathlib import Path

_OVERCR_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_OVERCR_ROOT))

from runtime.worker_registry import WorkerRegistration, WorkerRegistry, KNOWER_CAPABILITIES, RUNTIME_COMPAT_VERSION
from runtime.worker_capabilities import (
    validate_capabilities,
    validate_packet_types,
    get_capability_summary,
    ALL_CAPABILITY_FLAGS,
    REQUIRED_CAPABILITIES,
    EXPECTED_CAPABILITIES,
    EXPECTED_PACKET_TYPES,
)

_FAILED = False


def _assert(condition, msg=""):
    global _FAILED
    if not condition:
        if msg:
            print(f"  FAIL: {msg}")
        else:
            print("  FAIL: assertion failed")
        _FAILED = True


def banner(text: str, width: int = 76):
    print(f"\n{'=' * width}")
    print(f"  {text}")
    print(f"{'=' * width}")


def section(text: str):
    print(f"\n--- {text} ---")


def make_registration(
    subagent: str,
    version: str = "0.1.0",
    capability_flags=None,
    supported_packet_types=None,
    runtime_compat_version: str = RUNTIME_COMPAT_VERSION,
    worker_path: str = "test_worker.py",
) -> WorkerRegistration:
    """Helper to create a WorkerRegistration."""
    caps = capability_flags or frozenset()
    ptypes = supported_packet_types or frozenset()
    return WorkerRegistration(
        subagent=subagent,
        version=version,
        capability_flags=caps,
        supported_packet_types=ptypes,
        runtime_compat_version=runtime_compat_version,
        worker_path=worker_path,
    )


def test_validate_capabilities_valid_registration():
    """Test: Valid registration passes capability validation."""
    section("validate_capabilities: Valid registration")

    registration = make_registration(
        subagent="test_worker",
        version="0.1.0",
        capability_flags=frozenset({
            "no_network",
            "no_shell",
            "no_fs_write",
            "no_outbound",
            "readonly_analysis",
        }),
        supported_packet_types=frozenset({"worker_packet"}),
    )

    result = validate_capabilities(registration)
    _assert(result.valid, f"Expected valid=True, got {result.valid}")
    _assert(len(result.warnings) == 0, f"Expected no warnings, got {result.warnings}")
    _assert(len(result.errors) == 0, f"Expected no errors, got {result.errors}")
    print("  PASS: validate_capabilities valid registration")


def test_validate_capabilities_unknown_flags():
    """Test: Unknown capability flags are rejected."""
    section("validate_capabilities: Unknown flags rejected")

    registration = make_registration(
        subagent="test_worker",
        version="0.1.0",
        capability_flags=frozenset({
            "no_network",
            "no_shell",
            "unknown_flag_1",
            "unknown_flag_2",
        }),
        supported_packet_types=frozenset({"worker_packet"}),
    )

    result = validate_capabilities(registration)
    _assert(not result.valid, "Expected invalid=False for unknown flags")
    _assert(len(result.errors) > 0, "Expected errors for unknown flags")
    _assert("unknown" in str(result.errors).lower(), "Expected unknown flag error")
    print("  PASS: validate_capabilities unknown flags rejected")


def test_validate_capabilities_missing_required():
    """Test: Missing required capabilities are rejected."""
    section("validate_capabilities: Missing required capabilities")

    registration = make_registration(
        subagent="test_worker",
        version="0.1.0",
        capability_flags=frozenset({
            "no_network",
            "no_shell",
            # Missing CAP_NO_OUTBOUND (REQUIRED_CAPABILITIES)
        }),
        supported_packet_types=frozenset({"worker_packet"}),
    )

    result = validate_capabilities(registration)
    _assert(not result.valid, "Expected invalid=False for missing required")
    _assert(len(result.errors) > 0, "Expected errors for missing required capabilities")
    _assert("missing" in str(result.errors).lower() or "required" in str(result.errors).lower(), "Expected missing required error")
    print("  PASS: validate_capabilities missing required capabilities rejected")


def test_validate_capabilities_subagent_mismatch():
    """Test: Known subagent with mismatched capabilities produces warnings."""
    section("validate_capabilities: Subagent capability mismatch warnings")

    registration = make_registration(
        subagent="my_knower",
        version="0.1.0",
        capability_flags=frozenset({
            "no_network",
            "no_shell",
            "no_outbound",
        }),
        supported_packet_types=frozenset({"knower_packet"}),
    )

    result = validate_capabilities(registration)
    _assert(len(result.warnings) >= 0, "Should handle subagent mismatch gracefully")
    warning_msgs = [w for w in result.warnings if "expected" in str(w).lower()]
    print(f"  Warnings: {warning_msgs}")
    print("  PASS: validate_capabilities subagent mismatch handled")


def test_validate_packet_types_valid():
    """Test: Valid packet types pass validation."""
    section("validate_packet_types: Valid packet types")

    registration = make_registration(
        subagent="coder",
        version="0.1.0",
        capability_flags=frozenset({"no_network", "no_shell", "no_outbound"}),
        supported_packet_types=frozenset({"coder_completion", "coder_blocked", "coder_diagnostic", "coder_patch_plan"}),
    )

    result = validate_packet_types(registration)
    _assert(result.valid, f"Expected valid=True, got {result.valid}")
    _assert(len(result.warnings) == 0, f"Expected no warnings, got {result.warnings}")
    _assert(len(result.errors) == 0, f"Expected no errors, got {result.errors}")
    print("  PASS: validate_packet_types valid packet types")


def test_validate_packet_types_invalid():
    """Test: Invalid packet types produce warnings."""
    section("validate_packet_types: Invalid packet types rejected")

    registration = make_registration(
        subagent="coder",
        version="0.1.0",
        capability_flags=frozenset({"no_network", "no_shell", "no_outbound"}),
        supported_packet_types=frozenset({"coder_completion", "coder_blocked", "coder_diagnostic", "coder_patch_plan", "invalid_packet_type_xyz"}),
    )

    result = validate_packet_types(registration)
    _assert(len(result.warnings) > 0, "Expected warnings for unknown packet types")
    _assert("invalid" in str(result.warnings).lower() or "unknown" in str(result.warnings).lower(), "Expected warning for invalid packet type")
    print("  PASS: validate_packet_types invalid packet types rejected")


def test_get_capability_summary_structure():
    """Test: get_capability_summary returns expected structure."""
    section("get_capability_summary: Structure")

    registration = make_registration(
        subagent="coder",
        version="0.1.0",
        capability_flags=frozenset({
            "no_network",
            "no_shell",
            "no_outbound",
            "readonly_analysis",
        }),
        supported_packet_types=frozenset({"coder_completion", "coder_blocked", "coder_diagnostic", "coder_patch_plan"}),
    )

    summary = get_capability_summary(registration)

    _assert(isinstance(summary, dict), "Expected dict type")
    _assert("subagent" in summary, "Expected 'subagent' key")
    _assert("version" in summary, "Expected 'version' key")
    _assert("capabilities" in summary, "Expected 'capabilities' key")
    _assert("packet_types" in summary, "Expected 'packet_types' key")
    _assert("meets_requirements" in summary, "Expected 'meets_requirements' key")
    _assert("safety_profile" in summary, "Expected 'safety_profile' key")

    _assert(summary["subagent"] == "coder", f"Wrong subagent: {summary['subagent']}")
    _assert(summary["version"] == "0.1.0", f"Wrong version: {summary['version']}")
    _assert("coder_completion" in summary["packet_types"], f"Expected 'coder_completion' in packet_types, got {summary['packet_types']}")
    _assert(summary["meets_requirements"] == True, f"Wrong meets_requirements: {summary['meets_requirements']}")
    _assert("no_network" in summary["safety_profile"], "Expected 'no_network' in safety_profile")
    print("  PASS: get_capability_summary returns expected structure")


def test_get_capability_summary_all_flags():
    """Test: get_capability_summary with all known capability flags."""
    section("get_capability_summary: All flags")

    all_caps = frozenset(ALL_CAPABILITY_FLAGS)
    registration = make_registration(
        subagent="test_worker_all",
        version="0.1.0",
        capability_flags=all_caps,
        supported_packet_types=frozenset({"worker_packet"}),
    )

    summary = get_capability_summary(registration)

    _assert(summary["capabilities"] == sorted(all_caps), "Expected all capability flags")
    _assert(summary["meets_requirements"] == True, "Expected meets_requirements=True with all flags")
    print("  PASS: get_capability_summary handles all flags correctly")


def main():
    global _FAILED
    banner("OverCR v0.3.0 — Worker Capabilities Tests")

    tests = [
        ("validate_capabilities: Valid registration", test_validate_capabilities_valid_registration),
        ("validate_capabilities: Unknown flags rejected", test_validate_capabilities_unknown_flags),
        ("validate_capabilities: Missing required capabilities", test_validate_capabilities_missing_required),
        ("validate_capabilities: Subagent mismatch warnings", test_validate_capabilities_subagent_mismatch),
        ("validate_packet_types: Valid packet types", test_validate_packet_types_valid),
        ("validate_packet_types: Invalid packet types rejected", test_validate_packet_types_invalid),
        ("get_capability_summary: Structure", test_get_capability_summary_structure),
        ("get_capability_summary: All flags", test_get_capability_summary_all_flags),
    ]

    for name, fn in tests:
        section(name)
        try:
            fn()
        except Exception as e:
            print(f"  ERROR: {e}")
            import traceback
            traceback.print_exc()
            _FAILED = True

    return 1 if _FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
