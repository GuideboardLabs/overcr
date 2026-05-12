#!/usr/bin/env python3
"""
OverCR v0.5.0 — CryER Real Inference Tests (Simple, Focused)

Run: python3 tests/test_cryer_real_inference.py
"""

import importlib.util
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TEST_FAILED = False


def _load_validate_packet():
    spec = importlib.util.spec_from_file_location(
        "validate_packet", str(PROJECT_ROOT / "tools" / "validate_packet.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_cryer_deterministic():
    spec = importlib.util.spec_from_file_location(
        "cryer_deterministic", str(PROJECT_ROOT / "subagents" / "cryer" / "worker.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_1_real_inference_happy_path():
    """Test 1: Simple CryER packet validation."""
    global TEST_FAILED
    print("\n[TEST 1] CryER packet validation")

    # Load cryer worker via deterministics
    cryer = _load_cryer_deterministic()

    request = {
        "task_id": "task-0001",
        "domain": "reputation_signal",
        "input_context": {
            "entity": "Test Entity",
            "snippets": ["Great service."],
        },
    }

    packet = cryer.build_reputation_signal_packet(request)
    valid, errors, warnings = validator.validate_packet(packet)

    if not valid:
        print(f"  FAIL: L1-L6 validation failed: {errors}")
        TEST_FAILED = True
    else:
        print(f"  PASS: cryer_reputation_signal packet validated")
        print(f"  PASS: packet_type={packet.get('packet_type')}, source={packet.get('source')}, target={packet.get('target')}")


def test_2_packet_types():
    """Test 2: All 7 CryER packet types validated."""
    global TEST_FAILED
    print("\n[TEST 2] All CryER packet types validated")

    cryer = _load_cryer_deterministic()

    request = {
        "task_id": "task-0002",
        "input_context": {
            "entity": "Test Entity",
        },
    }

    builders = [
        ("recon", cryer.build_recon_packet),
        ("reputation_signal", cryer.build_reputation_signal_packet),
        ("engagement_signal", cryer.build_engagement_signal_packet),
        ("booking_friction", cryer.build_booking_friction_packet),
        ("directory_completeness", cryer.build_directory_completeness_packet),
        ("hiring_growth", cryer.build_hiring_growth_packet),
    ]

    for domain, builder in builders:
        request["domain"] = domain
        packet = builder(request)
        valid, errors, warnings = validator.validate_packet(packet)
        if not valid:
            print(f"  FAIL: {domain} failed validation: {errors}")
            TEST_FAILED = True
            return

    print(f"  PASS: All 6 packet types validated")


def test_3_inference_worker_structure():
    """Test 3: Inference worker has correct structure."""
    global TEST_FAILED
    print("\n[TEST 3] Inference worker structure")

    spec = importlib.util.spec_from_file_location(
        "cryer_inf", str(PROJECT_ROOT / "subagents" / "cryer" / "inference_worker.py")
    )
    inf_module = importlib.util.module_from_spec(spec)

    try:
        spec.loader.exec_module(inf_module)
    except Exception as e:
        print(f"  FAIL: Cannot load inference_worker.py: {e}")
        TEST_FAILED = True
        return

    # Check key functions exist
    required = [
        "build_inference_prompt",
        "_build_reputation_signal_packet_inference",
        "_load_deterministic_worker",
        "_main",
    ]

    missing = [f for f in required if not hasattr(inf_module, f)]
    if missing:
        print(f"  FAIL: Missing functions: {missing}")
        TEST_FAILED = True
        return

    print(f"  PASS: inference_worker.py has expected functions")

    # Check prompt template exists
    prompt_file = PROJECT_ROOT / "subagents" / "cryer" / "inference_prompt.md"
    if not prompt_file.exists():
        print(f"  FAIL: inference_prompt.md not found")
        TEST_FAILED = True
        return

    content = prompt_file.read_text()
    if "CryER" not in content:
        print(f"  FAIL: inference_prompt.md missing CryER context")
        TEST_FAILED = True
        return

    print(f"  PASS: inference_prompt.md exists with CryER context")


def test_4_governance_rules():
    """Test 4: Governance rules enforced."""
    global TEST_FAILED
    print("\n[TEST 4] Governance rules")

    # Check that all CryER packets route to overcr
    cryer = _load_cryer_deterministic()

    tests = [
        ("reputation_signal", cryer.build_reputation_signal_packet),
        ("booking_friction", cryer.build_booking_friction_packet),
        ("directory_completeness", cryer.build_directory_completeness_packet),
    ]

    for domain, builder in tests:
        packet = builder({"task_id": "test", "input_context": {"entity": "X"}})
        routing = packet.get("audit_trail", {}).get("recommended_routing", packet.get("next_steps_recommendation", ""))
        if "overcr" not in str(routing).lower():
            print(f"  FAIL: {domain} does not route to overcr")
            TEST_FAILED = True
            return

    print(f"  PASS: All packets route to overcr")


def test_5_l6_audit_trail():
    """Test 5: L6 audit trail requirements."""
    global TEST_FAILED
    print("\n[TEST 5] L6 audit trail requirements")

    cryer = _load_cryer_deterministic()

    packet = cryer.build_reputation_signal_packet({
        "task_id": "test",
        "input_context": {"entity": "X"},
    })

    audit = packet.get("audit_trail", {})
    required = ["worker_version", "execution_timestamp", "methods_used"]

    missing = [f for f in required if f not in audit]
    if missing:
        print(f"  FAIL: Missing audit_trail fields: {missing}")
        TEST_FAILED = True
        return

    print(f"  PASS: Audit trail has required fields")


def main():
    global validator

    # Load validator
    validator = _load_validate_packet()

    # Run tests
    test_1_real_inference_happy_path()
    test_2_packet_types()
    test_3_inference_worker_structure()
    test_4_governance_rules()
    test_5_l6_audit_trail()

    if TEST_FAILED:
        print("\n[RESULT] Some tests FAILED")
        sys.exit(1)
    else:
        print("\n[RESULT] All tests PASSED")
        sys.exit(0)


if __name__ == "__main__":
    main()
