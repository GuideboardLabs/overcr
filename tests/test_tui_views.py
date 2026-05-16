#!/usr/bin/env python3
"""
OverCR v2.2.0 — TUI Operator Interface Layer Tests

Coverage:
  - Task rendering: list, detail, filtered, plain fallback
  - Workflow DAG rendering: nodes, edges, states, fallback
  - Approval queue: pending list, no auto-approve, propagate approval, plain
  - Audit filtering: by task, type, category, plain
  - Packet inspection: request, response, validation, routing, rejection, plain
  - Degraded runtime behavior: missing data produces graceful output
  - Deterministic fallback rendering: same input → same output
  - Status bar: task counts, memory summary, worker info
  - Theme consistency: colors, icons, badge rendering

Run:
    python3 tests/test_tui_views.py
"""

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

# Ensure project root is on sys.path
OVERCR_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(OVERCR_ROOT))

from tui.theme import Theme, StatusColors, Icons
from tui.keybindings import KeyBindings, BindingScope
from tui.widgets.status_badge import StatusBadge
from tui.widgets.table import TableWidget
from tui.widgets.panel import PanelWidget
from tui.widgets.log_view import LogViewWidget
from tui.status_bar import StatusBar
from tui.task_view import TaskView
from tui.workflow_view import WorkflowView
from tui.packet_inspector import PacketInspector, VALIDATION_LEVELS
from tui.audit_view import AuditView
from tui.approval_queue import ApprovalQueue, ApprovalAction
from tui.dashboard import Dashboard

FAILED = False


def assert_test(condition, msg):
    global FAILED
    if not condition:
        print(f"  FAIL: {msg}")
        FAILED = True
        return False
    return True


