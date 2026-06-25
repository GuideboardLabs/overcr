#!/usr/bin/env python3
"""
OverCR v0.1.0 Runtime Demo — CryER → PypER Multi-Hop Flow

This demo exercises the full runtime pipeline:
  1. Create a CryER task (recon)
  2. Simulate CryER response packet
  3. Validate the response
  4. Route to PypER (downstream task)
  5. Simulate PypER approval packet
  6. Validate the PypER response
  7. Hit the approval gate — block final outbound action
  8. Write audit trail throughout
  9. Print operator-facing summary

What is EXECUTABLE (real logic, real I/O):
  - Task record creation on filesystem
  - Task ID assignment from counter
  - State machine transitions (all 12 states)
  - Packet validation (6-level validator)
  - Approval gate enforcement
  - Audit log entries (append-only JSONL)
  - Operator-facing summary generation
  - Outbound block check

What remains SIMULATED:
  - CryER response packet (synthetic, not from a live subagent)
  - PypER response packet (synthetic, not from a live subagent)
  - Subagent process spawning (none)
  - Web crawling / data gathering (none)
  - Any outbound action (blocked by approval gate)

Usage:
  cd $OVERCR_ROOT
  python examples/runtime_demo_cryer_to_pyper.py

  Or with a custom workspace (for clean demo):
  python examples/runtime_demo_cryer_to_pyper.py --workspace /tmp/overcr-demo
"""

import json
import sys
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

# Add the core directory to the path
CORE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CORE_DIR))

from runtime.overcr_runtime import OverCRRuntime


def banner(text: str, width: int = 72):
    """Print a section banner."""
    print(f"\n{'=' * width}")
    print(f"  {text}")
    print(f"{'=' * width}")


def section(text: str):
    """Print a section header."""
    print(f"\n--- {text} ---")


def print_task_state(task: dict, label: str = ""):
    """Print key fields from a task record."""
    prefix = f"[{label}] " if label else ""
    print(f"  {prefix}task_id    : {task['task_id']}")
    print(f"  {prefix}state       : {task['state']}")
    print(f"  {prefix}subagent    : {task['assigned_subagent']}")
    print(f"  {prefix}domain      : {task['domain']}")
    print(f"  {prefix}description : {task['description'][:80]}...")
    print(f"  {prefix}revisions   : {task.get('revision_count', 0)}")


def print_validation(result: dict):
    """Print a validation result."""
    status = "PASS" if result["valid"] else "FAIL"
    print(f"  Validation: {status}")
    print(f"  Packet type : {result.get('packet_type', 'N/A')}")
    print(f"  Source      : {result.get('source', 'N/A')}")
    print(f"  Errors      : {len(result.get('errors', []))}")
    print(f"  Warnings    : {len(result.get('warnings', []))}")
    for e in result.get("errors", []):
        print(f"    ERROR: {e}")
    for w in result.get("warnings", []):
        print(f"    WARN:  {w}")


def print_audit_summary(entries: list[dict]):
    """Print a compact audit trail."""
    print(f"\n  Audit entries: {len(entries)}")
    for e in entries[-10:]:  # Last 10
        etype = e.get("entry_type", "?")
        tid = e.get("task_id", "?")
        ts = e.get("timestamp", "")[11:19]
        details = e.get("details", {})
        if etype == "state_transition":
            note = f"{details.get('from_state', '?')} -> {details.get('to_state', '?')}"
        elif etype == "validation_result":
            note = f"valid={details.get('valid')} errors={details.get('error_count', 0)}"
        elif etype == "routing_decision":
            note = f"-> {details.get('routing_target', '?')}"
        elif etype == "approval_action":
            note = f"{details.get('decision', '?')} by {details.get('operator', '?')}"
        else:
            note = str(details)[:60]
        print(f"    {ts} [{etype:>20}] {tid}: {note}")


