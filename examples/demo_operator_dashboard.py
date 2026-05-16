#!/usr/bin/env python3
"""
OverCR v2.2.0 — Operator Dashboard Demo

Creates a sample workspace with realistic data and renders
the full dashboard, individual views, and keybindings help.

This demo is non-interactive — it prints formatted output to stdout.
In production, the dashboard would be driven by a TUI frontend
(e.g. Textual app, Rich Live display, or simple REPL).

Usage:
    python3 examples/demo_operator_dashboard.py
"""

import json
import os
import sys
import tempfile
from pathlib import Path

# Ensure project root is on sys.path
OVERCR_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(OVERCR_ROOT))

from tui.dashboard import Dashboard
from tui.task_view import TaskView
from tui.workflow_view import WorkflowView
from tui.packet_inspector import PacketInspector
from tui.audit_view import AuditView
from tui.approval_queue import ApprovalQueue
from tui.status_bar import StatusBar
from tui.keybindings import KeyBindings, BindingScope


def create_demo_workspace():
    """Create a demo workspace with sample data."""
    tmpdir = tempfile.mkdtemp(prefix="overcr-demo-")

    # Create directories
    os.makedirs(os.path.join(tmpdir, "orchestration", "tasks"), exist_ok=True)
    os.makedirs(os.path.join(tmpdir, "runtime"), exist_ok=True)
    os.makedirs(os.path.join(tmpdir, "memory", "records"), exist_ok=True)
    os.makedirs(os.path.join(tmpdir, "subagents", "cryer"), exist_ok=True)
    os.makedirs(os.path.join(tmpdir, "subagents", "pyper"), exist_ok=True)
    os.makedirs(os.path.join(tmpdir, "subagents", "coder"), exist_ok=True)
    os.makedirs(os.path.join(tmpdir, "subagents", "knower"), exist_ok=True)

    # Task counter
    with open(os.path.join(tmpdir, "orchestration", "task_counter.json"), "w") as f:
        json.dump({"last_task_id": "0583", "last_updated": "2026-05-15T21:30:00+00:00"}, f)

    # Sample tasks
    tasks = [
        {
            "task_id": "task-0580",
            "upstream_task_id": None,
            "created_at": "2026-05-15T20:00:00+00:00",
            "created_by": "overcr",
            "assigned_subagent": "cryer",
            "domain": "reputation_signal",
            "description": "Recon: local restaurant reputation signals",
            "state": "completed",
            "revision_count": 0,
            "state_log": [
                {"state": "created", "timestamp": "2026-05-15T20:00:00+00:00", "note": "Task created"},
                {"state": "assigned", "timestamp": "2026-05-15T20:00:10+00:00", "note": "Assigned to cryer"},
                {"state": "in_progress", "timestamp": "2026-05-15T20:01:00+00:00", "note": "CryER processing"},
                {"state": "response_received", "timestamp": "2026-05-15T20:02:00+00:00", "note": "Response received"},
                {"state": "validation_passed", "timestamp": "2026-05-15T20:02:10+00:00", "note": "L1-L6 passed"},
                {"state": "routed", "timestamp": "2026-05-15T20:02:20+00:00", "note": "Routed to PypER"},
                {"state": "completed", "timestamp": "2026-05-15T20:03:00+00:00", "note": "Completed"},
            ],
            "request_packet": {
                "task_id": "task-0580", "assigned_subagent": "cryer", "domain": "reputation_signal",
                "instruction": "Identify reputation signals for local restaurants",
                "input_context": {"area": "Endicott, NY"},
                "constraints": ["Public signals only", "No outbound contact"],
                "required_packet_type": "cryer_reputation_signal", "created_at": "2026-05-15T20:00:00+00:00",
            },
            "response_packet": {
                "packet_type": "cryer_reputation_signal", "version": "1.0", "source": "cryer",
                "target": "overcr", "task_id": "task-0580", "summary": "5 restaurant signals identified",
                "approval_required": False, "timestamp": "2026-05-15T20:02:00+00:00",
            },
            "validation_result": {"valid": True, "errors": [], "warnings": [], "levels": {
                "L1": {"valid": True}, "L2": {"valid": True}, "L3": {"valid": True},
                "L4": {"valid": True}, "L5": {"valid": True}, "L6": {"valid": True},
            }},
            "routing_decision": {"routing_target": "pyper", "reason": "Outreach domain", "creates_downstream_task": True},
            "operator_approval": None,
        },
        {
            "task_id": "task-0581",
            "upstream_task_id": "task-0580",
            "created_at": "2026-05-15T20:03:30+00:00",
            "created_by": "overcr",
            "assigned_subagent": "pyper",
            "domain": "outreach",
            "description": "Outreach draft for top prospect",
            "state": "approval_pending",
            "revision_count": 0,
            "state_log": [
                {"state": "created", "timestamp": "2026-05-15T20:03:30+00:00", "note": "Task created"},
                {"state": "assigned", "timestamp": "2026-05-15T20:03:40+00:00", "note": "Assigned to pyper"},
                {"state": "in_progress", "timestamp": "2026-05-15T20:04:00+00:00", "note": "PypER processing"},
                {"state": "response_received", "timestamp": "2026-05-15T20:05:00+00:00", "note": "Response received"},
                {"state": "validation_passed", "timestamp": "2026-05-15T20:05:10+00:00", "note": "L1-L6 passed"},
                {"state": "routed", "timestamp": "2026-05-15T20:05:20+00:00", "note": "Approval required"},
                {"state": "approval_pending", "timestamp": "2026-05-15T20:05:30+00:00", "note": "Awaiting operator approval"},
            ],
            "request_packet": {
                "task_id": "task-0581", "assigned_subagent": "pyper", "domain": "outreach",
                "instruction": "Draft outreach email for top prospect",
                "input_context": {"prospect": "Example Restaurant"},
                "constraints": ["Public signals only", "No outbound contact"],
                "required_packet_type": "pyper_approval", "created_at": "2026-05-15T20:03:30+00:00",
            },
            "response_packet": {
                "packet_type": "pyper_approval", "version": "1.0", "source": "pyper",
                "target": "overcr", "task_id": "task-0581", "summary": "Outreach draft for Example Restaurant",
                "approval_required": True, "outbound_contact": True, "timestamp": "2026-05-15T20:05:00+00:00",
            },
            "validation_result": {"valid": True, "errors": [], "warnings": []},
            "routing_decision": None,
            "operator_approval": None,
        },
        {
            "task_id": "task-0582",
            "upstream_task_id": None,
            "created_at": "2026-05-15T20:06:00+00:00",
            "created_by": "overcr",
            "assigned_subagent": "knower",
            "domain": "claim_review",
            "description": "Review fact claims about local business",
            "state": "in_progress",
            "revision_count": 0,
            "state_log": [
                {"state": "created", "timestamp": "2026-05-15T20:06:00+00:00", "note": "Task created"},
                {"state": "assigned", "timestamp": "2026-05-15T20:06:10+00:00", "note": "Assigned to knower"},
                {"state": "in_progress", "timestamp": "2026-05-15T20:07:00+00:00", "note": "KnowER processing"},
            ],
            "request_packet": {
                "task_id": "task-0582", "assigned_subagent": "knower", "domain": "claim_review",
                "instruction": "Review claims about business reputation",
                "input_context": {},
                "constraints": ["Public signals only"],
                "required_packet_type": "knower_claim_review", "created_at": "2026-05-15T20:06:00+00:00",
            },
            "response_packet": None,
            "validation_result": None,
            "routing_decision": None,
            "operator_approval": None,
        },
    ]

    for task in tasks:
        path = os.path.join(tmpdir, "orchestration", "tasks", f"{task['task_id']}.json")
        with open(path, "w") as f:
            json.dump(task, f, indent=2)

    # Audit log
    audit_entries = [
        {"timestamp": "2026-05-15T20:00:00+00:00", "entry_type": "task_created", "task_id": "task-0580", "details": {"subagent": "cryer", "domain": "reputation_signal"}},
        {"timestamp": "2026-05-15T20:02:10+00:00", "entry_type": "validation_result", "task_id": "task-0580", "details": {"valid": True, "error_count": 0, "warning_count": 0}},
        {"timestamp": "2026-05-15T20:02:20+00:00", "entry_type": "routing_decision", "task_id": "task-0580", "details": {"routing_target": "pyper", "reason": "Outreach domain"}},
        {"timestamp": "2026-05-15T20:03:30+00:00", "entry_type": "task_created", "task_id": "task-0581", "details": {"subagent": "pyper", "domain": "outreach"}},
        {"timestamp": "2026-05-15T20:05:30+00:00", "entry_type": "approval_action", "task_id": "task-0581", "details": {"gate_action": "pending", "decision": "required"}},
    ]
    with open(os.path.join(tmpdir, "runtime", "audit.jsonl"), "w") as f:
        for entry in audit_entries:
            f.write(json.dumps(entry) + "\n")

    # Memory index
    memory_entries = [
        {"memory_id": "mem-a1b2c3d4", "status": "active", "project_scope": "crm-outreach", "semantic_summary": "Endicott restaurants have strong review signals"},
        {"memory_id": "mem-e5f6g7h8", "status": "active", "project_scope": "crm-outreach", "semantic_summary": "Local business outreach best practices"},
        {"memory_id": "mem-i9j0k1l2", "status": "stale", "project_scope": "infrastructure", "semantic_summary": "Provider routing config"},
    ]
    with open(os.path.join(tmpdir, "memory", "index.jsonl"), "w") as f:
        for entry in memory_entries:
            f.write(json.dumps(entry) + "\n")

    return tmpdir


