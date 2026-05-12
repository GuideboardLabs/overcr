#!/usr/bin/env python3
"""
OverCR v0.2.1 Model Routing Extension — Test Examples

Demonstrates the model router with various routing scenarios.
"""

import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from runtime.model_router import ModelRouter, RoutingResult


def test_basic_routing():
    """Test basic route resolution."""
    print("\n=== Test 1: Basic Routing ===")
    router = ModelRouter()

    cases = [
        ("task-001", "research", "knower", None),
        ("task-002", "code", "coder", None),
        ("task-003", "recon", "cryer", None),
        ("task-004", "unknown", None, None),
    ]

    for tid, domain, subagent, task_type in cases:
        result = router.route(
            task_id=tid,
            domain=domain,
            assigned_subagent=subagent,
            task_type=task_type,
        )
        print(f"{tid}: {result.model} ({result.route_used})")


def test_subagent_override():
    """Test subagent-specific model preference."""
    print("\n=== Test 2: Subagent Override ===")
    router = ModelRouter()

    result = router.route(
        task_id="task-005",
        domain="diagnostics",
        assigned_subagent="knower",  # knower prefers glm-5.1
    )
    print(f"knower on diagnostics: {result.model}")


def test_task_type_override():
    """Test explicit task_type override."""
    print("\n=== Test 3: Task Type Override ===")
    router = ModelRouter()

    result = router.route(
        task_id="task-006",
        domain="code",
        assigned_subagent="coder",
        task_type="overcr_hq",  # Override to HQ route
    )
    print(f"overcr_hq override: {result.model}")


def test_fallback_logic():
    """Test fallback model selection."""
    print("\n=== Test 4: Fallback Simulation ===")
    router = ModelRouter()

    # Simulate a scenario where preferred fails
    # (in real use, SubagentAdapter would detect timeout/empty)
    result = router.route(
        task_id="task-007",
        domain="local_boot",
        assigned_subagent="pyper",
    )
    print(f"local_boot → {result.model} (fallback_used: {result.fallback_used})")


def test_audit_log():
    """Test audit log generation."""
    print("\n=== Test 5: Audit Log ===")
    router = ModelRouter()

    router.route("task-008", "research", "knower", None)
    router.route("task-009", "code", "coder", None)
    router.route("task-010", "unknown", None, None)

    for entry in router.get_audit_entries():
        print(f"  {entry['entry_type']}: {entry['details']['model_selected']}")

    print(f"\nTotal selections: {len(router._model_selection_log)}")
    print(f"Total fallbacks: {len(router._fallback_log)}")


def test_validation():
    """Test packet validation integration."""
    print("\n=== Test 6: Validation Integration ===")
    router = ModelRouter()

    # Sample response packet (simplified L1)
    packet = {
        "packet_type": "knower_research",
        "version": "1.0",
        "timestamp": "2026-05-10T00:00:00+00:00",
        "source": "knower",
        "target": "overcr",
        "task_id": "task-0011",
        "summary": "Test research",
        "research_data": {
            "topic": "Test topic",
            "findings": [],
            "sources": [],
        },
        "audit_trail": {
            "worker_version": "0.2.1",
            "execution_timestamp": "2026-05-10T00:00:00+00:00",
        },
        "approval_required": False,
    }

    valid, errors, warnings = router.validate_packet_type(packet)
    print(f"Packet valid: {valid}")
    if errors:
        print(f"Errors: {errors}")
    if warnings:
        print(f"Warnings: {warnings}")


def main():
    """Run all tests."""
    print("=" * 60)
    print("OverCR Model Router Test Suite (v0.2.1)")
    print("=" * 60)

    test_basic_routing()
    test_subagent_override()
    test_task_type_override()
    test_fallback_logic()
    test_audit_log()
    test_validation()

    print("\n" + "=" * 60)
    print("All tests completed.")
    print("=" * 60)


if __name__ == "__main__":
    main()