def make_cryer_recon_packet(task_id: str) -> dict:
    """Synthesize a valid CryER recon response packet."""
    return {
        "packet_type": "cryer_recon",
        "version": "1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "cryer",
        "target": "overcr",
        "task_id": task_id,
        "summary": (
            "Recon on Example Business Group: strong yield (72/100). "
            "Active hiring, positive reviews with moderate response time, "
            "partial directory presence suggesting digital ops gaps."
        ),
        "recon_data": {
            "targets": [
                {
                    "entity": "Example Business Group",
                    "type": "business",
                    "signals": {
                        "reviews": {
                            "count": 124,
                            "sentiment": "positive",
                            "recency": "2026-05-01",
                            "sources": ["Public Review Platform A", "Regional Business Directory"],
                        },
                        "engagement": {
                            "social_presence": True,
                            "response_rate": "~60%",
                            "active_signals": [
                                "Regular social media updates (3x/week)",
                                "Seasonal promotion content",
                            ],
                        },
                        "hiring": {
                            "active": True,
                            "roles": ["Operations Coordinator", "Marketing Associate"],
                            "growth_signal": "growing",
                        },
                        "directory": {
                            "listed": True,
                            "directories": ["Public Directory A", "Regional Business Directory"],
                            "completeness": "partial",
                        },
                        "reputation": {
                            "yield_score": 72,
                            "confidence": 78,
                            "risk_flags": [
                                "Moderate review response time (2-3 days average)",
                                "Partial directory presence across platforms",
                            ],
                        },
                    },
                    "raw_sources": [
                        "https://example-directory.com/business/example-business-group",
                        "https://public-reviews.com/example-business-group",
                    ],
                }
            ]
        },
        "next_steps_recommendation": (
            "Submit to OverCR for outreach routing. "
            "Yield score 72 with actionable signals: growing team, "
            "moderate response gaps, partial digital presence suggesting "
            "room for operational improvement tools."
        ),
        "audit_trail": {
            "collection_timestamps": [
                datetime.now(timezone.utc).isoformat(),
            ],
            "methods_used": ["public_directory_crawl", "review_aggregation", "job_board_scan"],
        },
    }


def make_pyper_approval_packet(task_id: str, upstream_task_id: str) -> dict:
    """Synthesize a valid PypER approval response packet."""
    return {
        "packet_type": "pyper_approval",
        "version": "1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "pyper",
        "target": "overcr",
        "task_id": task_id,
        "upstream_task_id": upstream_task_id,
        "summary": (
            "Outreach draft for Example Business Group — consultative approach "
            "addressing growth-stage operational friction."
        ),
        "draft_data": {
            "prospects": [
                {
                    "entity": "Example Business Group",
                    "approach_type": "cold_email",
                    "personalization_signals": [
                        "Growing team — hiring Operations Coordinator and Marketing Associate",
                        "124 positive reviews but moderate response time suggesting capacity strain",
                        "Partial directory presence — consolidation opportunity",
                    ],
                    "drafts": [
                        {
                            "channel": "email",
                            "subject": "Helping Example Business Group streamline growth operations",
                            "body": (
                                "Hi [First Name],\n\n"
                                "I noticed Example Business Group is expanding — congrats on the "
                                "recent hires. With your team growing, I wanted to share how similar "
                                "organizations have streamlined their digital operations to handle "
                                "increased volume without adding friction.\n\n"
                                "Your reviews are strong (4.5 average across 124), but I noticed "
                                "response times could be faster — that's actually an area where "
                                "practices like yours have seen real improvement.\n\n"
                                "Would it be helpful to chat briefly?\n\n"
                                "Best,\n[Sender]"
                            ),
                            "tone": "consultative",
                            "evidence_citations": [
                                f"{upstream_task_id}: hiring signals — Operations Coordinator, Marketing Associate",
                                f"{upstream_task_id}: positive reviews, moderate response time (~60%)",
                                f"{upstream_task_id}: partial directory presence",
                            ],
                        }
                    ],
                    "yield_score": 72,
                    "fit_score": 80,
                }
            ]
        },
        "approval_required": True,
        "next_steps_recommendation": (
            "Present to operator for review and approval before any outbound action."
        ),
        "audit_trail": {
            "upstream_sources": [f"{upstream_task_id} (CryER recon)"],
            "draft_methods": ["evidence-backed personalization", "objection anticipation"],
            "review_count": 1,
        },
    }


