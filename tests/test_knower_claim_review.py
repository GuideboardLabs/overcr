#!/usr/bin/env python3
"""
OverCR v0.3.0 Test Suite — KnowER Claim Review

Tests the knower_claim_review packet type through the full runtime pipeline:
  1. Worker produces valid claim_review packets
  2. Packets pass 6-level validation
  3. Claim classification fields are correct
  4. Source quality ratings are valid
  5. Unknowns and verification needs are present
  6. Operator brief is non-empty
  7. Domain routing works correctly
  8. Governance: no outbound contact, no governance override claims
  9. Malformed packets are rejected
  10. Direct worker invocation works

Run:
  cd $OVERCR_ROOT
  python3 tests/test_knower_claim_review.py
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
from runtime.worker_registry import WorkerRegistry, WorkerRegistration, KNOWER_CAPABILITIES, RUNTIME_COMPAT_VERSION
from runtime.worker_capabilities import validate_capabilities, validate_packet_types

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
    workspace = base_path or tempfile.mkdtemp(prefix="overcr-claim-review-test-")
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


def test_claim_review_happy_path():
    """Test: KnowER worker produces valid claim_review packet via runtime."""
    banner("Test 1: Claim Review Happy Path")
    workspace = make_workspace()
    rt = OverCRRuntime(str(_CORE_DIR))

    claim_review_input = {
        "topic": "Test topic: public budget claims",
        "claims_to_review": [
            "The city allocated $5M for park renovation",
            "Mayor promised no tax increases",
            "The project will be completed by next year",
            "A private donor funded the entire project",
        ],
        "source_texts": [
            "City budget document, section 2.3: $4.8M allocated for parks.",
        ],
    }

    task = rt.create_task(
        domain="claim_review",
        description="Test claim review",
        instruction="Classify claims about public budget",
        input_context=claim_review_input,
    )
    task_id = task["task_id"]

    assert_test("Task created", task_id.startswith("task-"))
    task = rt.task_store.load_task(task_id)
    assert_test("Task subagent is knower", task["assigned_subagent"] == "knower",
                f"Expected knower, got {task['assigned_subagent']}")
    assert_test("Task state is created", task["state"] == "created",
                f"Expected created, got {task['state']}")

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

    assert_test("Response packet type is knower_claim_review",
                response.get("packet_type") == "knower_claim_review",
                f"Got {response.get('packet_type')}")
    assert_test("Source is knower", response.get("source") == "knower")
    assert_test("Target is overcr", response.get("target") == "overcr")

    # Validate with 6-level validator
    valid, errors, warnings = validate_packet(response)
    assert_test("6-level validation passes", valid,
                f"Errors: {errors[:3]}")

    # Check claim_review_data structure
    cr_data = response.get("claim_review_data", {})
    assert_test("claim_review_data exists", bool(cr_data))
    assert_test("claim_review_data.topic is non-empty",
                bool(cr_data.get("topic")),
                f"Got: {cr_data.get('topic')}")

    claims = cr_data.get("claims", [])
    assert_test("claims array has at least 1 entry", len(claims) >= 1,
                f"Got {len(claims)} claims")

    if claims:
        claim = claims[0]
        assert_test("claim.text is non-empty", bool(claim.get("text")),
                    f"Got: {claim.get('text')}")
        assert_test("claim.classification is valid",
                    claim.get("classification") in ("fact", "inference", "assumption", "rumor"),
                    f"Got: {claim.get('classification')}")
        assert_test("claim.confidence is 1-4",
                    claim.get("confidence") in (1, 2, 3, 4),
                    f"Got: {claim.get('confidence')}")
        assert_test("claim.source_quality is valid",
                    claim.get("source_quality") in ("primary", "secondary", "tertiary", "unverified"),
                    f"Got: {claim.get('source_quality')}")
        assert_test("claim.unknowns exists", "unknowns" in claim,
                    f"Missing unknowns field")

    operator_brief = cr_data.get("operator_brief", "")
    assert_test("operator_brief is non-empty", bool(operator_brief),
                f"Got: '{operator_brief[:50]}'")

    # Check routing
    routing = result.get("routing")
    assert_test("Routes to operator", routing is not None and routing.get("routing_target") == "operator",
                f"Routing: {routing}")

    # Cleanup
    shutil.rmtree(workspace, ignore_errors=True)


def test_claim_review_governance():
    """Test: Claim review packets have no outbound or governance override patterns."""
    banner("Test 2: Claim Review Governance Safety")
    workspace = make_workspace()
    rt = OverCRRuntime(str(_CORE_DIR))

    task = rt.create_task(
        domain="claim_review",
        description="Governance safety test",
        instruction="Review claims about municipal spending",
        input_context={"topic": "Municipal spending claims", "claims_to_review": ["Test claim"]},
    )
    task_id = task["task_id"]

    result = rt.invoke_subagent(task_id, timeout=30.0)

    if result.get("success"):
        adapter_result = result.get("adapter_result", {})
        response = adapter_result.get("response_packet")
        if response:
            valid, errors, warnings = validate_packet(response)
            assert_test("No L5 outbound patterns", not any("outbound" in e.lower() or "contact" in e.lower() for e in errors),
                        f"L5 errors: {[e for e in errors if 'contact' in e.lower() or 'outbound' in e.lower()]}")
            assert_test("No L5 governance override patterns",
                        not any("governance override" in e.lower() or "override claim" in e.lower() for e in errors),
                        f"Governance errors: {[e for e in errors if 'governance' in e.lower() or 'override' in e.lower()]}")
            assert_test("Validation passes", valid, f"Errors: {errors}")
        else:
            assert_test("Got response packet", False, "No response packet from adapter")
    else:
        assert_test("Worker pipeline succeeded", False, f"Error: {result.get('error', 'unknown')}")

    shutil.rmtree(workspace, ignore_errors=True)


def test_claim_review_malformed():
    """Test: Malformed claim_review packets are rejected by validator."""
    banner("Test 3: Malformed Claim Review Packets Rejected")

    # Missing claim_review_data
    packet_no_data = {
        "packet_type": "knower_claim_review",
        "version": "1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "knower",
        "target": "overcr",
        "task_id": "task-0001",
        "summary": "Test claim review with missing data",
    }

    valid, errors, _ = validate_packet(packet_no_data)
    assert_test("Missing claim_review_data rejected at L3", not valid,
                f"Expected validation failure, got valid={valid}")
    has_l3 = any("Level 3" in e and "claim_review_data" in e for e in errors)
    assert_test("L3 error mentions claim_review_data", has_l3,
                f"L3 errors: {[e for e in errors if 'Level 3' in e]}")

    # Empty claims array
    packet_empty_claims = {
        "packet_type": "knower_claim_review",
        "version": "1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "knower",
        "target": "overcr",
        "task_id": "task-0002",
        "summary": "Test claim review with empty claims",
        "claim_review_data": {
            "topic": "Test",
            "claims": [],
            "operator_brief": "Brief",
        },
    }

    valid2, errors2, _ = validate_packet(packet_empty_claims)
    assert_test("Empty claims array rejected at L3 or L6", not valid2,
                f"Expected failure, got valid={valid2}")

    # Invalid classification
    packet_bad_class = {
        "packet_type": "knower_claim_review",
        "version": "1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "knower",
        "target": "overcr",
        "task_id": "task-0003",
        "summary": "Test with invalid classification",
        "claim_review_data": {
            "topic": "Test",
            "claims": [
                {
                    "text": "A claim",
                    "classification": "invalid_type",
                    "confidence": 3,
                    "source_quality": "secondary",
                    "evidence": [],
                    "unknowns": [],
                }
            ],
            "operator_brief": "Brief",
        },
    }

    valid3, errors3, _ = validate_packet(packet_bad_class)
    assert_test("Invalid classification rejected at L6", not valid3,
                f"Expected failure, got valid={valid3}")
    has_l6_class = any("Level 6" in e and "classification" in e for e in errors3)
    assert_test("L6 error mentions classification", has_l6_class,
                f"L6 errors: {[e for e in errors3 if 'Level 6' in e]}")

    # Invalid source quality
    packet_bad_qual = {
        "packet_type": "knower_claim_review",
        "version": "1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "knower",
        "target": "overcr",
        "task_id": "task-0004",
        "summary": "Test with invalid source quality",
        "claim_review_data": {
            "topic": "Test",
            "claims": [
                {
                    "text": "A claim",
                    "classification": "fact",
                    "confidence": 3,
                    "source_quality": "invalid_quality",
                    "evidence": [],
                    "unknowns": [],
                }
            ],
            "operator_brief": "Brief",
        },
    }

    valid4, errors4, _ = validate_packet(packet_bad_qual)
    assert_test("Invalid source_quality rejected at L6", not valid4,
                f"Expected failure, got valid={valid4}")


def test_claim_review_timeout():
    """Test: Worker timeout is handled safely for claim_review domain."""
    banner("Test 4: Claim Review Timeout Safety")
    workspace = make_workspace()
    rt = OverCRRuntime(str(_CORE_DIR))

    task = rt.create_task(
        domain="claim_review",
        description="Timeout test",
        instruction="Review claims (will timeout)",
        input_context={"topic": "Timeout test"},
    )
    task_id = task["task_id"]

    # Use a very short timeout to force timeout
    adapter = SubagentAdapter(str(_CORE_DIR))
    from runtime.overcr_runtime import OverCRRuntime as _OR
    # We need to invoke with timeout directly
    rt.task_store.advance_state(task_id, "assigned", "Subagent acknowledged assignment")
    rt.audit.state_transition(task_id, "created", "assigned", "Subagent acknowledged")
    rt.task_store.advance_state(task_id, "in_progress", "Subagent began work")
    rt.audit.state_transition(task_id, "assigned", "in_progress", "Subagent began work")

    request_packet = rt.task_store.load_task(task_id).get("request_packet", {})
    result = adapter.invoke("knower", request_packet, task_id, timeout=0.001)

    assert_test("Timeout results in failure", not result.get("success") or result.get("exit_code", -1) != 0,
                f"Expected failure, got success={result.get('success')} exit_code={result.get('exit_code')}")

    shutil.rmtree(workspace, ignore_errors=True)


def test_claim_review_routing():
    """Test: claim_review domain routes to knower and then to operator."""
    banner("Test 5: Claim Review Routing")

    # Verify domain mapping
    from runtime.task_store import DOMAIN_SUBAGENT_MAP
    assert_test("claim_review domain maps to knower",
                DOMAIN_SUBAGENT_MAP.get("claim_review") == "knower",
                f"Expected knower, got {DOMAIN_SUBAGENT_MAP.get('claim_review')}")

    # Verify packet type is registered
    from runtime.task_store import SUBAGENT_PACKET_TYPES
    assert_test("knower_claim_review in subagent packet types",
                "knower_claim_review" in SUBAGENT_PACKET_TYPES.get("knower", set()),
                f"Available: {SUBAGENT_PACKET_TYPES.get('knower', set())}")

    # Verify routing table
    from runtime.overcr_runtime import OverCRRuntime
    routing_table = OverCRRuntime.ROUTING_TABLE
    routing_key = ("knower", "knower_claim_review")
    assert_test("Routing table has knower_claim_review entry",
                routing_key in routing_table,
                f"Key {routing_key} not found in routing table")
    claim_review_routes = routing_table.get(routing_key, [])
    route_targets = [r.get("target") for r in claim_review_routes]
    assert_test("knower_claim_review routes to operator",
                "operator" in route_targets,
                f"Expected operator in routes, got {route_targets}")


def test_claim_review_worker_direct():
    """Test: Invoke KnowER worker directly via subprocess for claim_review."""
    banner("Test 6: Direct Worker Invocation (Claim Review)")

    request = json.dumps({
        "task_id": "task-0099",
        "domain": "claim_review",
        "instruction": "Classify claims as fact, inference, assumption, or rumor",
        "input_context": {
            "topic": "Test infrastructure claims",
            "claims_to_review": ["The bridge was built in 1950", "Traffic will double by 2030"],
            "source_texts": ["Highway department records indicate construction in 1952."],
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

    assert_test("Response packet_type is knower_claim_review",
                response.get("packet_type") == "knower_claim_review",
                f"Got: {response.get('packet_type')}")
    assert_test("claim_review_data exists", "claim_review_data" in response)
    assert_test("claim_review_data.topic is non-empty",
                bool(response.get("claim_review_data", {}).get("topic")))
    claims = response.get("claim_review_data", {}).get("claims", [])
    assert_test("At least 1 claim in result", len(claims) >= 1)
    if claims:
        assert_test("First claim has classification",
                    claims[0].get("classification") in ("fact", "inference", "assumption", "rumor"))
        assert_test("First claim has source_quality",
                    claims[0].get("source_quality") in ("primary", "secondary", "tertiary", "unverified"))
        assert_test("First claim has confidence 1-4",
                    claims[0].get("confidence") in (1, 2, 3, 4))

    # Full 6-level validation
    valid, errors, warnings = validate_packet(response)
    assert_test("6-level validation passes", valid,
                f"Errors: {errors[:5]}")


def main():
    banner("OverCR v0.3.0 — KnowER Claim Review Tests")
    print(f"  Core dir: {_CORE_DIR}")

    test_claim_review_happy_path()
    test_claim_review_governance()
    test_claim_review_malformed()
    test_claim_review_timeout()
    test_claim_review_routing()
    test_claim_review_worker_direct()

    banner("Test Results")
    if _FAILED:
        print("  FAILED: Some tests did not pass.")
        print("  Review the FAIL entries above for details.")
        sys.exit(1)
    else:
        print("  ALL PASSED: Claim review tests passed.")
        sys.exit(0)


if __name__ == "__main__":
    main()