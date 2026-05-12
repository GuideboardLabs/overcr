#!/usr/bin/env python3
"""
OverCR v0.3.0 Runtime Demo — KnowER Claim Review

This demo exercises the full runtime pipeline with KnowER's new
knower_claim_review packet type:

  1. Register KnowER in the WorkerRegistry with v0.3.0 capabilities
  2. Create a claim_review task (claim_review domain)
  3. Invoke the KnowER worker as a live subprocess
  4. Validate the response packet (6-level validator)
  5. Route through OverCR
  6. Produce operator-facing summary
  7. Clean up workspace

What is EXECUTABLE (real logic, real I/O):
  - KnowER worker subprocess invocation (real Python process)
  - Full runtime pipeline: create → invoke → validate → route
  - Task record creation on filesystem
  - Packet validation (6-level)
  - Audit log entries (append-only JSONL)
  - Operator-facing summary with gate-authenticated governance

What remains SIMULATED:
  - The task instruction and input_context are synthetic
  - No real knowledge base or external research is performed
  - KnowER produces structured template responses based on instruction keywords

Usage:
  cd $OVERCR_ROOT
  python3 examples/runtime_demo_knower_claim_review.py

  Or with a custom workspace:
  python3 examples/runtime_demo_knower_claim_review.py --workspace /tmp/overcr-claim-review-demo
"""

import atexit
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add core to path
CORE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CORE_DIR))

from runtime.overcr_runtime import OverCRRuntime
from runtime.subagent_adapter import SubagentAdapter
from runtime.worker_runner import WorkerRunner
from runtime.worker_registry import (
    WorkerRegistry,
    WorkerRegistration,
    KNOWER_CAPABILITIES,
    RUNTIME_COMPAT_VERSION,
)
from runtime.worker_capabilities import (
    validate_capabilities,
    validate_packet_types,
    get_capability_summary,
)


# ── Global workspace path (set in main, used by cleanup) ──────────
_workspace_to_clean = None


def banner(text: str, width: int = 76):
    print(f"\n{'=' * width}")
    print(f"  {text}")
    print(f"{'=' * width}")


def section(text: str):
    print(f"\n--- {text} ---")


def cleanup():
    global _workspace_to_clean
    if _workspace_to_clean and os.path.exists(_workspace_to_clean):
        shutil.rmtree(_workspace_to_clean, ignore_errors=True)


