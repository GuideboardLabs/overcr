#!/usr/bin/env python3
"""
OverCR v0.2.1 Test Suite
========================

Test scenarios for v0.2.1 hardening (L5 pattern leak prevention, health check
extension, packet versioning):

1. KnowER Live Demo: Full runtime pipeline with L5 pattern checks
2. Health Check Extension: verify live worker registry state
3. Replay Safety: Replaying the same packet MUST NOT trigger L5 patterns
4. Packet Validation: Full 6-level validation passes

Run:
  cd $OVERCR_ROOT
  python3 examples/test_v021.py

  Or with a custom workspace:
  python3 examples/test_v021.py --workspace /tmp/overcr-v021-tests
"""

import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

_CORE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_CORE_DIR))

from runtime.overcr_runtime import OverCRRuntime
from runtime.subagent_adapter import SubagentAdapter
from runtime.worker_registry import WorkerRegistry, WorkerRegistration, RUNTIME_COMPAT_VERSION

# Load validate_packet module via importlib.util to avoid 'tools' namespace conflict
# (tools/ has no __init__.py, so `from tools.validate_packet import` fails
#  when loaded via importlib.import_module by the test runner)
import importlib.util as _ilu
_vp_spec = _ilu.spec_from_file_location(
    "validate_packet",
    str(_CORE_DIR / "tools" / "validate_packet.py"),
)
_vp_mod = _ilu.module_from_spec(_vp_spec)
_vp_spec.loader.exec_module(_vp_mod)
validate_file = _vp_mod.validate_file


_FAILED = False


def banner(text: str, width: int = 76):
    print(f"\n{'=' * width}")
    print(f"  {text}")
    print(f"{'=' * width}")


def section(text: str):
    print(f"\n--- {text} ---")


def assert_test(name: str, condition: bool, detail: str = ""):
    global _FAILED
    status = "PASS" if condition else "FAIL"
    if not condition:
        _FAILED = True
    print(f"  [{status}] {name}")
    if detail:
        print(f"         {detail}")


def make_workspace(base_path: str | None = None) -> str:
    """Create a clean test workspace."""
    workspace = base_path or tempfile.mkdtemp(prefix="overcr-v021-test-")
    if os.path.exists(workspace):
        shutil.rmtree(workspace)
    os.makedirs(workspace, exist_ok=True)
    orch_dir = os.path.join(workspace, "orchestration", "tasks")
    os.makedirs(orch_dir, exist_ok=True)
    tools_dir = os.path.join(workspace, "tools")
    os.makedirs(tools_dir, exist_ok=True)

    with open(os.path.join(workspace, "orchestration", "task_counter.json"), "w") as f:
        json.dump({"last_task_id": "0000", "last_updated": datetime.now(timezone.utc).isoformat()}, f)
    shutil.copy2(str(_CORE_DIR / "tools" / "validate_packet.py"), os.path.join(tools_dir, "validate_packet.py"))

    return workspace


# ──────────────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────────────

def check_l5_patterns(packet: dict) -> list:
    """Check for Level 5 forbidden patterns in packet."""
    invalid_patterns = ["contact", "email", "call", "reach.out", "dm", "message"]
    found_patterns = []

    def find_patterns(obj, path=""):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(v, str):
                    for pat in invalid_patterns:
                        if pat.lower() in v.lower():
                            found_patterns.append(f"{path}.{k} = ...{pat}...")
                find_patterns(v, f"{path}.{k}")
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                find_patterns(item, f"{path}[{i}]")

    find_patterns(packet)
    return found_patterns


# ──────────────────────────────────────────────────────────────────────
# TEST 1: KnowER Live Demo with L5 Pattern Checks
# ──────────────────────────────────────────────────────────────────────

def test_knower_live_demo():
    """Full runtime pipeline with L5 pattern checks."""
    banner("Test 1: KnowER Live Demo")

    workspace = make_workspace()
    rt = OverCRRuntime(str(_CORE_DIR))
    adapter = SubagentAdapter(str(_CORE_DIR))

    # Verify worker is available
    assert_test("KnowER worker available", adapter.has_live_worker("knower"))

    # Register KnowER in the WorkerRegistry
    reg = WorkerRegistry(RUNTIME_COMPAT_VERSION)
    registration = WorkerRegistration(
        subagent="knower",
        version="0.2.1",
        supported_packet_types=frozenset(["knower_research", "knower_assessment", "knower_myth_separation"]),
        capability_flags=frozenset(["no_network", "no_shell", "no_fs_write", "no_outbound", "readonly_analysis"]),
        runtime_compat_version=RUNTIME_COMPAT_VERSION,
        worker_path="subagents/knower/worker.py",
    )
    reg.register(registration)

    # Create a KnowER research task
    section("Creating research task")
    task = rt.create_task(
        domain="research",
        description="Evaluate research topic",
        instruction="Research the history of quantum computing",
        input_context={"topic": "quantum computing history"},
    )
    assert_test("Task created", task is not None, f"task_id={task.get('task_id')}")
    task_id = task["task_id"]

    # Run the worker via invoke_subagent
    result = rt.invoke_subagent(task_id, timeout=30.0)
    assert_test("Worker completed successfully", result.get("success", False))

    # Extract output packet from adapter_result
    adapter_result = result.get("adapter_result", {})
    output = adapter_result.get("response_packet")
    assert_test("Worker produced output", output is not None, "output is not None")

    # Check Level 5 patterns
    section("L5 pattern check")
    found_patterns = check_l5_patterns(output)
    assert_test("No L5 contact instructions", len(found_patterns) == 0, f"patterns={found_patterns}")

    # Save output for validation
    output_path = os.path.join(workspace, "orchestration", "tasks", f"{task_id}_response.json")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)

    # Run full validation (Level 1-6)
    validation_result = validate_file(output_path)
    assert_test("Packet passes validation", validation_result.get("valid", False))
    if not validation_result.get("valid", False):
        print(f"         Errors: {validation_result.get('errors', [])}")


