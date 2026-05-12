#!/usr/bin/env python3
"""
OverCR v0.2.0 Runtime Demo — Live CodER Worker

This demo exercises the full runtime pipeline with a LIVE subagent worker:
  1. Create a CodER task (code/inspection domain)
  2. Invoke the CodER worker as a live subprocess
  3. Worker receives request packet via stdin, produces response via stdout
  4. Validate the response packet (6-level validator)
  5. Route through OverCR
  6. Produce operator-facing summary
  7. Write audit trail

What is EXECUTABLE (real logic, real I/O):
  - CodER worker subprocess invocation (real Python process)
  - Worker request/response via stdin/stdout JSON
  - Worker timeout enforcement
  - Stdout/stderr capture and audit summary
  - Task record creation on filesystem
  - Packet validation (6-level)
  - Audit log entries (append-only JSONL)
  - Operator-facing summary with gate-authenticated governance

What remains SIMULATED:
  - The task creation instruction is synthetic (not from a real codebase scan)
  - No files are actually modified by the worker (plans only)

Usage:
  cd $OVERCR_ROOT
  python3 examples/runtime_demo_live_coder.py

  Or with a custom workspace:
  python3 examples/runtime_demo_live_coder.py --workspace /tmp/overcr-live-demo
"""

import json
import sys
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

# Add core to path
CORE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CORE_DIR))

from runtime.overcr_runtime import OverCRRuntime
from runtime.subagent_adapter import SubagentAdapter


def banner(text: str, width: int = 76):
    print(f"\n{'=' * width}")
    print(f"  {text}")
    print(f"{'=' * width}")


def section(text: str):
    print(f"\n--- {text} ---")


def print_task_state(task: dict, label: str = ""):
    prefix = f"[{label}] " if label else ""
    print(f"  {prefix}task_id    : {task['task_id']}")
    print(f"  {prefix}state       : {task['state']}")
    print(f"  {prefix}subagent    : {task['assigned_subagent']}")
    print(f"  {prefix}domain      : {task['domain']}")
    print(f"  {prefix}description : {task['description'][:80]}")