def run_demo(workspace: str | None = None):
    """Run the full CryER → PypER demo."""

    # Use a clean workspace if specified, otherwise use the core directory
    if workspace:
        core_dir = workspace
        # Set up clean workspace
        os.makedirs(core_dir, exist_ok=True)
        orch_dir = os.path.join(core_dir, "orchestration", "tasks")
        os.makedirs(orch_dir, exist_ok=True)
        # Initialize task counter
        counter_path = os.path.join(core_dir, "orchestration", "task_counter.json")
        with open(counter_path, "w") as f:
            json.dump({"last_task_id": "0000", "last_updated": datetime.now(timezone.utc).isoformat()}, f)
    else:
        core_dir = str(CORE_DIR)

    # Ensure tools directory exists and validate_packet.py is accessible
    tools_dir = os.path.join(core_dir, "tools")
    if not os.path.exists(os.path.join(tools_dir, "validate_packet.py")):
        # Copy the validator from the real core dir if using a temp workspace
        if workspace:
            os.makedirs(tools_dir, exist_ok=True)
            src = str(CORE_DIR / "tools" / "validate_packet.py")
            dst = os.path.join(tools_dir, "validate_packet.py")
            if os.path.exists(src):
                shutil.copy2(src, dst)
            else:
                print(f"  WARNING: validate_packet.py not found at {src}")

    banner("OverCR v0.1.0 Runtime Demo — CryER to PypER")
    print(f"  Workspace : {core_dir}")
    print(f"  Time       : {datetime.now(timezone.utc).isoformat()}")
    print(f"  Scope      : Full multi-hop flow demo (simulated subagent responses)")

    rt = OverCRRuntime(core_dir)

    # ═══════════════════════════════════════════════════════════
    # PHASE 1: Create CryER Recon Task
    # ═══════════════════════════════════════════════════════════
    section("Phase 1: Create CryER Recon Task")
    task1 = rt.create_task(
        domain="recon",
        description="Public signal reconnaissance on Example Business Group",
        instruction=(
            "Conduct public signal reconnaissance on Example Business Group. "
            "Focus on reviews, engagement, hiring, and directory presence. "
            "Public signals only — no private data, no outbound contact."
        ),
        input_context={
            "entity": "Example Business Group",
            "type": "business",
            "focus_areas": ["reviews", "engagement", "hiring", "directory"],
            "upstream_task_id": None,
        },
    )
    print_task_state(task1, "CryER Task Created")

    # ═══════════════════════════════════════════════════════════
    # PHASE 2: Simulate CryER Acknowledgment + Response
    # ═══════════════════════════════════════════════════════════
    section("Phase 2: Simulate CryER Acknowledgment & Response")
    task1 = rt.simulate_acknowledge(task1["task_id"])
    print(f"  Acknowledged: {task1['task_id']} -> state={task1['state']}")

    # Simulate CryER producing a response packet
    cryer_packet = make_cryer_recon_packet(task1["task_id"])
    task1 = rt.receive_response(task1["task_id"], cryer_packet)
    print(f"  Response received: {task1['state']}")

    # ═══════════════════════════════════════════════════════════
    # PHASE 3: Validate CryER Response
    # ═══════════════════════════════════════════════════════════
    section("Phase 3: Validate CryER Response Packet")
    v1 = rt.validate_response(task1["task_id"])
    print_validation(v1)
    task1 = rt.get_task(task1["task_id"])
    print(f"  Task state after validation: {task1['state']}")

    # ═══════════════════════════════════════════════════════════
    # PHASE 4: Route CryER → PypER
    # ═══════════════════════════════════════════════════════════
    section("Phase 4: Routing Decision (CryER → PypER)")
    routing1 = rt.route(task1["task_id"])
    print(f"  Routing target : {routing1['routing_target']}")
    print(f"  Reason          : {routing1['reason']}")
    print(f"  Creates downstream task : {routing1['creates_downstream_task']}")
    task1 = rt.get_task(task1["task_id"])
    print(f"  Task state      : {task1['state']}")

    # Complete the upstream CryER task (its output has been routed)
    if not rt.gate.check_approval_required(task1):
        task1 = rt.complete_task(task1["task_id"], "CryER task completed — output routed to PypER")
        print(f"  Upstream task completed: {task1['state']}")

    # Create downstream PypER task
    if routing1["creates_downstream_task"]:
        section("Phase 4b: Create PypER Downstream Task")
        task2 = rt.create_downstream_task(
            upstream_task_id=task1["task_id"],
            routing_target=routing1["routing_target"],
        )
        print_task_state(task2, "PypER Task Created")

        # ═════════════════════════════════════════════════════════
        # PHASE 5: Simulate PypER Acknowledgment + Response
        # ═════════════════════════════════════════════════════════
        section("Phase 5: Simulate PypER Acknowledgment & Response")
        task2 = rt.simulate_acknowledge(task2["task_id"])
        print(f"  Acknowledged: {task2['task_id']} -> state={task2['state']}")

        pyper_packet = make_pyper_approval_packet(task2["task_id"], task1["task_id"])
        task2 = rt.receive_response(task2["task_id"], pyper_packet)
        print(f"  Response received: {task2['state']}")

        # ═════════════════════════════════════════════════════════
        # PHASE 6: Validate PypER Response
        # ═════════════════════════════════════════════════════════
        section("Phase 6: Validate PypER Response Packet")
        v2 = rt.validate_response(task2["task_id"])
        print_validation(v2)
        task2 = rt.get_task(task2["task_id"])
        print(f"  Task state after validation: {task2['state']}")

        # ═════════════════════════════════════════════════════════
        # PHASE 7: Route + Approval Gate
        # ═════════════════════════════════════════════════════════
        section("Phase 7: Routing + Approval Gate (PypER)")
        routing2 = rt.route(task2["task_id"])
        print(f"  Routing target : {routing2['routing_target']}")
        print(f"  Reason          : {routing2['reason']}")
        task2 = rt.get_task(task2["task_id"])
        print(f"  Task state      : {task2['state']}")

        # ═════════════════════════════════════════════════════════
        # PHASE 8: Outbound Block Check
        # ═════════════════════════════════════════════════════════
        section("Phase 8: Outbound Action Block Check")
        blocked, reason = rt.check_outbound_block(task2["task_id"])
        print(f"  Outbound blocked : {blocked}")
        print(f"  Reason            : {reason}")

        # ═════════════════════════════════════════════════════════
        # PHASE 9: Simulate Operator Approval (APPROVE)
        # ═════════════════════════════════════════════════════════
        section("Phase 9: Operator Approves")
        task2 = rt.process_approval(
            task2["task_id"],
            decision="approved",
            reason="Outreach draft looks good. Proceed with caution.",
            operator="demo_operator",
        )
        print(f"  Task state after approval: {task2['state']}")

        # Check outbound again
        blocked2, reason2 = rt.check_outbound_block(task2["task_id"])
        print(f"  Outbound blocked after approval : {blocked2}")
        print(f"  Reason                           : {reason2}")

    # ═══════════════════════════════════════════════════════════
    # PHASE 10: Operator-Facing Summary
    # ═══════════════════════════════════════════════════════════
    section("Phase 10: Operator-Facing Summaries")
    print("\n  --- Task 1 (CryER Recon) ---")
    summary1 = rt.operator_summary(task1["task_id"])
    print(json.dumps(summary1, indent=2))

    if routing1.get("creates_downstream_task"):
        print("\n  --- Task 2 (PypER Outreach) ---")
        summary2 = rt.operator_summary(task2["task_id"])
        print(json.dumps(summary2, indent=2))

    # ═══════════════════════════════════════════════════════════
    # AUDIT TRAIL
    # ═══════════════════════════════════════════════════════════
    section("Complete Audit Trail")
    all_entries = rt.get_audit_trail(limit=50)
    print_audit_summary(all_entries)

    # ═══════════════════════════════════════════════════════════
    # TASK FILE INSPECTION
    # ═══════════════════════════════════════════════════════════
    section("Task Records on Disk")
    tasks = rt.list_tasks()
    for t in tasks:
        print_task_state(t)
        print()

    # ═══════════════════════════════════════════════════════════
    # FINAL REPORT
    # ═══════════════════════════════════════════════════════════
    banner("Demo Complete — Executive Summary")
    print(f"""
  What was EXECUTED (real runtime logic):
    - Task record creation on filesystem      ✓
    - Sequential task ID assignment            ✓
    - Subagent selection from domain           ✓
    - Request packet generation                ✓
    - 6-level packet validation                ✓
    - State machine transitions (12 states)    ✓
    - Approval gate enforcement                ✓
    - Outbound action blocking                 ✓
    - Operator approval processing             ✓
    - Audit trail (append-only JSONL)          ✓
    - Operator-facing summary generation       ✓
    - Downstream task creation (multi-hop)     ✓

  What remains SIMULATED:
    - CryER response packet                    (synthetic data)
    - PypER response packet                    (synthetic data)
    - Subagent process spawning                (not implemented)
    - Web crawling / data gathering            (not implemented)
    - Any outbound action                      (blocked by design)

  Task IDs created:
    - {task1['task_id']} (CryER recon)
    - {task2['task_id'] if routing1.get('creates_downstream_task') else '(not created)'}

  Audit log: {core_dir}/runtime/audit.jsonl
  Task files: {core_dir}/orchestration/tasks/
  Counter:    {core_dir}/orchestration/task_counter.json
""")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="OverCR v0.1.0 Runtime Demo")
    parser.add_argument(
        "--workspace",
        default=None,
        help="Directory for demo workspace (default: use overcr directory)",
    )
    args = parser.parse_args()

    # If no workspace specified, use the core directory but we need to
    # manage the task counter carefully. For a clean demo, use --workspace.
    run_demo(workspace=args.workspace)