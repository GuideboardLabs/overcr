#!/usr/bin/env python3
"""
OverCR v0.3.0 Test Suite — KnowER Myth/Fact Classification

Tests the knower_myth_fact packet type:
  1. Worker produces valid myth_fact packets
  2. Packets pass 6-level validation
  3. Classification types (myth/fact/partial_truth/unverified) are valid
  4. Source quality ratings are valid
  5. Unknowns and explanations are present
  6. Operator brief is non-empty
  7. Domain routing works (myth_fact → knower)
  8. Governance: no outbound, no override claims
  9. Malformed packets are rejected
  10. Direct worker invocation works

Run:
  cd $OVERCR_ROOT
  python3 tests/test_knower_myth_fact.py
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

_CORE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_CORE_DIR))

from runtime.overcr_runtime import OverCRRuntime
from runtime.subagent_adapter import SubagentAdapter
from runtime.worker_registry import WorkerRegistry, WorkerRegistration, RUNTIME_COMPAT_VERSION

# Load validate_packet via importlib.util to avoid 'tools' namespace conflict
# (tools/ has no __init__.py, so `from tools.validate_packet import` fails
#  when loaded via importlib.import_module by the test runner)
import importlib.util as _ilu
_vp_spec = _ilu.spec_from_file_location(
    "validate_packet",
    str(_CORE_DIR / "tools" / "validate_packet.py"),
)
_vp_mod = _ilu.module_from_spec(_vp_spec)
_vp_spec.loader.exec_module(_vp_mod)
validate_packet = _vp_mod.validate_packet


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
    workspace = base_path or tempfile.mkdtemp(prefix="overcr-myth-fact-test-")
    if os.path.exists(workspace):
        shutil.rmtree(workspace)
    os.makedirs(workspace, exist_ok=True)
    orch_dir = os.path.join(workspace, "orchestration", "tasks")
    os.makedirs(orch_dir, exist_ok=True)
    tools_dir = os.path.join(workspace, "tools")
    os.makedirs(tools_dir, exist_ok=True)
    with open(os.path.join(workspace, "orchestration", "task_counter.json"), "w") as f:
        json.dump({"last_task_id": "0000", "last_updated": datetime.now(timezone.utc).isoformat()}, f)
    shutil.copy2(str(_CORE_DIR / "tools" / "validate_packet.py"),
                 os.path.join(tools_dir, "validate_packet.py"))
    return workspace


def test_myth_fact_happy_path():
    """Test: KnowER worker produces valid myth_fact packet via runtime."""
    banner("Test 1: Myth/Fact Happy Path")
    workspace = make_workspace()
    rt = OverCRRuntime(str(_CORE_DIR))

    myth_fact_input = {
        "topic": "Test regional economic myths",
        "statements": [
            "The county has the highest unemployment rate in the state",
            "A new tech campus is opening downtown next year",
        ],
        "source_texts": [
            "Employment report: County unemployment is 5.2%, state average is 4.8%.",
        ],
    }

    task = rt.create_task(
        domain="myth_fact",
        description="Classify statements as myth/fact/partial_truth/unverified",
        instruction="Classify each statement as myth, fact, partial_truth, or unverified",
        input_context=myth_fact_input,
    )
    task_id = task["task_id"]

    assert_test("Task created", task_id.startswith("task-"))
    task = rt.task_store.load_task(task_id)
    assert_test("Task subagent is knower", task["assigned_subagent"] == "knower")

    # Invoke worker via runtime pipeline
    result = rt.invoke_subagent(task_id, timeout=30.0)
    assert_test("Worker pipeline succeeded", result.get("success"),
                f"Error: {result.get('error', 'none')}")

    if not result.get("success"):
        print(f"  Error detail: {result.get('error', 'unknown')}")
        shutil.rmtree(workspace, ignore_errors=True)
        return

    # Extract response packet
    adapter_result = result.get("adapter_result", {})
    response = adapter_result.get("response_packet")
    assert_test("Response packet exists", response is not None)
    if not response:
        shutil.rmtree(workspace, ignore_errors=True)
        return

    assert_test("Packet type is knower_myth_fact",
                response.get("packet_type") == "knower_myth_fact",
                f"Got {response.get('packet_type')}")
    assert_test("Source is knower", response.get("source") == "knower")
    assert_test("Target is overcr", response.get("target") == "overcr")

    # Validate
    valid, errors, warnings = validate_packet(response)
    assert_test("6-level validation passes", valid, f"Errors: {errors[:3]}")

    # Check myth_fact_data structure
    mf_data = response.get("myth_fact_data", {})
    assert_test("myth_fact_data exists", bool(mf_data))
    assert_test("topic is non-empty", bool(mf_data.get("topic")))

    items = mf_data.get("items", [])
    assert_test("items array has at least 1 entry", len(items) >= 1)

    if items:
        item = items[0]
        assert_test("item.statement is non-empty", bool(item.get("statement")))
        valid_classifications = ("myth", "fact", "partial_truth", "unverified")
        assert_test("item.classification is valid",
                    item.get("classification") in valid_classifications,
                    f"Got: {item.get('classification')}")
        assert_test("item.confidence is 1-4",
                    item.get("confidence") in (1, 2, 3, 4),
                    f"Got: {item.get('confidence')}")
        valid_qualities = ("primary", "secondary", "tertiary", "unverified")
        assert_test("item.source_quality is valid",
                    item.get("source_quality") in valid_qualities,
                    f"Got: {item.get('source_quality')}")
        assert_test("item.explanation is non-empty", bool(item.get("explanation")))
        assert_test("item.unknowns exists", "unknowns" in item)

    operator_brief = mf_data.get("operator_brief", "")
    assert_test("operator_brief is non-empty", bool(operator_brief))

    # Check routing
    routing = result.get("routing")
    assert_test("Routes to operator", routing is not None and routing.get("routing_target") == "operator",
                f"Routing: {routing}")

    shutil.rmtree(workspace, ignore_errors=True)


def test_myth_fact_governance():
    """Test: Myth/fact packets have no outbound or governance override patterns."""
    banner("Test 2: Myth/Fact Governance Safety")
    workspace = make_workspace()
    rt = OverCRRuntime(str(_CORE_DIR))

    task = rt.create_task(
        domain="myth_fact",
        description="Governance test",
        instruction="Classify myths about economic indicators",
        input_context={"topic": "Economic myths", "statements": ["Test statement"]},
    )
    task_id = task["task_id"]

    result = rt.invoke_subagent(task_id, timeout=30.0)

    if result.get("success"):
        adapter_result = result.get("adapter_result", {})
        response = adapter_result.get("response_packet")
        if response:
            valid, errors, warnings = validate_packet(response)
            assert_test("No L5 outbound patterns",
                        not any("contact" in e.lower() or "outbound" in e.lower() for e in errors))
            assert_test("No L5 governance override",
                        not any("governance override" in e.lower() or "override claim" in e.lower() for e in errors))
            assert_test("Validation passes", valid, f"Errors: {errors[:3]}")
        else:
            assert_test("Got response packet", False, "No response packet from adapter")
    else:
        assert_test("Worker pipeline succeeded", False, f"Error: {result.get('error', 'unknown')}")

    shutil.rmtree(workspace, ignore_errors=True)


def test_myth_fact_malformed():
    """Test: Malformed myth_fact packets are rejected."""
    banner("Test 3: Malformed Myth/Fact Packets Rejected")

    # Missing myth_fact_data
    packet_no_data = {
        "packet_type": "knower_myth_fact",
        "version": "1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "knower",
        "target": "overcr",
        "task_id": "task-0001",
        "summary": "Test myth_fact with missing data",
    }

    valid, errors, _ = validate_packet(packet_no_data)
    assert_test("Missing myth_fact_data rejected", not valid)
    has_l3 = any("Level 3" in e and "myth_fact" in e for e in errors)
    assert_test("L3 error mentions myth_fact_data", has_l3,
                f"L3 errors: {[e for e in errors if 'Level 3' in e]}")

    # Empty items
    packet_empty_items = {
        "packet_type": "knower_myth_fact",
        "version": "1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "knower",
        "target": "overcr",
        "task_id": "task-0002",
        "summary": "Test with empty items",
        "myth_fact_data": {
            "topic": "Test",
            "items": [],
            "operator_brief": "Brief",
        },
    }

    valid2, errors2, _ = validate_packet(packet_empty_items)
    assert_test("Empty items rejected at L6", not valid2)

    # Invalid classification
    packet_bad_class = {
        "packet_type": "knower_myth_fact",
        "version": "1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "knower",
        "target": "overcr",
        "task_id": "task-0003",
        "summary": "Test with invalid classification",
        "myth_fact_data": {
            "topic": "Test",
            "items": [
                {
                    "statement": "A claim",
                    "classification": "wrong_type",
                    "confidence": 3,
                    "source_quality": "secondary",
                    "explanation": "Test explanation",
                    "unknowns": [],
                }
            ],
            "operator_brief": "Brief",
        },
    }

    valid3, errors3, _ = validate_packet(packet_bad_class)
    assert_test("Invalid classification rejected at L6", not valid3)
    has_l6_class = any("Level 6" in e and "classification" in e for e in errors3)
    assert_test("L6 error references classification", has_l6_class)

    # Invalid source_quality
    packet_bad_qual = {
        "packet_type": "knower_myth_fact",
        "version": "1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "knower",
        "target": "overcr",
        "task_id": "task-0004",
        "summary": "Test with invalid source quality",
        "myth_fact_data": {
            "topic": "Test",
            "items": [
                {
                    "statement": "A claim",
                    "classification": "myth",
                    "confidence": 3,
                    "source_quality": "invalid_quality",
                    "explanation": "Test explanation",
                    "unknowns": [],
                }
            ],
            "operator_brief": "Brief",
        },
    }

    valid4, errors4, _ = validate_packet(packet_bad_qual)
    assert_test("Invalid source_quality rejected at L6", not valid4)


def test_myth_fact_routing():
    """Test: myth_fact domain routing."""
    banner("Test 4: Myth/Fact Routing")

    from runtime.task_store import DOMAIN_SUBAGENT_MAP, SUBAGENT_PACKET_TYPES
    assert_test("myth_fact domain maps to knower",
                DOMAIN_SUBAGENT_MAP.get("myth_fact") == "knower",
                f"Expected knower, got {DOMAIN_SUBAGENT_MAP.get('myth_fact')}")
    assert_test("knower_myth_fact in subagent packet types",
                "knower_myth_fact" in SUBAGENT_PACKET_TYPES.get("knower", set()),
                f"Available: {SUBAGENT_PACKET_TYPES.get('knower', set())}")

    # Verify routing table
    from runtime.overcr_runtime import OverCRRuntime
    routing_table = OverCRRuntime.ROUTING_TABLE
    routing_key = ("knower", "knower_myth_fact")
    assert_test("Routing table has knower_myth_fact entry",
                routing_key in routing_table,
                f"Key {routing_key} not found in routing table")
    myth_fact_routes = routing_table.get(routing_key, [])
    route_targets = [r.get("target") for r in myth_fact_routes]
    assert_test("knower_myth_fact routes to operator",
                "operator" in route_targets,
                f"Expected operator in routes, got {route_targets}")


def test_myth_fact_worker_direct():
    """Test: Direct subprocess invocation for myth_fact."""
    banner("Test 5: Direct Worker Invocation (Myth/Fact)")

    request = json.dumps({
        "task_id": "task-0088",
        "domain": "myth_fact",
        "instruction": "Classify statements as myth, fact, partial_truth, or unverified",
        "input_context": {
            "topic": "Direct invocation test: urban legends",
            "statements": ["The city was founded in 1800", "Underground tunnels connect downtown buildings"],
            "source_texts": ["Historical records: City founded 1789.", "No documentation of tunnels."],
        },
    })

    worker_path = str(_CORE_DIR / "subagents" / "knower" / "worker.py")
    proc = subprocess.run(
        [sys.executable, worker_path],
        input=request,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert_test("Worker exits 0", proc.returncode == 0,
                f"exit_code={proc.returncode}")

    try:
        response = json.loads(proc.stdout)
    except json.JSONDecodeError:
        assert_test("Worker output is valid JSON", False, f"stdout: {proc.stdout[:200]}")
        return

    assert_test("Packet type is knower_myth_fact",
                response.get("packet_type") == "knower_myth_fact",
                f"Got: {response.get('packet_type')}")
    assert_test("myth_fact_data exists", "myth_fact_data" in response)
    mf_data = response.get("myth_fact_data", {})
    assert_test("topic is non-empty", bool(mf_data.get("topic")))

    items = mf_data.get("items", [])
    assert_test("At least 1 item", len(items) >= 1)

    if items:
        assert_test("First item has classification",
                    items[0].get("classification") in ("myth", "fact", "partial_truth", "unverified"))
        assert_test("First item has source_quality",
                    items[0].get("source_quality") in ("primary", "secondary", "tertiary", "unverified"))
        assert_test("First item has confidence 1-4",
                    items[0].get("confidence") in (1, 2, 3, 4))
        assert_test("First item has explanation",
                    bool(items[0].get("explanation")))

    # Full 6-level validation
    valid, errors, warnings = validate_packet(response)
    assert_test("6-level validation passes", valid,
                f"Errors: {errors[:5]}")


def main():
    banner("OverCR v0.3.0 — KnowER Myth/Fact Tests")
    print(f"  Core dir: {_CORE_DIR}")

    test_myth_fact_happy_path()
    test_myth_fact_governance()
    test_myth_fact_malformed()
    test_myth_fact_routing()
    test_myth_fact_worker_direct()

    banner("Test Results")
    if _FAILED:
        print("  FAILED: Some tests did not pass.")
        print("  Review the FAIL entries above for details.")
        sys.exit(1)
    else:
        print("  ALL PASSED: Myth/fact tests passed.")
        sys.exit(0)


if __name__ == "__main__":
    main()