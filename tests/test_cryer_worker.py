#!/usr/bin/env python3
"""
OverCR CryER Worker Test — v0.4.0

Tests the CryER live worker for all 6 packet types:
1. cryer_recon — Public signal reconnaissance with yield scoring
2. cryer_reputation_signal — Reputation signal summary
3. cryer_engagement_signal — Engagement signal summary
4. cryer_booking_friction — Booking friction detection
5. cryer_directory_completeness — Directory listing completeness
6. cryer_hiring_growth — Hiring/growth signal detection

Plus: malformed input, unknown domain, governance boundary checks.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

OVERCR_ROOT = Path(__file__).resolve().parent.parent
WORKER_PATH = OVERCR_ROOT / "subagents" / "cryer" / "worker.py"

# Module-level flag for test runner signal detection
FAILED = False

# Ensure tools/ and project root are importable
if str(OVERCR_ROOT) not in sys.path:
    sys.path.insert(0, str(OVERCR_ROOT))


def invoke_worker(request: dict, timeout: float = 10.0) -> tuple[dict | None, int, str]:
    """Invoke the CryER worker subprocess and return (packet, exit_code, stderr)."""
    proc = subprocess.run(
        [sys.executable, str(WORKER_PATH)],
        input=json.dumps(request),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if proc.returncode != 0:
        return None, proc.returncode, proc.stderr
    try:
        packet = json.loads(proc.stdout)
        return packet, 0, ""
    except json.JSONDecodeError as e:
        return None, 0, f"JSON parse error: {e}"


def validate_with_runtime(packet: dict) -> tuple[bool, list[str]]:
    """Validate a packet through the 6-level validator.

    Uses importlib.util to load validate_packet directly from the tools/
    directory, avoiding package namespace issues.
    """
    import importlib.util
    validator_path = OVERCR_ROOT / "tools" / "validate_packet.py"
    spec = importlib.util.spec_from_file_location("validate_packet", validator_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    valid, errors, warnings = mod.validate_packet(packet)
    return valid, errors


# ── Phase 1: Recon ──────────────────────────────────────────────

def test_recon_basic():
    """Test basic cryer_recon packet production."""
    request = {
        "task_id": "task-0001",
        "domain": "recon",
        "instruction": "Analyze reputation for Test Corp",
        "input_context": {
            "entity": "Test Corp",
            "snippets": ["4.5 stars across 120 reviews on public listing"],
            "targets": [{
                "entity": "Test Corp",
                "type": "business",
                "yield_score": 78,
                "confidence": 85,
                "risk_flags": [],
                "raw_sources": ["provided_input"],
            }],
        },
    }
    packet, exit_code, stderr = invoke_worker(request)
    assert exit_code == 0, f"Worker exited with code {exit_code}: {stderr}"
    assert packet is not None, "Worker produced no output"
    assert packet["packet_type"] == "cryer_recon", f"Expected cryer_recon, got {packet['packet_type']}"
    assert packet["source"] == "cryer"
    assert packet["target"] == "overcr"
    assert "recon_data" in packet
    assert len(packet["recon_data"]["targets"]) >= 1
    print("  ✓ test_recon_basic: PASS")


def test_recon_validation():
    """Test that cryer_recon output passes 6-level validation."""
    request = {
        "task_id": "task-0002",
        "domain": "recon",
        "instruction": "Analyze signals",
        "input_context": {
            "entity": "Alpha LLC",
            "targets": [{
                "entity": "Alpha LLC",
                "type": "business",
                "yield_score": 65,
                "confidence": 70,
                "risk_flags": [],
                "raw_sources": ["provided_input"],
            }],
        },
    }
    packet, exit_code, _ = invoke_worker(request)
    assert exit_code == 0
    valid, errors = validate_with_runtime(packet)
    assert valid, f"cryer_recon failed validation: {errors}"
    print("  ✓ test_recon_validation: PASS")


# ── Phase 2: Reputation Signal ──────────────────────────────────

def test_reputation_signal_basic():
    """Test basic cryer_reputation_signal packet production."""
    request = {
        "task_id": "task-0003",
        "domain": "reputation_signal",
        "instruction": "Analyze reputation signals",
        "input_context": {
            "entity": "Beta Corp",
            "signals": [{
                "type": "rating",
                "classification": "observed",
                "confidence": 85,
                "detail": "4.5-star average across 120 reviews",
                "source_quality": "primary",
                "unknowns": ["Exact review distribution"],
            }],
        },
    }
    packet, exit_code, stderr = invoke_worker(request)
    assert exit_code == 0, f"Worker exited with code {exit_code}: {stderr}"
    assert packet["packet_type"] == "cryer_reputation_signal"
    assert packet["source"] == "cryer"
    data = packet["reputation_signal_data"]
    assert data["entity"] == "Beta Corp"
    assert len(data["signals"]) >= 1
    assert isinstance(data["yield_score"], int)
    assert data["recommended_routing"] == "overcr"
    print("  ✓ test_reputation_signal_basic: PASS")


def test_reputation_signal_validation():
    """Test that cryer_reputation_signal passes 6-level validation."""
    request = {
        "task_id": "task-0004",
        "domain": "reputation_signal",
        "instruction": "Analyze reputation",
        "input_context": {
            "entity": "Gamma Inc",
            "signals": [{
                "type": "sentiment",
                "classification": "inferred",
                "confidence": 72,
                "detail": "Mostly positive reviews",
                "source_quality": "secondary",
                "unknowns": [],
            }],
        },
    }
    packet, exit_code, _ = invoke_worker(request)
    assert exit_code == 0
    valid, errors = validate_with_runtime(packet)
    assert valid, f"cryer_reputation_signal failed validation: {errors}"
    print("  ✓ test_reputation_signal_validation: PASS")


# ── Phase 3: Engagement Signal ─────────────────────────────────

def test_engagement_signal_basic():
    """Test basic cryer_engagement_signal packet production."""
    request = {
        "task_id": "task-0005",
        "domain": "engagement_signal",
        "instruction": "Analyze engagement",
        "input_context": {
            "entity": "Delta LLC",
            "metrics": [{
                "type": "review_count",
                "classification": "observed",
                "value": "87",
                "confidence": 90,
                "source_quality": "primary",
                "unknowns": [],
            }],
        },
    }
    packet, exit_code, stderr = invoke_worker(request)
    assert exit_code == 0, f"Worker exited with code {exit_code}: {stderr}"
    assert packet["packet_type"] == "cryer_engagement_signal"
    data = packet["engagement_signal_data"]
    assert data["entity"] == "Delta LLC"
    assert len(data["metrics"]) >= 1
    assert data["recommended_routing"] == "overcr"
    print("  ✓ test_engagement_signal_basic: PASS")


def test_engagement_signal_validation():
    """Test that cryer_engagement_signal passes 6-level validation."""
    request = {
        "task_id": "task-0006",
        "domain": "engagement_signal",
        "instruction": "Engagement analysis",
        "input_context": {
            "entity": "Epsilon Corp",
            "metrics": [{
                "type": "average_rating",
                "classification": "observed",
                "value": "4.2",
                "confidence": 88,
                "source_quality": "primary",
                "unknowns": [],
            }],
        },
    }
    packet, exit_code, _ = invoke_worker(request)
    assert exit_code == 0
    valid, errors = validate_with_runtime(packet)
    assert valid, f"cryer_engagement_signal failed validation: {errors}"
    print("  ✓ test_engagement_signal_validation: PASS")


# ── Phase 4: Booking Friction ───────────────────────────────────

def test_booking_friction_basic():
    """Test basic cryer_booking_friction packet production."""
    request = {
        "task_id": "task-0007",
        "domain": "booking_friction",
        "instruction": "Detect booking friction",
        "input_context": {
            "entity": "Zeta Services",
            "friction_points": [{
                "type": "no_online_booking",
                "classification": "observed",
                "confidence": 92,
                "detail": "No online booking system",
                "source_quality": "primary",
                "unknowns": [],
            }],
        },
    }
    packet, exit_code, stderr = invoke_worker(request)
    assert exit_code == 0, f"Worker exited with code {exit_code}: {stderr}"
    assert packet["packet_type"] == "cryer_booking_friction"
    data = packet["booking_friction_data"]
    assert data["entity"] == "Zeta Services"
    assert len(data["friction_points"]) >= 1
    assert data["recommended_routing"] == "overcr"
    print("  ✓ test_booking_friction_basic: PASS")


def test_booking_friction_validation():
    """Test that cryer_booking_friction passes 6-level validation."""
    request = {
        "task_id": "task-0008",
        "domain": "booking_friction",
        "instruction": "Friction detection",
        "input_context": {
            "entity": "Eta Medical",
            "friction_points": [{
                "type": "limited_hours",
                "classification": "observed",
                "confidence": 85,
                "detail": "10am-3pm Mon-Fri only",
                "source_quality": "primary",
                "unknowns": [],
            }],
        },
    }
    packet, exit_code, _ = invoke_worker(request)
    assert exit_code == 0
    valid, errors = validate_with_runtime(packet)
    assert valid, f"cryer_booking_friction failed validation: {errors}"
    print("  ✓ test_booking_friction_validation: PASS")


# ── Phase 5: Directory Completeness ────────────────────────────

def test_directory_completeness_basic():
    """Test basic cryer_directory_completeness packet production."""
    request = {
        "task_id": "task-0009",
        "domain": "directory_completeness",
        "instruction": "Assess directory completeness",
        "input_context": {
            "entity": "Theta Dental",
            "present_fields": ["name", "address", "phone", "website"],
            "missing_fields": ["hours", "description", "photos"],
        },
    }
    packet, exit_code, stderr = invoke_worker(request)
    assert exit_code == 0, f"Worker exited with code {exit_code}: {stderr}"
    assert packet["packet_type"] == "cryer_directory_completeness"
    data = packet["directory_completeness_data"]
    assert data["entity"] == "Theta Dental"
    assert isinstance(data["present_fields"], list)
    assert isinstance(data["missing_fields"], list)
    assert isinstance(data["completeness_score"], int)
    assert data["classification"] in ("observed", "inferred", "assumed", "unknown")
    assert data["recommended_routing"] == "overcr"
    print("  ✓ test_directory_completeness_basic: PASS")


def test_directory_completeness_validation():
    """Test that cryer_directory_completeness passes 6-level validation."""
    request = {
        "task_id": "task-0010",
        "domain": "directory_completeness",
        "instruction": "Directory assessment",
        "input_context": {
            "entity": "Iota Solutions",
            "present_fields": ["name"],
            "missing_fields": ["phone", "hours"],
        },
    }
    packet, exit_code, _ = invoke_worker(request)
    assert exit_code == 0
    valid, errors = validate_with_runtime(packet)
    assert valid, f"cryer_directory_completeness failed validation: {errors}"
    print("  ✓ test_directory_completeness_validation: PASS")


# ── Phase 6: Hiring Growth ──────────────────────────────────────

def test_hiring_growth_basic():
    """Test basic cryer_hiring_growth packet production."""
    request = {
        "task_id": "task-0011",
        "domain": "hiring_growth",
        "instruction": "Detect hiring signals",
        "input_context": {
            "entity": "Kappa Technologies",
            "signals": [{
                "type": "job_posting",
                "classification": "observed",
                "confidence": 88,
                "detail": "3 active job postings for senior engineers",
                "source_quality": "primary",
                "unknowns": [],
            }],
        },
    }
    packet, exit_code, stderr = invoke_worker(request)
    assert exit_code == 0, f"Worker exited with code {exit_code}: {stderr}"
    assert packet["packet_type"] == "cryer_hiring_growth"
    data = packet["hiring_growth_data"]
    assert data["entity"] == "Kappa Technologies"
    assert len(data["signals"]) >= 1
    assert data["recommended_routing"] == "overcr"
    print("  ✓ test_hiring_growth_basic: PASS")


def test_hiring_growth_validation():
    """Test that cryer_hiring_growth passes 6-level validation."""
    request = {
        "task_id": "task-0012",
        "domain": "hiring_growth",
        "instruction": "Growth analysis",
        "input_context": {
            "entity": "Lambda Labs",
            "signals": [{
                "type": "expansion_signal",
                "classification": "inferred",
                "confidence": 65,
                "detail": "Multiple simultaneous hires suggest expansion",
                "source_quality": "secondary",
                "unknowns": ["Expansion vs replacement unclear"],
            }],
        },
    }
    packet, exit_code, _ = invoke_worker(request)
    assert exit_code == 0
    valid, errors = validate_with_runtime(packet)
    assert valid, f"cryer_hiring_growth failed validation: {errors}"
    print("  ✓ test_hiring_growth_validation: PASS")


# ── Phase 7: Edge Cases ────────────────────────────────────────

def test_unknown_domain():
    """Test that unknown domain produces a valid fallback packet."""
    request = {
        "task_id": "task-0013",
        "domain": "unknown_domain",
        "instruction": "Analyze unknown",
        "input_context": {"entity": "Test Corp"},
    }
    packet, exit_code, stderr = invoke_worker(request)
    assert exit_code == 0, f"Worker exited with code {exit_code}: {stderr}"
    # Unknown domain should still produce output (fallback recon packet)
    assert packet is not None
    assert packet["source"] == "cryer"
    assert packet["target"] == "overcr"
    print("  ✓ test_unknown_domain: PASS")


def test_empty_input():
    """Test that empty input causes worker to exit nonzero."""
    proc = subprocess.run(
        [sys.executable, str(WORKER_PATH)],
        input="",
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode != 0, "Worker should exit nonzero on empty input"
    print("  ✓ test_empty_input: PASS")


def test_invalid_json():
    """Test that invalid JSON causes worker to exit nonzero."""
    proc = subprocess.run(
        [sys.executable, str(WORKER_PATH)],
        input="not json",
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode != 0, "Worker should exit nonzero on invalid JSON"
    print("  ✓ test_invalid_json: PASS")


def test_explicit_packet_type_override():
    """Test that required_packet_type overrides domain routing."""
    request = {
        "task_id": "task-0014",
        "domain": "recon",
        "required_packet_type": "cryer_hiring_growth",
        "instruction": "Detect growth",
        "input_context": {"entity": "Mu Corp"},
    }
    packet, exit_code, _ = invoke_worker(request)
    assert exit_code == 0
    assert packet["packet_type"] == "cryer_hiring_growth", f"Expected cryer_hiring_growth, got {packet['packet_type']}"
    print("  ✓ test_explicit_packet_type_override: PASS")


def test_governance_boundary():
    """Test that CryER packets route to operator (not directly to subagent)."""
    request = {
        "task_id": "task-0015",
        "domain": "reputation_signal",
        "instruction": "Analyze reputation",
        "input_context": {"entity": "Nu Corp"},
    }
    packet, exit_code, _ = invoke_worker(request)
    assert exit_code == 0
    # All CryER packets must target "overcr" — never another subagent
    assert packet["target"] == "overcr", f"CryER must target overcr, got {packet['target']}"
    # recommended_routing must be "overcr"
    data = packet.get("reputation_signal_data", {})
    assert data.get("recommended_routing") == "overcr", f"recommended_routing must be overcr"
    # No outbound contact instructions
    assert "contact" not in json.dumps(packet).lower() or "No external action" in packet.get("next_steps_recommendation", "")
    print("  ✓ test_governance_boundary: PASS")


# ── Main ────────────────────────────────────────────────────────

def main():
    """Run all CryER worker tests."""
    print("=" * 60)
    print("OverCR CryER Worker Test Suite — v0.4.0")
    print("=" * 60)

    tests = [
        # Phase 1: Recon
        test_recon_basic,
        test_recon_validation,
        # Phase 2: Reputation Signal
        test_reputation_signal_basic,
        test_reputation_signal_validation,
        # Phase 3: Engagement Signal
        test_engagement_signal_basic,
        test_engagement_signal_validation,
        # Phase 4: Booking Friction
        test_booking_friction_basic,
        test_booking_friction_validation,
        # Phase 5: Directory Completeness
        test_directory_completeness_basic,
        test_directory_completeness_validation,
        # Phase 6: Hiring Growth
        test_hiring_growth_basic,
        test_hiring_growth_validation,
        # Phase 7: Edge Cases
        test_unknown_domain,
        test_empty_input,
        test_invalid_json,
        test_explicit_packet_type_override,
        test_governance_boundary,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"  ✗ {test.__name__}: FAIL — {e}")
            failed += 1

    print()
    print(f"Results: {passed} passed, {failed} failed, {passed + failed} total")
    if failed > 0:
        global FAILED
        FAILED = True
        print("SOME TESTS FAILED")
    else:
        print("ALL TESTS PASSED")


if __name__ == "__main__":
    main()