def main():
    global _workspace_to_clean

    # Parse workspace arg
    workspace = None
    for i, arg in enumerate(sys.argv[1:]):
        if arg == "--workspace" and i + 1 < len(sys.argv):
            workspace = sys.argv[i + 2]  # offset by 1 for argv

    # Fallback: parse manually
    args = sys.argv[1:]
    for i in range(len(args)):
        if args[i] == "--workspace" and i + 1 < len(args):
            workspace = args[i + 1]

    if not workspace:
        import tempfile
        workspace = tempfile.mkdtemp(prefix="overcr-claim-review-demo-")

    _workspace_to_clean = workspace
    atexit.register(cleanup)

    # Clean workspace if it exists
    if os.path.exists(workspace):
        shutil.rmtree(workspace)
    os.makedirs(workspace, exist_ok=True)

    # Create required directories
    orch_dir = os.path.join(workspace, "orchestration", "tasks")
    os.makedirs(orch_dir, exist_ok=True)
    tools_dir = os.path.join(workspace, "tools")
    os.makedirs(tools_dir, exist_ok=True)

    # Copy validator
    import shutil as sh
    sh.copy2(str(CORE_DIR / "tools" / "validate_packet.py"),
             os.path.join(tools_dir, "validate_packet.py"))

    # Initialize task counter
    with open(os.path.join(workspace, "orchestration", "task_counter.json"), "w") as f:
        json.dump({"last_task_id": "0000", "last_updated": datetime.now(timezone.utc).isoformat()}, f)

    banner("OverCR v0.3.0 Runtime Demo — KnowER Claim Review")

    # ── Step 1: Register KnowER worker ──────────────────────────────
    section("Step 1: Register KnowER Worker")
    registry = WorkerRegistry()
    knower_reg = WorkerRegistration(
        subagent="knower",
        version="0.3.0",
        supported_packet_types=frozenset({
            "knower_research", "knower_assessment", "knower_myth_separation",
            "knower_claim_review", "knower_myth_fact",
        }),
        capability_flags=KNOWER_CAPABILITIES,
        runtime_compat_version=RUNTIME_COMPAT_VERSION,
        worker_path="subagents/knower/worker.py",
    )
    result = registry.register(knower_reg)
    print(f"  Registration: {result}")
    summary = get_capability_summary(knower_reg)
    print(f"  Capability summary: {json.dumps(summary, indent=2)}")

    # ── Step 2: Initialize OverCR runtime ──────────────────────────
    section("Step 2: Initialize OverCR Runtime")
    rt = OverCRRuntime(workspace)

    # ── Step 3: Create claim_review task ────────────────────────────
    section("Step 3: Create Claim Review Task")
    claim_review_input = {
        "topic": "Regional infrastructure investment claims",
        "claims_to_review": [
            "The county has allocated $12M for downtown renovation",
            "The renovation will increase commercial occupancy by 30%",
            "Local businesses oppose the construction timeline",
            "A competing developer is planning a similar project",
        ],
        "source_texts": [
            "Budget document excerpt: 'Section 3.1 allocates $12,034,500 for downtown capital improvements in FY2026.'",
            "Regional development report: 'Downtown vacancy rates declined from 22% to 15% over the prior renovation cycle.'",
        ],
    }

    task_id = rt.create_task(
        domain="claim_review",
        description="Classify claims about regional infrastructure investment",
        instruction="Review and classify the following claims as fact, inference, assumption, or rumor. Rate confidence and source quality. Identify unknowns and verification needs.",
        input_context=claim_review_input,
    )
    print(f"  Created task: {task_id}")
    task = rt.task_store.load_task(task_id)
    print(f"  Task state: {task['state']}")
    print(f"  Task subagent: {task['subagent']}")

    # ── Step 4: Invoke KnowER worker ────────────────────────────────
    section("Step 4: Invoke KnowER Worker (Claim Review)")
    adapter = SubagentAdapter(str(CORE_DIR))
    request_packet = rt.generate_request_packet(task_id)
    print(f"  Request packet type: {request_packet.get('domain', 'claim_review')}")
    print(f"  Instruction: {request_packet.get('instruction', '')[:80]}...")

    result = adapter.invoke("knower", request_packet, task_id, timeout=30.0)
    print(f"  Worker exit code: {result.exit_code}")
    print(f"  Worker success: {result.success}")

    if not result.success:
        print(f"  ERROR: Worker failed — stderr: {result.stderr_summary[:200]}")
        print("  Demo cannot proceed with failed worker.")
        return

    # ── Step 5: Validate response ──────────────────────────────────
    section("Step 5: Validate Response Packet")
    response_packet = result.response_packet
    print(f"  Packet type: {response_packet.get('packet_type', 'unknown')}")
    print(f"  Task ID: {response_packet.get('task_id', 'unknown')}")

    valid, errors, warnings = rt.validator.validate_packet(response_packet)
    print(f"  Validation: {'PASS' if valid else 'FAIL'}")
    if errors:
        for e in errors:
            print(f"    ERROR: {e}")
    if warnings:
        for w in warnings:
            print(f"    WARN:  {w}")

    if not valid:
        print("  Packet validation failed — cannot advance task state.")
        return

    # ── Step 6: Receive and route ───────────────────────────────────
    section("Step 6: Receive Response and Route")
    rt.receive_response(task_id, response_packet)
    rt.validate_response(task_id)

    routing = rt.route(task_id)
    print(f"  Routed to: {routing['target']}")
    print(f"  Condition: {routing['condition']}")

    # ── Step 7: Operator summary ────────────────────────────────────
    section("Step 7: Operator-Facing Summary")
    op_summary = rt.operator_summary(task_id)
    print(json.dumps(op_summary, indent=2, default=str))

    # ── Step 8: Claim review specifics ──────────────────────────────
    section("Step 8: Claim Review Output Details")
    cr_data = response_packet.get("claim_review_data", {})
    print(f"  Topic: {cr_data.get('topic', 'N/A')}")
    claims = cr_data.get("claims", [])
    print(f"  Claims reviewed: {len(claims)}")
    for i, claim in enumerate(claims):
        print(f"    [{i+1}] {claim.get('classification', '?').upper():12s} "
              f"conf={claim.get('confidence', '?')} "
              f"src={claim.get('source_quality', '?'):12s} "
              f"| {claim.get('text', '')[:60]}...")
    brief = cr_data.get("operator_brief", "")
    if brief:
        print(f"\n  Operator Brief:\n    {brief[:200]}...")

    # ── Done ────────────────────────────────────────────────────────
    banner("Demo Complete")
    print(f"  Workspace: {workspace}")
    print(f"  Task ID: {task_id}")
    print(f"  Audit entries: {len(rt.task_store.load_task(task_id).get('state_log', []))}")
    print(f"\n  Claim review packet type: knower_claim_review")
    print(f"  New domains: claim_review, myth_fact")
    print(f"  New fields: classification, source_quality, unknowns, operator_brief")
    print()


if __name__ == "__main__":
    main()