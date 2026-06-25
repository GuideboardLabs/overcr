# OverCR Operator Interface Layer (v2.2.0)

Terminal-first operator observatory for the OverCR orchestration substrate.

## Architecture

```
tui/
├── __init__.py            # Package init, public exports
├── README.md              # This file
├── theme.py               # Status colors, icons, panel styles
├── keybindings.py          # Declarative keybinding registry
├── dashboard.py            # Main dashboard composing all views
├── task_view.py            # Task lifecycle rendering
├── workflow_view.py        # DAG visualization (ASCII/text)
├── packet_inspector.py     # Packet contents + L1-L6 validation display
├── audit_view.py           # Append-only audit stream viewer
├── approval_queue.py       # Pending approvals + approve/reject paths
├── status_bar.py           # Runtime health summary bar
└── widgets/
    ├── __init__.py
    ├── table.py            # Deterministic table rendering (rich)
    ├── panel.py             # Bordered panel wrapper
    ├── log_view.py          # Append-only log stream widget
    └── status_badge.py      # Colored status badges
```

## Design Principles

1. **Observatory, not cockpit** — The TUI reflects operational truth; it does not create truth.
2. **Filesystem-first** — All data is read from canonical filesystem state on disk.
3. **Read-only rendering** — Views render data; they never advance task state.
4. **Governance through routing** — Approval actions are returned as `ApprovalAction` data objects that must be routed through `OverCRRuntime` + `ApprovalGate`. The TUI never bypasses governance.
5. **Deterministic fallback** — Every view has a `render_plain()` method that produces plain text when rich rendering fails.
6. **Resilient to partial failure** — Missing runtime components produce empty/degraded views, not crashes.

## Views

### Dashboard
The main view. Composes status bar, approval queue, task list, and audit stream into a single overview.

```python
from tui.dashboard import Dashboard

dash = Dashboard(root="/path/to/overcr")
output = dash.render()           # Rich-formatted
plain = dash.render_plain()      # Plain-text fallback
section = dash.render_section("approvals")  # Single section
```

### Task View
Renders task lifecycle state from `orchestration/tasks/`.

```python
from tui.task_view import TaskView

tv = TaskView(root="/path/to/overcr")
tv.render_task_list()                          # All tasks
tv.render_task_list(filter_state="approval_pending")  # Filtered
tv.render_task_detail("task-0565")             # Single task detail
tv.render_task_detail_plain("task-0565")      # Plain fallback
tv.render_workflow_membership("task-0565")     # Workflow refs
```

### Workflow View
Renders workflow DAG as ASCII/text tree.

```python
from tui.workflow_view import WorkflowView

wv = WorkflowView(root="/path/to/overcr")
wv.render_dag(graph_data, node_states={...})   # Rich DAG
wv.render_dag_plain(graph_data, node_states)    # Plain fallback
wv.render_node_states_table(graph_data, node_states)
```

### Packet Inspector
Shows packet contents, validation status, L1-L6 outcomes, provenance, routing metadata, and rejection reasons.

```python
from tui.packet_inspector import PacketInspector

pi = PacketInspector(root="/path/to/overcr")
pi.render_request_packet("task-0565")    # Request packet
pi.render_response_packet("task-0565")    # Response packet
pi.render_validation_status("task-0565")  # L1-L6 breakdown
pi.render_routing_metadata("task-0565")   # Routing decision
pi.render_rejection_reason("task-0565")   # Rejection info
pi.render_plain("task-0565")              # Full plain fallback
```

### Audit View
Renders the append-only audit stream from `runtime/audit.jsonl`.

```python
from tui.audit_view import AuditView

av = AuditView(root="/path/to/overcr")
av.render()                          # Last 50 entries
av.render(filter_task="task-0565")    # Filter by task
av.render(filter_type="approval_action")  # Filter by type
av.render(filter_category="validation")    # Filter by category
av.render_plain()                    # Plain fallback
av.render_entry_detail(entry)        # Single entry detail
```

### Approval Queue
Shows pending approvals with rationale. Approval actions are returned as `ApprovalAction` data objects — they are NOT executed by the TUI.

```python
from tui.approval_queue import ApprovalQueue, ApprovalAction

aq = ApprovalQueue(root="/path/to/overcr")
aq.render_queue()                  # All pending approvals
aq.render_queue_plain()            # Plain fallback
aq.render_detail("task-0565")      # Detail for one approval

# Create proposed actions (NOT executed)
action = aq.propose_approval("task-0565", reason="Looks good", operator="alice")
# action.to_dict() => {"task_id": "task-0565", "action": "approve", ...}
# Route through OverCRRuntime.process_approval() to execute
```

### Status Bar
Runtime health summary: task counts, approval queue depth, memory summary, worker availability.

```python
from tui.status_bar import StatusBar

sb = StatusBar(root="/path/to/overcr")
sb.render()         # Rich-formatted
sb.render_plain()   # Plain fallback
```

## Dependencies

- **rich** (Python library) — Terminal formatting. Already available in the environment.
- **No web/browser dependencies** — Pure terminal output.
- **No cloud dependencies** — All data from local filesystem.
- **No database dependencies** — Reads from JSON files on disk.

## Governance Constraints

| Constraint | Enforcement |
|---|---|
| TUI cannot bypass runtime policy | Approval actions are `ApprovalAction` data, not direct state mutations |
| TUI actions route through governance | Caller must pass actions to `OverCRRuntime.process_approval()` |
| TUI reflects truth, doesn't create it | All views read from canonical filesystem state |
| All operator actions auditable | Approval proposals carry `operator` field, routed through audit |
| No auto-approval | `ApprovalQueue.propose_approval()` returns data, not execution |

## Deterministic Fallback

Every view provides both `render()` (rich) and `render_plain()` (plain text) methods. If rich formatting fails or is unavailable, the plain fallback produces identical semantic content without markup.

## Testing

See `tests/test_tui_views.py` for the full test suite covering:
- Task rendering (list, detail, filtered)
- Workflow DAG rendering
- Approval queue integrity (no auto-approve)
- Audit filtering
- Packet inspection (L1-L6, rejection, routing)
- Degraded runtime behavior (missing data)
- Deterministic fallback rendering