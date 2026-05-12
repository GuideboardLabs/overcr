#!/usr/bin/env python3
"""
OverCR v0.2.1 Runtime Demo — Live KnowER Worker

This demo exercises the full runtime pipeline with a LIVE KnowER subagent worker:
  1. Register KnowER in the WorkerRegistry with proper capabilities
  2. Create a KnowER research task (research domain)
  3. Invoke the KnowER worker as a live subprocess
  4. Worker receives request packet via stdin, produces response via stdout
  5. Validate the response packet (6-level validator)
  6. Route through OverCR
  7. Produce operator-facing summary
  8. Repeat for an assessment task (analysis domain)
  9. Repeat for a myth_separation task (required_packet_type override)
  10. Clean up workspace

What is EXECUTABLE (real logic, real I/O):
  - KnowER worker subprocess invocation (real Python process)
  - Worker request/response via stdin/stdout JSON
  - Worker timeout enforcement
  - Stdout/stderr capture and audit summary
  - Task record creation on filesystem
  - Packet validation (6-level)
  - Audit log entries (append-only JSONL)
  - Operator-facing summary with gate-authenticated governance
  - WorkerRegistry registration and capability validation

What remains SIMULATED:
  - The task creation instruction is synthetic (not from a real knowledge base)
  - No real research, analysis, or myth separation is performed
  - KnowER produces structured template responses based on instruction keywords

Usage:
  cd $OVERCR_ROOT
  python3 examples/runtime_demo_live_knower.py

  Or with a custom workspace:
  python3 examples/runtime_demo_live_knower.py --workspace /tmp/overcr-live-knower-demo
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
    EXPECTED_CAPABILITIES,
    EXPECTED_PACKET_TYPES,
)


# ── Global workspace path (set in main, used by cleanup) ──────────
_workspace_to_clean = None


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


def make_workspace(workspace: str) -> str:
    """
    Create and populate a workspace directory for the demo.

    Sets up:
      - orchestration/tasks/
      - orchestration/task_counter.json
      - tools/validate_packet.py (copied from core)
    """
    if os.path.exists(workspace):
        shutil.rmtree(workspace)
    os.makedirs(workspace, exist_ok=True)

    orch_dir = os.path.join(workspace, "orchestration", "tasks")
    os.makedirs(orch_dir, exist_ok=True)

    with open(os.path.join(workspace, "orchestration", "task_counter.json"), "w") as f:
        json.dump(
            {"last_task_id": "0000", "last_updated": datetime.now(timezone.utc).isoformat()},
            f,
        )

    tools_dir = os.path.join(workspace, "tools")
    os.makedirs(tools_dir, exist_ok=True)
    shutil.copy2(
        str(CORE_DIR / "tools" / "validate_packet.py"),
        os.path.join(tools_dir, "validate_packet.py"),
    )

    return workspace


def cleanup_workspace():
    """Remove the workspace directory at exit (registered via atexit)."""
    global _workspace_to_clean
    if _workspace_to_clean and os.path.exists(_workspace_to_clean):
        shutil.rmtree(_workspace_to_clean, ignore_errors=True)
        print(f"  Workspace cleaned up: {_workspace_to_clean}")


def run_knower_task_pipeline(
    rt: OverCRRuntime,
    adapter: SubagentAdapter,
    domain: str,
    description: str,
    instruction: str,
    input_context: dict,
    required_packet_type: str | None = None,
    constraints: list[str] | None = None,
    phase_label: str = "",
):
    """
    Run a full KnowER task through the pipeline:
      create -> acknowledge -> invoke -> receive -> validate -> route -> summary

    Returns the completed task dict, or None on failure.
    """
    banner_text = phase_label or f"KnowER {domain} Task Pipeline"
    section(banner_text)

    # ── Create Task ────────────────────────────────────────────
    section(f"Create KnowER {domain} Task")

    task = rt.create_task(
        domain=domain,
        description=description,
        instruction=instruction,
        input_context=input_context,
        constraints=constraints,
        required_packet_type=required_packet_type,
    )
    task = rt.simulate_acknowledge(task["task_id"])
    print_task_state(task, "created+acknowledged")

    # ── Invoke KnowER Worker ───────────────────────────────────
    section(f"Invoke KnowER Worker — {domain}")

    print(f"  Invoking worker for task {task['task_id']}...")
    result = adapter.invoke_for_task(rt, task["task_id"], timeout=30.0)

    print(f"  Worker success      : {result['success']}")
    print(f"  Worker exit_code    : {result['exit_code']}")
    print(f"  Worker timed_out    : {result['timed_out']}")
    print(f"  Worker stdout_summary: {result['stdout_summary'][:200]}")
    print(f"  Worker stderr_summary: {result['stderr_summary'][:200]}")
    if result.get("error"):
        print(f"  Worker error        : {result['error']}")

    if not result["success"]:
        print(f"\n  Worker invocation FAILED. Cannot proceed.")
        print(f"  Error: {result.get('error', 'unknown')}")
        return None

    # ── Receive Response Packet ─────────────────────────────────
    section(f"Receive Worker Response Packet — {domain}")

    response_packet = result["response_packet"]
    print(f"  Packet type   : {response_packet.get('packet_type')}")
    print(f"  Source        : {response_packet.get('source')}")
    print(f"  Target       : {response_packet.get('target')}")
    print(f"  Task ID      : {response_packet.get('task_id')}")
    print(f"  Summary      : {response_packet.get('summary', '')[:100]}")
    print(f"  Approval req : {response_packet.get('approval_required')}")

    task = rt.receive_response(task["task_id"], response_packet)
    print_task_state(task, "response_received")

    # ── Validate Response Packet ────────────────────────────────
    section(f"Validate Response Packet (6-Level Validator) — {domain}")

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
        return None

    # ── Route the Task ──────────────────────────────────────────
    section(f"Route the Task — {domain}")

    route = rt.route(task["task_id"])
    print(f"  Routing target: {route['routing_target']}")
    print(f"  Routing reason: {route['reason']}")
    print(f"  Creates downstream: {route.get('creates_downstream_task', False)}")

    task = rt.get_task(task["task_id"])
    print(f"  Task final state: {task['state']}")

    # ── Operator Summary ────────────────────────────────────────
    section(f"Operator Summary — {domain}")

    summary = rt.operator_summary(task["task_id"])
    print(json.dumps(summary, indent=2))

    # ── Audit Trail ─────────────────────────────────────────────
    section(f"Audit Trail — {domain}")

    audit_entries = rt.get_audit_trail(task_id=task["task_id"], limit=50)
    print(f"  Audit entries: {len(audit_entries)}")
    for e in audit_entries:
        etype = e.get("entry_type", "?")
        ts = e.get("timestamp", "")[11:19]
        details = e.get("details", {})
        if etype == "state_transition":
            print(
                f"    {ts} [{etype}] {details.get('from_state')} -> "
                f"{details.get('to_state')}: {details.get('note', '')[:60]}"
            )
        else:
            print(f"    {ts} [{etype}]: {str(details)[:80]}")

    return task


def main():
    global _workspace_to_clean

    workspace = (
        sys.argv[2]
        if len(sys.argv) > 2 and sys.argv[1] == "--workspace"
        else "/tmp/overcr-live-knower-demo"
    )
    _workspace_to_clean = workspace

    # Register cleanup
    atexit.register(cleanup_workspace)

    # ── Set up workspace ────────────────────────────────────────
    make_workspace(workspace)

    banner("OverCR v0.2.1 — Live KnowER Worker Demo")
    print(f"  Workspace : {workspace}")
    print(f"  Core Dir  : {CORE_DIR}")
    print(f"  Time       : {datetime.now(timezone.utc).isoformat()}")
    print(f"  Purpose    : Demonstrate live KnowER subagent worker execution")
    print(f"  Worker     : KnowER (subagents/knower/worker.py)")
    print(f"  Domains    : research, analysis, myth_separation")

    # ── Initialize Runtime and Adapter ───────────────────────────
    rt = OverCRRuntime(workspace)
    adapter = SubagentAdapter(str(CORE_DIR))

    # ═════════════════════════════════════════════════════════════
    # PHASE 1: Register KnowER in the WorkerRegistry
    # ═════════════════════════════════════════════════════════════
    section("Phase 1: Register KnowER in WorkerRegistry")

    registry = WorkerRegistry()

    knower_registration = WorkerRegistration(
        subagent="knower",
        version="0.2.1",
        supported_packet_types=frozenset({
            "knower_research",
            "knower_assessment",
            "knower_myth_separation",
        }),
        capability_flags=KNOWER_CAPABILITIES,
        runtime_compat_version=RUNTIME_COMPAT_VERSION,
        worker_path="subagents/knower/worker.py",
    )

    print(f"  Registering KnowER worker...")
    print(f"    subagent              : {knower_registration.subagent}")
    print(f"    version               : {knower_registration.version}")
    print(f"    supported_packet_types: {sorted(knower_registration.supported_packet_types)}")
    print(f"    capability_flags      : {sorted(knower_registration.capability_flags)}")
    print(f"    runtime_compat_version: {knower_registration.runtime_compat_version}")
    print(f"    worker_path           : {knower_registration.worker_path}")

    reg_result = registry.register(knower_registration)
    print(f"  Registration result: {reg_result}")

    # ── Validate capabilities ────────────────────────────────────
    cap_check = validate_capabilities(knower_registration)
    print(f"  Capability validation: {'PASS' if cap_check.valid else 'FAIL'}")
    if cap_check.errors:
        for e in cap_check.errors:
            print(f"    ERROR: {e}")
    if cap_check.warnings:
        for w in cap_check.warnings:
            print(f"    WARN:  {w}")

    # ── Validate packet types ────────────────────────────────────
    pkt_check = validate_packet_types(knower_registration)
    print(f"  Packet type validation: {'PASS' if pkt_check.valid else 'FAIL'}")
    if pkt_check.errors:
        for e in pkt_check.errors:
            print(f"    ERROR: {e}")
    if pkt_check.warnings:
        for w in pkt_check.warnings:
            print(f"    WARN:  {w}")

    # ── Capability summary ───────────────────────────────────────
    cap_summary = get_capability_summary(knower_registration)
    print(f"  Capability summary:")
    print(f"    meets_requirements  : {cap_summary['meets_requirements']}")
    print(f"    safety_profile      : {cap_summary['safety_profile']}")

    # ── Registry lookups ─────────────────────────────────────────
    print(f"  Registry lookup for 'knower': {registry.lookup('knower') is not None}")
    print(f"  Registry is_registered('knower'): {registry.is_registered('knower')}")
    print(f"  Packet type owner for 'knower_research': {registry.packet_type_owner('knower_research')}")
    print(f"  Packet type owner for 'knower_assessment': {registry.packet_type_owner('knower_assessment')}")
    print(f"  Packet type owner for 'knower_myth_separation': {registry.packet_type_owner('knower_myth_separation')}")
    print(f"  knower supports 'knower_research': {registry.supports_packet_type('knower', 'knower_research')}")
    print(f"  knower supports 'knower_assessment': {registry.supports_packet_type('knower', 'knower_assessment')}")
    print(f"  knower supports 'knower_myth_separation': {registry.supports_packet_type('knower', 'knower_myth_separation')}")

    # ═════════════════════════════════════════════════════════════
    # PHASE 2: Verify KnowER Worker Is Available
    # ═════════════════════════════════════════════════════════════
    section("Phase 2: Verify KnowER Worker Is Available")

    knower_path = adapter.resolve_worker("knower")
    print(f"  KnowER worker path: {knower_path}")
    print(f"  KnowER worker exists: {knower_path is not None and knower_path.exists()}")
    print(f"  KnowER has live worker: {adapter.has_live_worker('knower')}")
    print(f"  Research domain has live worker: {adapter.has_live_worker_for_domain('research')}")
    print(f"  Analysis domain has live worker: {adapter.has_live_worker_for_domain('analysis')}")

    if knower_path is None:
        print("\n  ERROR: KnowER worker not found. Cannot proceed with live demo.")
        return 1

    # ═════════════════════════════════════════════════════════════
    # PHASE 3: KnowER Research Task
    # ═════════════════════════════════════════════════════════════
    research_task = run_knower_task_pipeline(
        rt=rt,
        adapter=adapter,
        domain="research",
        description="KnowER research — evaluate reputation signals for outreach target",
        instruction="Research the reputation and public signals of the specified entity. "
                    "Identify reliability ratings, potential yield scores, and any gaps in available evidence. "
                    "Focus on publicly verifiable claims with source citations.",
        input_context={
            "entity": "Acme Corp",
            "topic": "Reputation and public signals analysis for Acme Corp",
            "focus": "yield assessment and reliability verification",
        },
        phase_label="KnowER Research Task (domain=research)",
    )

    if research_task is None:
        print("\n  Research task pipeline FAILED. Skipping remaining tasks.")
        return 1

    # ═════════════════════════════════════════════════════════════
    # PHASE 4: KnowER Assessment Task
    # ═════════════════════════════════════════════════════════════
    assessment_task = run_knower_task_pipeline(
        rt=rt,
        adapter=adapter,
        domain="analysis",
        description="KnowER assessment — verify claims about entity reliability",
        instruction="Assess and verify whether the claims about this entity's reliability "
                    "are confirmed, likely, possible, speculative, or debunked. "
                    "Provide a verdict with supporting evidence and confidence rating.",
        input_context={
            "entity": "Acme Corp",
            "claim": "Acme Corp has a verified and reputable public presence",
            "focus": "claim verification and verdict assessment",
        },
        phase_label="KnowER Assessment Task (domain=analysis)",
    )

    if assessment_task is None:
        print("\n  Assessment task pipeline FAILED. Continuing to myth separation.")

    # ═════════════════════════════════════════════════════════════
    # PHASE 5: KnowER Myth Separation Task
    # ═════════════════════════════════════════════════════════════
    myth_task = run_knower_task_pipeline(
        rt=rt,
        adapter=adapter,
        domain="research",
        description="KnowER myth separation — separate myth from fact for entity claims",
        instruction="Separate myths and rumors from verified facts about this topic. "
                    "Identify commonly held beliefs that may not be supported by evidence, "
                    "provide debunking status, and list verified facts with source citations.",
        input_context={
            "entity": "Acme Corp",
            "topic": "Common misconceptions and myths about Acme Corp",
            "focus": "myth/fact separation and debunking",
        },
        required_packet_type="knower_myth_separation",
        phase_label="KnowER Myth Separation Task (required_packet_type=knower_myth_separation)",
    )

    if myth_task is None:
        print("\n  Myth separation task pipeline FAILED.")

    # ═════════════════════════════════════════════════════════════
    # SUMMARY
    # ═════════════════════════════════════════════════════════════
    banner("Live KnowER Worker Demo — Complete")

    print("\n  v0.2.1 capabilities demonstrated:")
    print("  1. KnowER registered in WorkerRegistry with validated capabilities")
    print("  2. KnowER worker invoked as live subprocess (3 task types)")
    print("  3. Worker received request packet via stdin")
    print("  4. Worker produced response packet via stdout")
    print("  5. Response packet validated by 6-level validator")
    print("  6. Task routed through OverCR state machine")
    print("  7. Operator-facing summary with gate-authenticated governance")
    print("  8. Full audit trail written to filesystem")
    print("  9. Myth separation task used required_packet_type override")
    print()
    print("  Task types demonstrated:")
    print("    - knower_research  (domain=research)")
    print("    - knower_assessment (domain=analysis)")
    print("    - knower_myth_separation (required_packet_type=knower_myth_separation)")
    print()
    print("  What is now EXECUTABLE (was simulated in v0.1.0):")
    print("    - KnowER subagent worker process spawning")
    print("    - Worker request/response via subprocess stdin/stdout")
    print("    - Worker timeout enforcement with process kill")
    print("    - Stdout/stderr capture with audit-safe summaries")
    print("    - WorkerRegistry registration with capability validation")
    print()
    print("  What remains SIMULATED:")
    print("    - No real research, analysis, or myth separation performed")
    print("    - KnowER produces structured template responses from instruction keywords")
    print("    - No web crawling or data gathering")
    print("    - No outbound contact or autonomous action")

    return 0


if __name__ == "__main__":
    sys.exit(main())