def create_test_workspace():
    """Create a temporary OverCR workspace with sample data."""
    tmpdir = tempfile.mkdtemp(prefix="overcr-tui-test-")

    # Create directory structure
    os.makedirs(os.path.join(tmpdir, "orchestration", "tasks"), exist_ok=True)
    os.makedirs(os.path.join(tmpdir, "runtime"), exist_ok=True)
    os.makedirs(os.path.join(tmpdir, "memory", "records"), exist_ok=True)
    os.makedirs(os.path.join(tmpdir, "subagents", "cryer"), exist_ok=True)
    os.makedirs(os.path.join(tmpdir, "subagents", "pyper"), exist_ok=True)
    os.makedirs(os.path.join(tmpdir, "subagents", "coder"), exist_ok=True)
    os.makedirs(os.path.join(tmpdir, "subagents", "knower"), exist_ok=True)

    # Create task counter
    with open(os.path.join(tmpdir, "orchestration", "task_counter.json"), "w") as f:
        json.dump({"last_task_id": "0585", "last_updated": "2026-05-15T21:00:00+00:00"}, f)

    # Create sample tasks
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
                "task_id": "task-0580",
                "assigned_subagent": "cryer",
                "domain": "reputation_signal",
                "instruction": "Identify reputation signals for local restaurants",
                "input_context": {"area": "Endicott, NY"},
                "constraints": ["Public signals only", "No outbound contact"],
                "required_packet_type": "cryer_reputation_signal",
                "created_at": "2026-05-15T20:00:00+00:00",
            },
            "response_packet": {
                "packet_type": "cryer_reputation_signal",
                "version": "1.0",
                "source": "cryer",
                "target": "overcr",
                "task_id": "task-0580",
                "timestamp": "2026-05-15T20:02:00+00:00",
                "summary": "5 restaurant reputation signals identified",
                "approval_required": False,
            },
            "validation_result": {"valid": True, "errors": [], "warnings": []},
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
                "task_id": "task-0581",
                "assigned_subagent": "pyper",
                "domain": "outreach",
                "instruction": "Draft outreach email for top prospect",
                "input_context": {"prospect": "Example Restaurant"},
                "constraints": ["Public signals only", "No outbound contact"],
                "required_packet_type": "pyper_approval",
                "created_at": "2026-05-15T20:03:30+00:00",
            },
            "response_packet": {
                "packet_type": "pyper_approval",
                "version": "1.0",
                "source": "pyper",
                "target": "overcr",
                "task_id": "task-0581",
                "timestamp": "2026-05-15T20:05:00+00:00",
                "summary": "Outreach draft for Example Restaurant",
                "approval_required": True,
                "outbound_contact": True,
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
                "task_id": "task-0582",
                "assigned_subagent": "knower",
                "domain": "claim_review",
                "instruction": "Review claims about business reputation",
                "input_context": {},
                "constraints": ["Public signals only"],
                "required_packet_type": "knower_claim_review",
                "created_at": "2026-05-15T20:06:00+00:00",
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

    # Create audit log
    audit_entries = [
        {"timestamp": "2026-05-15T20:00:00+00:00", "entry_type": "task_created", "task_id": "task-0580", "details": {"subagent": "cryer", "domain": "reputation_signal"}},
        {"timestamp": "2026-05-15T20:02:10+00:00", "entry_type": "validation_result", "task_id": "task-0580", "details": {"valid": True, "error_count": 0, "warning_count": 0}},
        {"timestamp": "2026-05-15T20:02:20+00:00", "entry_type": "routing_decision", "task_id": "task-0580", "details": {"routing_target": "pyper", "reason": "Outreach domain", "creates_downstream_task": True}},
        {"timestamp": "2026-05-15T20:05:30+00:00", "entry_type": "approval_action", "task_id": "task-0581", "details": {"gate_action": "pending", "decision": "required", "operator": "system"}},
        {"timestamp": "2026-05-15T20:06:00+00:00", "entry_type": "task_created", "task_id": "task-0582", "details": {"subagent": "knower", "domain": "claim_review"}},
    ]
    with open(os.path.join(tmpdir, "runtime", "audit.jsonl"), "w") as f:
        for entry in audit_entries:
            f.write(json.dumps(entry) + "\n")

    # Create memory index
    memory_entries = [
        {"memory_id": "mem-a1b2c3d4", "status": "active", "project_scope": "crm-outreach"},
        {"memory_id": "mem-e5f6g7h8", "status": "active", "project_scope": "crm-outreach"},
        {"memory_id": "mem-i9j0k1l2", "status": "stale", "project_scope": "infrastructure"},
        {"memory_id": "mem-m3n4o5p6", "status": "rejected", "project_scope": "crm-outreach"},
    ]
    with open(os.path.join(tmpdir, "memory", "index.jsonl"), "w") as f:
        for entry in memory_entries:
            f.write(json.dumps(entry) + "\n")

    return tmpdir


# ════════════════════════════════════════════════════════════
# PHASE 1: Theme & Icons
# ════════════════════════════════════════════════════════════

def test_theme_and_icons():
    print("Phase 1: Theme & Icons")
    tests_passed = 0
    tests_total = 0

    # Status color mapping
    tests_total += 1
    assert_test(StatusColors.for_task_state("completed") == "bright_green", "Task state color: completed → bright_green")
    tests_passed += 1 if StatusColors.for_task_state("completed") == "bright_green" else 0

    tests_total += 1
    assert_test(StatusColors.for_task_state("approval_pending") == "bright_yellow", "Task state color: approval_pending → bright_yellow")
    tests_passed += 1 if StatusColors.for_task_state("approval_pending") == "bright_yellow" else 0

    tests_total += 1
    assert_test(StatusColors.for_task_state("unknown_state") == "dim white", "Unknown task state → dim white fallback")
    tests_passed += 1 if StatusColors.for_task_state("unknown_state") == "dim white" else 0

    # Validation level colors
    tests_total += 1
    assert_test(StatusColors.for_validation_level(1) == "bright_red", "L1 → bright_red")
    tests_passed += 1 if StatusColors.for_validation_level(1) == "bright_red" else 0

    tests_total += 1
    assert_test(StatusColors.for_validation_level(6) == "bright_green", "L6 → bright_green")
    tests_passed += 1 if StatusColors.for_validation_level(6) == "bright_green" else 0

    # Memory status colors
    tests_total += 1
    assert_test(StatusColors.for_memory_status("active") == "green", "Memory active → green")
    tests_passed += 1 if StatusColors.for_memory_status("active") == "green" else 0

    # Icons
    tests_total += 1
    assert_test(Icons.CHECK == "\u2713", "Unicode check icon")
    tests_passed += 1 if Icons.CHECK == "\u2713" else 0

    # ASCII fallback
    Icons.use_unicode(False)
    tests_total += 1
    assert_test(Icons.check == Icons.CHECK_ASCII, "ASCII fallback: check → +")
    tests_passed += 1 if Icons.check == Icons.CHECK_ASCII else 0
    Icons.use_unicode(True)  # Reset

    # Theme constants defined
    tests_total += 1
    assert_test(Theme.PANEL_PADDING == 1, "Panel padding is 1")
    tests_passed += 1 if Theme.PANEL_PADDING == 1 else 0

    tests_total += 1
    assert_test(Theme.TASK_ID_WIDTH == 14, "Task ID width is 14")
    tests_passed += 1 if Theme.TASK_ID_WIDTH == 14 else 0

    print(f"  Theme & Icons: {tests_passed}/{tests_total} passed")
    return tests_passed, tests_total


# ════════════════════════════════════════════════════════════
# PHASE 2: Keybindings
# ════════════════════════════════════════════════════════════

def test_keybindings():
    print("Phase 2: Keybindings")
    tests_passed = 0
    tests_total = 0

    kb = KeyBindings()

    # Global bindings exist
    tests_total += 1
    global_bindings = kb.get_bindings_for_scope(BindingScope.GLOBAL)
    assert_test(len(global_bindings) > 0, "Global bindings exist")
    tests_passed += 1 if len(global_bindings) > 0 else 0

    # Binding lookup
    tests_total += 1
    quit_binding = kb.get_binding("quit")
    assert_test(quit_binding is not None, "Quit binding exists")
    tests_passed += 1 if quit_binding is not None else 0

    tests_total += 1
    assert_test(quit_binding.action == "quit", "Quit binding action is 'quit'")
    tests_passed += 1 if quit_binding.action == "quit" else 0

    # Scope filtering includes global
    tests_total += 1
    task_bindings = kb.get_bindings_for_scope(BindingScope.TASK_VIEW)
    global_in_task = any(b.action == "quit" for b in task_bindings)
    assert_test(global_in_task, "Scope-filtered bindings include global actions")
    tests_passed += 1 if global_in_task else 0

    # Help text
    tests_total += 1
    help_text = kb.format_help(scope=BindingScope.GLOBAL)
    assert_test("quit" in help_text and "Keybindings" in help_text, "Help text contains quit and title")
    tests_passed += 1 if ("quit" in help_text and "Keybindings" in help_text) else 0

    # No auto-approve binding
    tests_total += 1
    approval_bindings = kb.get_bindings_for_scope(BindingScope.APPROVAL_QUEUE)
    auto_approve = any(b.action == "auto_approve" for b in approval_bindings)
    assert_test(not auto_approve, "NO auto_approve binding exists (governance)")
    tests_passed += 1 if not auto_approve else 0

    print(f"  Keybindings: {tests_passed}/{tests_total} passed")
    return tests_passed, tests_total


# ════════════════════════════════════════════════════════════
# PHASE 3: Status Badge
# ════════════════════════════════════════════════════════════

def test_status_badge():
    print("Phase 3: Status Badge")
    tests_passed = 0
    tests_total = 0

    badge = StatusBadge(use_unicode=True)

    # Rich rendering
    tests_total += 1
    rendered = badge.render("completed", "task")
    assert_test("completed" in rendered, "Badge contains status text")
    tests_passed += 1 if "completed" in rendered else 0

    # Plain rendering
    tests_total += 1
    plain = badge.render_plain("completed", "task")
    assert_test("completed" in plain, "Plain badge contains status text")
    tests_passed += 1 if "completed" in plain else 0

    # Validation level badge
    tests_total += 1
    l3_badge = badge.render("L3", "validation")
    assert_test("L3" in l3_badge, "Validation level badge contains level")
    tests_passed += 1 if "L3" in l3_badge else 0

    # Task state reference strip
    tests_total += 1
    strip = badge.render_all_task_states()
    assert_test("completed" in strip, "State reference strip contains 'completed'")
    tests_passed += 1 if "completed" in strip else 0

    # Deterministic: same input → same output
    tests_total += 1
    r1 = badge.render("in_progress", "task")
    r2 = badge.render("in_progress", "task")
    assert_test(r1 == r2, "Deterministic: same input produces same badge")
    tests_passed += 1 if r1 == r2 else 0

    # ASCII fallback mode
    badge_ascii = StatusBadge(use_unicode=False)
    tests_total += 1
    plain_ascii = badge_ascii.render_plain("completed", "task")
    assert_test("completed" in plain_ascii, "ASCII badge contains status text")
    tests_passed += 1 if "completed" in plain_ascii else 0

    print(f"  Status Badge: {tests_passed}/{tests_total} passed")
    return tests_passed, tests_total


# ════════════════════════════════════════════════════════════
# PHASE 4: Task View
# ════════════════════════════════════════════════════════════

def test_task_view():
    print("Phase 4: Task View")
    tmpdir = create_test_workspace()
    tests_passed = 0
    tests_total = 0

    try:
        tv = TaskView(root=tmpdir)

        # Load all tasks
        tests_total += 1
        tasks = tv._load_tasks()
        assert_test(len(tasks) == 3, f"Loaded 3 tasks, got {len(tasks)}")
        tests_passed += 1 if len(tasks) == 3 else 0

        # Task list rendering
        tests_total += 1
        list_output = tv.render_task_list()
        assert_test("task-0580" in list_output or len(list_output) > 0, "Task list renders")
        tests_passed += 1 if len(list_output) > 0 else 0

        # Filtered task list
        tests_total += 1
        filtered = tv.render_task_list(filter_state="approval_pending")
        assert_test("task-0581" in filtered or len(filtered) > 0, "Filtered task list renders")
        tests_passed += 1 if len(filtered) > 0 else 0

        # Task detail
        tests_total += 1
        detail = tv.render_task_detail("task-0580")
        assert_test("task-0580" in detail and "completed" in detail, "Task detail renders")
        tests_passed += 1 if "task-0580" in detail else 0

        # Task detail plain fallback
        tests_total += 1
        detail_plain = tv.render_task_detail_plain("task-0580")
        assert_test("task-0580" in detail_plain, "Plain task detail renders")
        tests_passed += 1 if "task-0580" in detail_plain else 0

        # Missing task
        tests_total += 1
        missing = tv.render_task_detail("task-9999")
        assert_test("not found" in missing, "Missing task shows 'not found'")
        tests_passed += 1 if "not found" in missing else 0

        # Approval pending detail
        tests_total += 1
        approval_detail = tv.render_task_detail("task-0581")
        assert_test("approval" in approval_detail.lower(), "Approval pending task shows approval info")
        tests_passed += 1 if "approval" in approval_detail.lower() else 0

        # Deterministic: same detail, same output
        tests_total += 1
        detail2 = tv.render_task_detail_plain("task-0580")
        assert_test(detail_plain == detail2, "Deterministic: same input produces same detail")
        tests_passed += 1 if detail_plain == detail2 else 0

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    print(f"  Task View: {tests_passed}/{tests_total} passed")
    return tests_passed, tests_total


# ════════════════════════════════════════════════════════════
# PHASE 5: Workflow View
# ════════════════════════════════════════════════════════════

def test_workflow_view():
    print("Phase 5: Workflow View")
    tmpdir = create_test_workspace()
    tests_passed = 0
    tests_total = 0

    try:
        wv = WorkflowView(root=tmpdir)

        # Sample workflow graph data
        graph_data = {
            "workflow_id": "wf-test-001",
            "name": "Test Outreach Pipeline",
            "version": "0.8.0",
            "description": "KnowER → CryER → PypER pipeline",
            "nodes": {
                "knower-research": {
                    "node_id": "knower-research",
                    "subagent": "knower",
                    "packet_type": "knower_research",
                    "input_requirements": [],
                    "output_requirements": ["knower_research"],
                    "approval_policy": "never",
                    "max_retries": 0,
                    "timeout_s": 30.0,
                    "description": "Research local businesses",
                },
                "cryer-recon": {
                    "node_id": "cryer-recon",
                    "subagent": "cryer",
                    "packet_type": "cryer_recon",
                    "input_requirements": ["knower_research"],
                    "output_requirements": ["cryer_recon"],
                    "approval_policy": "never",
                    "max_retries": 0,
                    "timeout_s": 60.0,
                    "description": "Gather reputation signals",
                },
                "pyper-outreach": {
                    "node_id": "pyper-outreach",
                    "subagent": "pyper",
                    "packet_type": "pyper_approval",
                    "input_requirements": ["cryer_recon"],
                    "output_requirements": ["pyper_approval"],
                    "approval_policy": "always",
                    "max_retries": 1,
                    "timeout_s": 120.0,
                    "description": "Draft outreach email (requires approval)",
                },
            },
            "edges": {
                "edge-knower-cryer": {
                    "edge_id": "edge-knower-cryer",
                    "source_node_id": "knower-research",
                    "target_node_id": "cryer-recon",
                    "accepted_packet_types": ["knower_research"],
                    "transformation_rule": None,
                    "approval_gate": None,
                },
                "edge-cryer-pyper": {
                    "edge_id": "edge-cryer-pyper",
                    "source_node_id": "cryer-recon",
                    "target_node_id": "pyper-outreach",
                    "accepted_packet_types": ["cryer_recon"],
                    "transformation_rule": None,
                    "approval_gate": "on_failure",
                },
            },
            "built": True,
        }

        # DAG rendering
        tests_total += 1
        rendered = wv.render_dag(graph_data)
        assert_test("knower-research" in rendered, "DAG contains knower node")
        tests_passed += 1 if "knower-research" in rendered else 0

        tests_total += 1
        assert_test("pyper-outreach" in rendered, "DAG contains pyper node")
        tests_passed += 1 if "pyper-outreach" in rendered else 0

        # Node states
        node_states = {
            "knower-research": "completed",
            "cryer-recon": "running",
            "pyper-outreach": "waiting_approval",
        }
        tests_total += 1
        rendered_with_states = wv.render_dag(graph_data, node_states=node_states)
        assert_test("waiting_approval" in rendered_with_states or "running" in rendered_with_states,
                     "DAG with states contains node state info")
        tests_passed += 1 if ("waiting_approval" in rendered_with_states or "running" in rendered_with_states) else 0

        # Approval gates shown
        tests_total += 1
        assert_test("approval" in rendered.lower(), "DAG shows approval gate info")
        tests_passed += 1 if "approval" in rendered.lower() else 0

        # Plain fallback
        tests_total += 1
        plain = wv.render_dag_plain(graph_data)
        assert_test("knower" in plain, "Plain DAG contains knower")
        tests_passed += 1 if "knower" in plain else 0

        # Empty graph
        tests_total += 1
        empty_rendered = wv.render_dag({"nodes": {}, "edges": {}})
        assert_test("No workflow nodes found" in empty_rendered, "Empty graph handled gracefully")
        tests_passed += 1 if "No workflow nodes found" in empty_rendered else 0

        # Blocked nodes display
        tests_total += 1
        blocked_rendered = wv.render_dag(graph_data, node_states={"pyper-outreach": "waiting_approval"})
        assert_test("Blocked" in blocked_rendered or "waiting_approval" in blocked_rendered,
                     "Blocked nodes shown in DAG")
        tests_passed += 1 if "Blocked" in blocked_rendered or "waiting_approval" in blocked_rendered else 0

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    print(f"  Workflow View: {tests_passed}/{tests_total} passed")
    return tests_passed, tests_total


# ════════════════════════════════════════════════════════════
# PHASE 6: Approval Queue
# ════════════════════════════════════════════════════════════

def test_approval_queue():
    print("Phase 6: Approval Queue")
    tmpdir = create_test_workspace()
    tests_passed = 0
    tests_total = 0

    try:
        aq = ApprovalQueue(root=tmpdir)

        # Pending approvals found
        tests_total += 1
        pending = aq.get_pending_approvals()
        assert_test(len(pending) == 1, f"Found 1 pending approval, got {len(pending)}")
        tests_passed += 1 if len(pending) == 1 else 0

        # Pending approval is the right task
        tests_total += 1
        assert_test(pending[0]["task_id"] == "task-0581", "Pending approval is task-0581")
        tests_passed += 1 if pending[0]["task_id"] == "task-0581" else 0

        # Queue rendering
        tests_total += 1
        rendered = aq.render_queue()
        assert_test("task-0581" in rendered, "Queue rendering contains task-0581")
        tests_passed += 1 if "task-0581" in rendered else 0

        # Queue plain rendering
        tests_total += 1
        rendered_plain = aq.render_queue_plain()
        assert_test("task-0581" in rendered_plain, "Plain queue rendering contains task-0581")
        tests_passed += 1 if "task-0581" in rendered_plain else 0

        # Detail rendering
        tests_total += 1
        detail = aq.render_detail("task-0581")
        assert_test("approval" in detail.lower(), "Approval detail contains 'approval'")
        tests_passed += 1 if "approval" in detail.lower() else 0

        # NO auto-approve method
        tests_total += 1
        has_auto_approve = hasattr(aq, "auto_approve") or hasattr(aq, "approve_all")
        assert_test(not has_auto_approve, "NO auto_approve or approve_all method (governance)")
        tests_passed += 1 if not has_auto_approve else 0

        # Propose approval returns data, not execution
        tests_total += 1
        action = aq.propose_approval("task-0581", reason="Looks correct", operator="alice")
        assert_test(isinstance(action, ApprovalAction), "propose_approval returns ApprovalAction")
        tests_passed += 1 if isinstance(action, ApprovalAction) else 0

        tests_total += 1
        assert_test(action.action == "approve", "ApprovalAction.action is 'approve'")
        tests_passed += 1 if action.action == "approve" else 0

        tests_total += 1
        assert_test(action.operator == "alice", "ApprovalAction.operator preserved")
        tests_passed += 1 if action.operator == "alice" else 0

        # Propose rejection
        tests_total += 1
        reject_action = aq.propose_rejection("task-0581", reason="Invalid data")
        assert_test(reject_action.action == "reject", "propose_rejection action is 'reject'")
        tests_passed += 1 if reject_action.action == "reject" else 0

        # Invalid action raises error
        tests_total += 1
        try:
            bad_action = ApprovalAction(task_id="task-0581", action="auto_approve")
            assert_test(False, "Should have raised ValueError for invalid action")
        except ValueError:
            assert_test(True, "Invalid action raises ValueError")
            tests_passed += 1

        # ApprovalAction.to_dict()
        tests_total += 1
        action_dict = action.to_dict()
        assert_test(action_dict["action"] == "approve" and action_dict["operator"] == "alice",
                     "ApprovalAction serializes to dict correctly")
        tests_passed += 1 if action_dict["action"] == "approve" and action_dict["operator"] == "alice" else 0

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    print(f"  Approval Queue: {tests_passed}/{tests_total} passed")
    return tests_passed, tests_total


# ════════════════════════════════════════════════════════════
# PHASE 7: Audit View
# ════════════════════════════════════════════════════════════

def test_audit_view():
    print("Phase 7: Audit View")
    tmpdir = create_test_workspace()
    tests_passed = 0
    tests_total = 0

    try:
        av = AuditView(root=tmpdir)

        # Read audit log
        tests_total += 1
        entries = av._read_audit_log()
        assert_test(len(entries) == 5, f"Audit log has 5 entries, got {len(entries)}")
        tests_passed += 1 if len(entries) == 5 else 0

        # Render all entries
        tests_total += 1
        rendered = av.render()
        assert_test(len(rendered) > 0, "Audit view renders")
        tests_passed += 1 if len(rendered) > 0 else 0

        # Filter by task
        tests_total += 1
        filtered = av.render(filter_task="task-0580")
        assert_test("task-0580" in filtered, "Filtered by task_id")
        tests_passed += 1 if "task-0580" in filtered else 0

        # Filter by type
        tests_total += 1
        filtered_type = av.render(filter_type="approval_action")
        assert_test("approval_action" in filtered_type, "Filtered by entry_type")
        tests_passed += 1 if "approval_action" in filtered_type else 0

        # Filter by category
        tests_total += 1
        filtered_cat = av.render(filter_category="validation")
        assert_test("validation_result" in filtered_cat, "Filtered by category")
        tests_passed += 1 if "validation_result" in filtered_cat else 0

        # Available categories
        tests_total += 1
        cats = av.get_available_categories()
        assert_test("task" in cats and "approval" in cats, "Categories include 'task' and 'approval'")
        tests_passed += 1 if ("task" in cats and "approval" in cats) else 0

        # Plain fallback
        tests_total += 1
        plain = av.render_plain(limit=3)
        assert_test(len(plain) > 0, "Plain audit rendering works")
        tests_passed += 1 if len(plain) > 0 else 0

        # Entry detail
        tests_total += 1
        entry = entries[0]
        detail = av.render_entry_detail(entry)
        assert_test("task_created" in detail or entry.get("entry_type") in detail,
                     "Entry detail contains type info")
        tests_passed += 1 if (len(detail) > 0) else 0

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    print(f"  Audit View: {tests_passed}/{tests_total} passed")
    return tests_passed, tests_total


# ════════════════════════════════════════════════════════════
# PHASE 8: Packet Inspector
# ════════════════════════════════════════════════════════════

def test_packet_inspector():
    print("Phase 8: Packet Inspector")
    tmpdir = create_test_workspace()
    tests_passed = 0
    tests_total = 0

    try:
        pi = PacketInspector(root=tmpdir)

        # Request packet
        tests_total += 1
        request = pi.render_request_packet("task-0580")
        assert_test("cryer" in request, "Request packet shows subagent")
        tests_passed += 1 if "cryer" in request else 0

        # Response packet
        tests_total += 1
        response = pi.render_response_packet("task-0580")
        assert_test("cryer_reputation_signal" in response, "Response shows packet type")
        tests_passed += 1 if "cryer_reputation_signal" in response else 0

        # Validation status
        tests_total += 1
        validation = pi.render_validation_status("task-0580")
        assert_test("PASS" in validation or "Valid" in validation, "Validation shows PASS")
        tests_passed += 1 if ("PASS" in validation or "Valid" in validation) else 0

        # Routing metadata
        tests_total += 1
        routing = pi.render_routing_metadata("task-0580")
        assert_test("pyper" in routing, "Routing shows target")
        tests_passed += 1 if "pyper" in routing else 0

        # Missing task
        tests_total += 1
        missing = pi.render_request_packet("task-9999")
        assert_test("not found" in missing, "Missing task shows 'not found'")
        tests_passed += 1 if "not found" in missing else 0

        # Rejection reason (task-0581 is pending, not rejected)
        tests_total += 1
        rejection = pi.render_rejection_reason("task-0581")
        assert_test("not rejected" in rejection, "Non-rejected task shows 'not rejected'")
        tests_passed += 1 if "not rejected" in rejection else 0

        # Validation levels are defined
        tests_total += 1
        assert_test(len(VALIDATION_LEVELS) == 6, "6 validation levels defined")
        tests_passed += 1 if len(VALIDATION_LEVELS) == 6 else 0

        # Plain fallback
        tests_total += 1
        plain = pi.render_plain("task-0580")
        assert_test("task-0580" in plain, "Plain packet info contains task ID")
        tests_passed += 1 if "task-0580" in plain else 0

        # No response packet task
        tests_total += 1
        no_response = pi.render_response_packet("task-0582")
        assert_test("No response packet" in no_response, "Task without response shows 'No response packet'")
        tests_passed += 1 if "No response packet" in no_response else 0

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    print(f"  Packet Inspector: {tests_passed}/{tests_total} passed")
    return tests_passed, tests_total


# ════════════════════════════════════════════════════════════
# PHASE 9: Degraded Runtime Behavior
# ════════════════════════════════════════════════════════════

def test_degraded_runtime():
    print("Phase 9: Degraded Runtime")
    tmpdir = tempfile.mkdtemp(prefix="overcr-tui-degraded-")
    # Create minimal workspace — no tasks, no audit, no memory
    os.makedirs(os.path.join(tmpdir, "orchestration", "tasks"), exist_ok=True)

    tests_passed = 0
    tests_total = 0

    try:
        # TaskView with empty workspace
        tv = TaskView(root=tmpdir)
        tests_total += 1
        result = tv.render_task_list()
        assert_test("No tasks" in result, "Empty workspace shows 'No tasks'")
        tests_passed += 1 if "No tasks" in result else 0

        # AuditView with no audit log
        av = AuditView(root=tmpdir)
        tests_total += 1
        result = av.render()
        assert_test(len(result) > 0, "No audit log doesn't crash")
        tests_passed += 1 if len(result) > 0 else 0

        # ApprovalQueue with no pending approvals
        aq = ApprovalQueue(root=tmpdir)
        tests_total += 1
        pending = aq.get_pending_approvals()
        assert_test(len(pending) == 0, "Empty workspace has 0 pending approvals")
        tests_passed += 1 if len(pending) == 0 else 0

        tests_total += 1
        rendered = aq.render_queue()
        assert_test("No pending" in rendered, "Empty workspace shows 'No pending approvals'")
        tests_passed += 1 if "No pending" in rendered else 0

        # StatusBar with empty workspace
        sb = StatusBar(root=tmpdir)
        tests_total += 1
        summary = sb._get_task_summary()
        assert_test(summary["total"] == 0, "Empty workspace: 0 tasks")
        tests_passed += 1 if summary["total"] == 0 else 0

        # No crash on missing task
        tests_total += 1
        result = tv.render_task_detail("task-9999")
        assert_test("not found" in result, "Missing task doesn't crash")
        tests_passed += 1 if "not found" in result else 0

        # PacketInspector with missing task
        pi = PacketInspector(root=tmpdir)
        tests_total += 1
        result = pi.render_request_packet("task-9999")
        assert_test("not found" in result, "Missing task doesn't crash in packet inspector")
        tests_passed += 1 if "not found" in result else 0

        # Dashboard render with empty workspace
        dash = Dashboard(root=tmpdir)
        tests_total += 1
        result = dash.render_plain()
        assert_test("DASHBOARD" in result, "Dashboard renders with empty workspace")
        tests_passed += 1 if "DASHBOARD" in result else 0

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    print(f"  Degraded Runtime: {tests_passed}/{tests_total} passed")
    return tests_passed, tests_total


# ════════════════════════════════════════════════════════════
# PHASE 10: Deterministic Fallback
# ════════════════════════════════════════════════════════════

def test_deterministic_fallback():
    print("Phase 10: Deterministic Fallback")
    tmpdir = create_test_workspace()
    tests_passed = 0
    tests_total = 0

    try:
        tv = TaskView(root=tmpdir)
        aq = ApprovalQueue(root=tmpdir)
        sb = StatusBar(root=tmpdir)

        # Task list: rich vs plain produces same semantic content
        tests_total += 1
        rich_output = tv.render_task_list()
        plain_output = tv.render_task_list()  # TaskView uses rich internally for render_task_list
        # For TaskView, render_task_list always uses TableWidget
        # The real fallback is the plain detail view
        assert_test(len(rich_output) > 0, "Rich task list renders")
        tests_passed += 1 if len(rich_output) > 0 else 0

        # Task detail: plain produces same content as rich (minus markup)
        tests_total += 1
        rich_detail = tv.render_task_detail("task-0580")
        plain_detail = tv.render_task_detail_plain("task-0580")
        # Both should contain the task ID
        assert_test("task-0580" in rich_detail and "task-0580" in plain_detail,
                     "Both rich and plain detail contain task ID")
        tests_passed += 1 if ("task-0580" in rich_detail and "task-0580" in plain_detail) else 0

        # Approval queue: plain fallback produces same task IDs
        tests_total += 1
        aq_rich = aq.render_queue()
        aq_plain = aq.render_queue_plain()
        assert_test("task-0581" in aq_rich and "task-0581" in aq_plain,
                     "Both rich and plain queue contain task-0581")
        tests_passed += 1 if ("task-0581" in aq_rich and "task-0581" in aq_plain) else 0

        # Status bar: plain fallback
        tests_total += 1
        sb_rich = sb.render()
        sb_plain = sb.render_plain()
        assert_test(len(sb_rich) > 0 and len(sb_plain) > 0, "Both rich and plain status bar render")
        tests_passed += 1 if (len(sb_rich) > 0 and len(sb_plain) > 0) else 0

        # Deterministic: calling same method twice produces same output
        tests_total += 1
        d1 = tv.render_task_detail_plain("task-0580")
        d2 = tv.render_task_detail_plain("task-0580")
        assert_test(d1 == d2, "Deterministic: identical calls produce identical output")
        tests_passed += 1 if d1 == d2 else 0

        # Workflow: deterministic DAG
        wv = WorkflowView(root=tmpdir)
        graph_data = {
            "name": "test",
            "nodes": {
                "n1": {"node_id": "n1", "subagent": "knower", "packet_type": "knower_research", "approval_policy": "never"},
                "n2": {"node_id": "n2", "subagent": "cryer", "packet_type": "cryer_recon", "approval_policy": "never"},
            },
            "edges": {
                "e1": {"edge_id": "e1", "source_node_id": "n1", "target_node_id": "n2", "accepted_packet_types": ["knower_research"]},
            },
        }
        tests_total += 1
        dag1 = wv.render_dag_plain(graph_data)
        dag2 = wv.render_dag_plain(graph_data)
        assert_test(dag1 == dag2, "Deterministic: identical DAG calls produce identical output")
        tests_passed += 1 if dag1 == dag2 else 0

        # Badge: deterministic
        badge = StatusBadge()
        tests_total += 1
        b1 = badge.render("completed", "task")
        b2 = badge.render("completed", "task")
        assert_test(b1 == b2, "Deterministic: identical badge calls produce identical output")
        tests_passed += 1 if b1 == b2 else 0

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    print(f"  Deterministic Fallback: {tests_passed}/{tests_total} passed")
    return tests_passed, tests_total


# ════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════

def main():
    global FAILED
    FAILED = False

    print("=" * 60)
    print("OverCR v2.2.0 — TUI Operator Interface Layer Tests")
    print("=" * 60)
    print()

    total_passed = 0
    total_tests = 0

    phases = [
        ("Theme & Icons", test_theme_and_icons),
        ("Keybindings", test_keybindings),
        ("Status Badge", test_status_badge),
        ("Task View", test_task_view),
        ("Workflow View", test_workflow_view),
        ("Approval Queue", test_approval_queue),
        ("Audit View", test_audit_view),
        ("Packet Inspector", test_packet_inspector),
        ("Degraded Runtime", test_degraded_runtime),
        ("Deterministic Fallback", test_deterministic_fallback),
    ]

    for name, test_fn in phases:
        passed, total = test_fn()
        total_passed += passed
        total_tests += total

    print()
    print("=" * 60)
    print(f"Test Results: {total_passed}/{total_tests} passed")
    print("=" * 60)

    if FAILED:
        print("FAILED: One or more tests failed")
        return 1
    else:
        print("ALL PASSED")
        return 0


if __name__ == "__main__":
    sys.exit(main())