def main():
    print("=" * 72)
    print("  OVERCR v2.2.0 — Operator Dashboard Demo")
    print("=" * 72)
    print()

    tmpdir = create_demo_workspace()
    print(f"Demo workspace: {tmpdir}")
    print()

    # ── Dashboard ──
    print("─" * 72)
    print("  DASHBOARD (Plain Text)")
    print("─" * 72)
    dash = Dashboard(root=tmpdir)
    print(dash.render_plain())
    print()

    # ── Approval Queue ──
    print("─" * 72)
    print("  APPROVAL QUEUE")
    print("─" * 72)
    aq = ApprovalQueue(root=tmpdir)
    print(aq.render_queue_plain())
    print()

    # ── Keybindings ──
    print("─" * 72)
    print("  KEYBINDINGS (Global Scope)")
    print("─" * 72)
    kb = KeyBindings()
    print(kb.format_help(scope=BindingScope.GLOBAL))
    print()

    # ── Packet Inspector ──
    print("─" * 72)
    print("  PACKET INSPECTOR — task-0580")
    print("─" * 72)
    pi = PacketInspector(root=tmpdir)
    print(pi.render_plain("task-0580"))
    print()

    # ── Audit View ──
    print("─" * 72)
    print("  AUDIT STREAM")
    print("─" * 72)
    av = AuditView(root=tmpdir)
    print(av.render_plain(limit=5))
    print()

    # ── Workflow View ──
    print("─" * 72)
    print("  WORKFLOW DAG")
    print("─" * 72)
    wv = WorkflowView(root=tmpdir)
    graph_data = {
        "name": "Outreach Pipeline",
        "nodes": {
            "knower-research": {"node_id": "knower-research", "subagent": "knower", "packet_type": "knower_research", "approval_policy": "never"},
            "cryer-recon": {"node_id": "cryer-recon", "subagent": "cryer", "packet_type": "cryer_recon", "approval_policy": "never"},
            "pyper-outreach": {"node_id": "pyper-outreach", "subagent": "pyper", "packet_type": "pyper_approval", "approval_policy": "always"},
        },
        "edges": {
            "e1": {"edge_id": "e1", "source_node_id": "knower-research", "target_node_id": "cryer-recon", "accepted_packet_types": ["knower_research"]},
            "e2": {"edge_id": "e2", "source_node_id": "cryer-recon", "target_node_id": "pyper-outreach", "accepted_packet_types": ["cryer_recon"]},
        },
    }
    print(wv.render_dag_plain(graph_data))
    print()

    # ── Status Bar ──
    print("─" * 72)
    print("  STATUS BAR")
    print("─" * 72)
    sb = StatusBar(root=tmpdir)
    print(sb.render_plain())
    print()

    print("=" * 72)
    print("  Demo complete. Workspace preserved at:")
    print(f"  {tmpdir}")
    print("=" * 72)

    return 0


if __name__ == "__main__":
    sys.exit(main())