# ──────────────────────────────────────────────────────────────────────
# TEST 2: Health Check Extension
# ──────────────────────────────────────────────────────────────────────

def test_healthcheck_extension():
    """Worker registry must validate live worker state."""
    banner("Test 2: Worker Registry Extension")

    workspace = make_workspace()
    rt = OverCRRuntime(str(_CORE_DIR))
    adapter = SubagentAdapter(str(_CORE_DIR))

    # Check worker availability
    assert_test("KnowER available", adapter.has_live_worker("knower"))

    # Register workers
    reg = WorkerRegistry(RUNTIME_COMPAT_VERSION)
    caps = frozenset(["no_network", "no_shell", "no_fs_write", "no_outbound", "readonly_analysis"])
    pkt_types = frozenset(["knower_research", "knower_assessment", "knower_myth_separation"])

    registration = WorkerRegistration(
        subagent="knower",
        version="0.2.1",
        supported_packet_types=pkt_types,
        capability_flags=caps,
        runtime_compat_version=RUNTIME_COMPAT_VERSION,
        worker_path="subagents/knower/worker.py",
    )
    reg_result = reg.register(registration)
    assert_test("Registration successful", reg_result.get("registered", False))

    # Verify the registration can be retrieved
    reg_dict = reg.get_registration_dict("knower")
    assert_test("Registration dict available", reg_dict is not None)
    assert_test("Registration has subagent", reg_dict.get("subagent") == "knower")
    assert_test("Registration has version", reg_dict.get("version") == "0.2.1")

    # List registered workers
    registrations = reg.list_registrations()
    assert_test("Registry lists workers", len(registrations) > 0)
    assert_test("List includes knower", any(r.subagent == "knower" for r in registrations))


# ──────────────────────────────────────────────────────────────────────
# TEST 3: Replay Safety
# ──────────────────────────────────────────────────────────────────────

def test_replay_safety():
    """Replaying the same packet MUST NOT trigger L5 patterns."""
    banner("Test 3: Replay Safety")

    workspace = make_workspace()
    rt = OverCRRuntime(str(_CORE_DIR))

    # Create and run task once to capture the response packet
    section("First run")
    task1 = rt.create_task(
        domain="research",
        description="Research topic",
        instruction="Research black holes",
        input_context={"topic": "black holes"},
    )
    assert_test("Task1 created", task1 is not None)
    task_id1 = task1["task_id"]

    result1 = rt.invoke_subagent(task_id1, timeout=30.0)
    assert_test("Task1 worker succeeded", result1.get("success", False))
    adapter_result1 = result1.get("adapter_result", {})
    output1 = adapter_result1.get("response_packet")

    # Check L5 patterns in first run
    section("L5 pattern check (first run)")
    found_patterns_1 = check_l5_patterns(output1)
    assert_test("First run has no L5 patterns", len(found_patterns_1) == 0)

    # Replay by creating a second task with same input (simulating same packet)
    section("Replay (same instruction)")
    task2 = rt.create_task(
        domain="research",
        description="Research topic (replay)",
        instruction="Research black holes",
        input_context={"topic": "black holes"},
    )
    assert_test("Task2 created", task2 is not None)
    task_id2 = task2["task_id"]

    result2 = rt.invoke_subagent(task_id2, timeout=30.0)
    assert_test("Task2 worker succeeded", result2.get("success", False))
    adapter_result2 = result2.get("adapter_result", {})
    output2 = adapter_result2.get("response_packet")

    # Check no L5 patterns in replay output
    section("L5 pattern check (replay)")
    found_patterns_2 = check_l5_patterns(output2)
    assert_test("Replay has no L5 patterns", len(found_patterns_2) == 0, f"patterns={found_patterns_2}")


# ──────────────────────────────────────────────────────────────────────
# TEST 4: Packet Validation
# ──────────────────────────────────────────────────────────────────────

def test_packet_validation():
    """Full 6-level validation passes."""
    banner("Test 4: Packet Validation")

    workspace = make_workspace()
    rt = OverCRRuntime(str(_CORE_DIR))

    # Create and run task
    section("Creating task")
    task = rt.create_task(
        domain="research",
        description="Test validation",
        instruction="Researchmars rovers",
        input_context={"topic": "mars rovers"},
    )
    task_id = task["task_id"]

    result = rt.invoke_subagent(task_id, timeout=30.0)
    assert_test("Worker succeeded", result.get("success", False))

    adapter_result = result.get("adapter_result", {})
    output = adapter_result.get("response_packet")
    output_path = os.path.join(workspace, "orchestration", "tasks", f"{task_id}_response.json")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)

    # Run full validation
    section("Full 6-level validation")
    validation_result = validate_file(output_path)

    assert_test("Validation valid", validation_result.get("valid", False))

    if not validation_result.get("valid", False):
        print(f"  Errors: {validation_result.get('errors', [])}")
        print(f"  Warnings: {validation_result.get('warnings', [])}")

    # Verify all required levels passed
    # (Level 1-6 checks are internal to validate_file, we just confirm final result)


# ──────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────

def main():
    banner("OverCR v0.2.1 Test Suite")
    section("Starting tests")

    test_knower_live_demo()
    test_healthcheck_extension()
    test_replay_safety()
    test_packet_validation()

    section("Summary")
    if _FAILED:
        print("  RESULTS: Some tests FAILED (see above)")
        sys.exit(1)
    else:
        print("  RESULTS: All tests PASSED")
        sys.exit(0)


if __name__ == "__main__":
    main()
