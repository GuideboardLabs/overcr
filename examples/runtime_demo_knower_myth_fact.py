#!/usr/bin/env python3
"""
OverCR v0.3.0 Runtime Demo — KnowER Myth/Fact Classification

This demo exercises KnowER's new knower_myth_fact packet type:

  1. Register KnowER in the WorkerRegistry with v0.3.0 capabilities
  2. Create a myth_fact task (myth_fact domain)
  3. Invoke the KnowER worker as a live subprocess
  4. Validate the response packet (6-level validator)
  5. Route through OverCR (always routes to operator for review)
  6. Produce operator-facing summary with research brief

What is EXECUTABLE (real logic, real I/O):
  - KnowER worker subprocess invocation (real Python process)
  - Full runtime pipeline: create → invoke → validate → route
  - Task record creation on filesystem
  - Packet validation (6-level)
  - Audit log entries (append-only JSONL)
  - Operator-facing summary with gate-authenticated governance

What remains SIMULATED:
  - The task instruction and input_context are synthetic
  - KnowER produces structured template responses based on instruction keywords

Usage:
  cd $OVERCR_ROOT
  python3 examples/runtime_demo_knower_myth_fact.py

  Or with a custom workspace:
  python3 examples/runtime_demo_knower_myth_fact.py --workspace /tmp/overcr-myth-fact-demo
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


# ── Global workspace path ──────────────────────────────────────────
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
    args = sys.argv[1:]
    for i in range(len(args)):
        if args[i] == "--workspace" and i + 1 < len(args):
            workspace = args[i + 1]

    if not workspace:
        import tempfile
        workspace = tempfile.mkdtemp(prefix="overcr-myth-fact-demo-")

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
    shutil.copy2(str(CORE_DIR / "tools" / "validate_packet.py"),
                 os.path.join(tools_dir, "validate_packet.py"))

    # Initialize task counter
    with open(os.path.join(workspace, "orchestration", "task_counter.json"), "w") as f:
        json.dump({"last_task_id": "0000", "last_updated": datetime.now(timezone.utc).isoformat()}, f)

    banner("OverCR v0.3.0 Runtime Demo — KnowER Myth/Fact Classification")

    # ── Step 1: Register KnowER worker ──────────────────────────────
    section("Step 1: Register KnowER Worker (v0.3.0)")
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
    print(f"  Packet types: {summary['packet_types']}")

    # ── Step 2: Initialize OverCR runtime ──────────────────────────
    section("Step 2: Initialize OverCR Runtime")
    rt = OverCRRuntime(workspace)

    # ── Step 3: Create myth_fact task ───────────────────────────────
    section("Step 3: Create Myth/Fact Classification Task")
    myth_fact_input = {
        "topic": "Regional economic growth myths and facts",
        "statements": [
            "The region has lost 40% of its manufacturing jobs since 2005",
            "The county offers no tax incentives for new businesses",
            "Population has been declining for the last decade",
            "The regional university is expanding its engineering program by 50%",
            "All major employers in the region are downsizing",
        ],
        "source_texts": [
            "Census data: Manufacturing employment declined 28% from 2005 to 2022.",
            "County economic development: Three active tax incentive programs listed.",
            "Census estimates: 0.3-0.5% annual population decline.",
            "Employment data: 3 of 8 major employers grew, 2 stable, 3 reduced.",
        ],
    }

    task_id = rt.create_task(
        domain="myth_fact",
        description="Classify statements about regional economic growth as myth/fact/partial_truth/unverified",
        instruction="Classify each statement as myth, fact, partial_truth, or unverified. Rate confidence and source quality. Identify unknowns. Provide an operator-facing research brief.",
        input_context=myth_fact_input,
    )
    print(f"  Created task: {task_id}")
    task = rt.task_store.load_task(task_id)
    print(f"  Task state: {task['state']}")
    print(f"  Task subagent: {task['subagent']}")

    # ── Step 4: Invoke KnowER worker ────────────────────────────────
    section("Step 4: Invoke KnowER Worker (Myth/Fact)")
    adapter = SubagentAdapter(str(CORE_DIR))
    request_packet = rt.generate_request_packet(task_id)
    print(f"  Request domain: {request_packet.get('domain', 'myth_fact')}")

    result = adapter.invoke("knower", request_packet, task_id, timeout=30.0)
    print(f"  Worker exit code: {result.exit_code}")
    print(f"  Worker success: {result.success}")

    if not result.success:
        print(f"  ERROR: Worker failed — stderr: {result.stderr_summary[:200]}")
        return

    # ── Step 5: Validate response ───────────────────────────────────
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

    # ── Step 6: Receive and route ────────────────────────────────────
    section("Step 6: Receive Response and Route")
    rt.receive_response(task_id, response_packet)
    rt.validate_response(task_id)

    routing = rt.route(task_id)
    print(f"  Routed to: {routing['target']}")
    print(f"  Condition: {routing['condition']}")

    # ── Step 7: Operator summary ─────────────────────────────────────
    section("Step 7: Operator-Facing Summary")
    op_summary = rt.operator_summary(task_id)
    print(json.dumps(op_summary, indent=2, default=str))

    # ── Step 8: Myth/fact output details ─────────────────────────────
    section("Step 8: Myth/Fact Output Details")
    mf_data = response_packet.get("myth_fact_data", {})
    print(f"  Topic: {mf_data.get('topic', 'N/A')}")
    items = mf_data.get("items", [])
    print(f"  Statements classified: {len(items)}")
    for i, item in enumerate(items):
        print(f"    [{i+1}] {item.get('classification', '?').upper():16s} "
              f"conf={item.get('confidence', '?')} "
              f"src={item.get('source_quality', '?'):12s} "
              f"| {item.get('statement', '')[:55]}...")
    brief = mf_data.get("operator_brief", "")
    if brief:
        print(f"\n  Operator Research Brief:\n    {brief[:250]}...")

    # ── Done ─────────────────────────────────────────────────────────
    banner("Demo Complete")
    print(f"  Workspace: {workspace}")
    print(f"  Task ID: {task_id}")
    print(f"  Packet type: knower_myth_fact")
    print(f"  Classification types: myth, fact, partial_truth, unverified")
    print(f"  Source quality types: primary, secondary, tertiary, unverified")
    print(f"  New domain: myth_fact")
    print()


if __name__ == "__main__":
    main()