def main():
    workspace = sys.argv[2] if len(sys.argv) > 2 and sys.argv[1] == "--workspace" else "/tmp/overcr-live-coder-demo"

    # Clean workspace
    if os.path.exists(workspace):
        shutil.rmtree(workspace)
    os.makedirs(workspace, exist_ok=True)
    orch_dir = os.path.join(workspace, "orchestration", "tasks")
    os.makedirs(orch_dir, exist_ok=True)
    with open(os.path.join(workspace, "orchestration", "task_counter.json"), "w") as f:
        json.dump({"last_task_id": "0000", "last_updated": datetime.now(timezone.utc).isoformat()}, f)

    # Copy validator into workspace
    tools_dir = os.path.join(workspace, "tools")
    os.makedirs(tools_dir, exist_ok=True)
    shutil.copy2(str(CORE_DIR / "tools" / "validate_packet.py"), os.path.join(tools_dir, "validate_packet.py"))

    banner("OverCR v0.2.0 — Live CodER Worker Demo")
    print(f"  Workspace : {workspace}")
    print(f"  Time       : {datetime.now(timezone.utc).isoformat()}")
    print(f"  Purpose    : Demonstrate live subagent worker execution")
    print(f"  Worker     : CodER (subagents/coder/worker.py)")

    rt = OverCRRuntime(workspace)
    adapter = SubagentAdapter(str(CORE_DIR))  # Use core dir as root for worker resolution

    # ═══════════════════════════════════════════════════════════
    # PHASE 1: Verify CodER Worker Is Available
    # ═══════════════════════════════════════════════════════════
    section("Phase 1: Verify CodER Worker Is Available")

    coder_path = adapter.resolve_worker("coder")
    print(f"  CodER worker path: {coder_path}")
    print(f"  CodER worker exists: {coder_path is not None and coder_path.exists()}")
    print(f"  CodER has live worker: {adapter.has_live_worker('coder')}")
    print(f"  Code domain has live worker: {adapter.has_live_worker_for_domain('code')}")

    if coder_path is None:
        print("\n  ERROR: CodER worker not found. Cannot proceed with live demo.")
        return 1

    # ═══════════════════════════════════════════════════════════
    # PHASE 2: Create a CodER Task
    # ═══════════════════════════════════════════════════════════
    section("Phase 2: Create a CodER Inspection Task")

    task = rt.create_task(
        domain="code",
        description="CodER code inspection — analyze input validation patterns",
        instruction="Inspect the input validation logic in the approval gate module. Identify any edge cases in the boundary enforcement that could allow a bypass.",
        input_context={
            "entity": "runtime/approval_gate.py",
            "focus": "boundary enforcement edge cases",
        },
    )
    task = rt.simulate_acknowledge(task["task_id"])
    print_task_state(task, "created+acknowledged")

    # ═══════════════════════════════════════════════════════════
    # PHASE 3: Invoke CodER Worker Live
    # ═══════════════════════════════════════════════════════════
    section("Phase 3: Invoke CodER Worker (Live Subprocess)")

    print(f"  Invoking worker for task {task['task_id']}...")
    result = adapter.invoke_for_task(rt, task["task_id"], timeout=30.0)

    print(f"  Worker success     : {result['success']}")
    print(f"  Worker exit_code    : {result['exit_code']}")
    print(f"  Worker timed_out    : {result['timed_out']}")
    print(f"  Worker stdout_summary: {result['stdout_summary'][:200]}")
    print(f"  Worker stderr_summary: {result['stderr_summary'][:200]}")
    if result.get("error"):
        print(f"  Worker error        : {result['error']}")

    if not result["success"]:
        print(f"\n  Worker invocation FAILED. Cannot proceed.")
        print(f"  Error: {result.get('error', 'unknown')}")
        return 1

    # ═══════════════════════════════════════════════════════════
    # PHASE 4: Receive Worker Response
    # ═══════════════════════════════════════════════════════════
    section("Phase 4: Receive Worker Response Packet")

    response_packet = result["response_packet"]
    print(f"  Packet type   : {response_packet.get('packet_type')}")
    print(f"  Source        : {response_packet.get('source')}")
    print(f"  Target       : {response_packet.get('target')}")
    print(f"  Task ID      : {response_packet.get('task_id')}")
    print(f"  Summary      : {response_packet.get('summary', '')[:100]}")
    print(f"  Approval req : {response_packet.get('approval_required')}")

    task = rt.receive_response(task["task_id"], response_packet)
    print_task_state(task, "response_received")

    # ═══════════════════════════════════════════════════════════
    # PHASE 5: Validate Response Packet
    # ═══════════════════════════════════════════════════════════
    section("Phase 5: Validate Response Packet (6-Level Validator)")

    validation = rt.validate_response(task["task_id"])
    print(f"  Validation result: {'PASS' if validation['valid'] else 'FAIL'}")
    print(f"  Errors:   {len(validation['errors'])}")
    for e in validation.get("errors", []):
        print(f"    ERROR: {e}")
    print(f"  Warnings: {len(validation['warnings'])}")
    for w in validation.get("warnings", []):
        print(f"    WARN:  {w}")

    if not validation["valid"]:
        print(f"\n  Worker response FAILED validation!")
        print(f"  Task state: {rt.get_task(task['task_id'])['state']}")
        return 1

    # ═══════════════════════════════════════════════════════════
    # PHASE 6: Route the Task
    # ═══════════════════════════════════════════════════════════
    section("Phase 6: Route the Task")

    route = rt.route(task["task_id"])
    print(f"  Routing target: {route['routing_target']}")
    print(f"  Routing reason: {route['reason']}")
    print(f"  Creates downstream: {route.get('creates_downstream_task', False)}")

    task = rt.get_task(task["task_id"])
    print(f"  Task final state: {task['state']}")

    # ═══════════════════════════════════════════════════════════
    # PHASE 7: Operator Summary
    # ═══════════════════════════════════════════════════════════
    section("Phase 7: Operator Summary")

    summary = rt.operator_summary(task["task_id"])
    print(json.dumps(summary, indent=2))

    # ═══════════════════════════════════════════════════════════
    # PHASE 8: Audit Trail
    # ═══════════════════════════════════════════════════════════
    section("Phase 8: Audit Trail")

    audit_entries = rt.get_audit_trail(task_id=task["task_id"], limit=50)
    print(f"  Audit entries: {len(audit_entries)}")
    for e in audit_entries:
        etype = e.get("entry_type", "?")
        ts = e.get("timestamp", "")[11:19]
        details = e.get("details", {})
        if etype == "state_transition":
            print(f"    {ts} [{etype}] {details.get('from_state')} -> {details.get('to_state')}: {details.get('note', '')[:60]}")
        else:
            print(f"    {ts} [{etype}]: {str(details)[:80]}")

    # ═══════════════════════════════════════════════════════════
    # SUMMARY
    # ═══════════════════════════════════════════════════════════
    banner("Live CodER Worker Demo — Complete")

    print("\n  v0.2.0 capabilities demonstrated:")
    print("  1. CodER worker invoked as live subprocess")
    print("  2. Worker received request packet via stdin")
    print("  3. Worker produced response packet via stdout")
    print("  4. Response packet validated by 6-level validator")
    print("  5. Task routed through OverCR state machine")
    print("  6. Operator-facing summary with gate-authenticated governance")
    print("  7. Full audit trail written to filesystem")
    print()
    print("  What is now EXECUTABLE (was simulated in v0.1.0):")
    print("    - Subagent worker process spawning (CodER)")
    print("    - Worker request/response via subprocess stdin/stdout")
    print("    - Worker timeout enforcement with process kill")
    print("    - Stdout/stderr capture with audit-safe summaries")
    print()
    print("  What remains SIMULATED:")
    print("    - CryER, PypER, KnowER still use simulated responses")
    print("    - No web crawling or data gathering")
    print("    - No outbound contact or autonomous action")

    return 0


if __name__ == "__main__":
    sys.exit(main())