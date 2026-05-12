# Task Orchestration v0.0.5

## What This Adds

v0.0.5 moves OverCR from static subagent doctrine to **executable task orchestration**. The four subagents (CryER, PypER, CodER, KnowER) already have doctrine, agent definitions, and handoff schemas. What was missing is the **task lifecycle** — how OverCR creates, routes, tracks, and closes tasks across subagents.

This document defines that lifecycle. It does not add live autonomous execution, new subagents, or agent-to-agent loops.

## Design Principles

1. **Filesystem-first.** All task state lives on disk. A cold-start reads the filesystem to reconstruct in-flight tasks. No task state exists only in RAM or chat history.
2. **OverCR is sovereign.** OverCR creates tasks, assigns subagents, routes packets, and closes tasks. Subagents never assign tasks to each other or to OverCR.
3. **Subagents are governed specialists.** Each subagent does exactly what its doctrine permits. The task lifecycle does not expand subagent scope.
4. **No live autonomous execution yet.** v0.0.5 defines the lifecycle and validates packet shape. Actual subagent invocation is simulated or operator-triggered — not autonomous looping.
5. **No uncontrolled agent-to-agent loops.** All routing goes through OverCR. Every hop is a discrete state transition recorded on disk.
6. **Approval gates are enforced, not advisory.** Any packet with `approval_required: true` or any action that doctrine marks as approval-gated must pause for operator approval before proceeding.

## Task Lifecycle

### States

A task moves through exactly these states:

| State | Meaning |
|-------|---------|
| `created` | OverCR has created the task and assigned a subagent. No packet yet. |
| `assigned` | Subagent has acknowledged the assignment. Not yet producing output. |
| `in_progress` | Subagent is actively working. Intermediate state. |
| `response_received` | Subagent has produced a response packet. Awaiting OverCR validation. |
| `validation_passed` | Packet passed shape validation. Awaiting routing decision. |
| `validation_failed` | Packet failed validation. Subagent must fix or OverCR must decide. |
| `routed` | OverCR has decided the next hop (another subagent, operator review, or archive). |
| `approval_pending` | Packet requires operator approval before the next action. |
| `approved` | Operator has approved. Task can proceed to next hop or closure. |
| `rejected` | Operator has rejected. Task returns to subagent for revision or is abandoned. |
| `completed` | Task is finished. All packets archived. No further action. |
| `abandoned` | Task was abandoned. Reason recorded. No further action. |

### State Transitions

```
created → assigned → in_progress → response_received
    ↓                                      ↓
abandoned                          validation_passed → routed
                                        ↓                    ↓
   validation_failed ←←←←←←    approval_pending → approved → (next hop or completed)
                                        ↓                    ↓
                                   rejected            completed
                                        ↓
                              (revision loop or abandoned)
```

Every transition is recorded in the task's state log (see Filesystem Layout below).

### Operator Approval Gate

The approval gate is non-negotiable when:
- The packet has `approval_required: true`
- The packet involves outbound contact (PypER approval packets always)
- The packet involves a destructive or irreversible action (CodER deployment packets, data deletion)
- The packet involves a governance change (never permitted by subagents — escalate to operator)

OverCR enforces this by refusing to advance a task past `routed` into any outbound action without explicit operator approval.

### Revision Loops

If a packet fails validation or is rejected by the operator:
- OverCR may route the task back to the same subagent with a revision request
- Maximum 3 revision loops per task before escalation to operator for re-evaluation
- Each revision increments a `revision_count` field tracked in the task record

## Task ID Format

Tasks are identified by IDs in the format:

```
task-NNNN
```

Where `NNNN` is a zero-padded sequential number starting from `0001`. The counter is stored in `orchestration/task_counter.json`.

For cross-referencing, packets carry:
- `task_id` — the current task
- `upstream_task_id` — the task that seeded this one (or null)

## Subagent Selection

OverCR selects the subagent based on the task's domain:

| Task Domain | Subagent | Packet Types |
|-------------|----------|--------------|
| Public reputation, engagement, hiring, directory signals | CryER | `cryer_recon`, `cryer_update`, `cryer_alert` |
| Outreach drafting, personalization, objection handling | PypER | `pyper_approval`, `pyper_revision`, `pyper_objection_response` |
| Code, scripting, debugging, runtime repair | CodER | `coder_completion`, `coder_blocked`, `coder_diagnostic` |
| Research, fact-checking, myth separation, domain analysis | KnowER | `knower_research`, `knower_assessment`, `knower_myth_separation` |

Multi-hop tasks (e.g., CryER recon → PypER outreach) are modeled as **separate tasks linked by `upstream_task_id`**, not as a single task with multiple subagent assignments. OverCR creates a new task for each hop and routes the upstream packet's output as input context to the downstream task.

## Routing Table

After a subagent produces a validated packet, OverCR routes based on the packet's `next_steps_recommendation` field and its own judgment:

| Upstream | Downstream | What Gets Routed |
|----------|------------|-----------------|
| CryER | PypER | Recon packets for outreach personalization |
| CryER | KnowER | Recon packets for deep analysis |
| KnowER | PypER | Research packets for evidence-backed personalization |
| KnowER | CryER | Research findings for refined targeting scope |
| KnowER | CodER | Domain knowledge to inform implementation |
| PypER | Operator | Approval packets always require operator review |
| CodER | KnowER | Research requests to unblock implementation |
| Any | Archive | Completed tasks with no further routing needed |

OverCR may also decide to route directly to the operator without a downstream subagent (e.g., a CryER alert that needs immediate human attention).

## Memory Updates

After a task reaches `completed` or `abandoned` state:
- OverCR may promote relevant findings from subagent memory to shared memory
- Subagent memory is scoped: each subagent reads/writes only its own `memory/` directory
- Memory promotion is an OverCR decision, not a subagent action

## What v0.0.5 Does NOT Include

- Live autonomous subagent execution (simulated responses only)
- Agent-to-agent communication (all routing through OverCR)
- New subagents
- Outbound contact of any kind
- Web scraping or API integration
- Runtime daemon or long-running process

## Relationship to Existing Doctrine

This document extends — does not replace — the existing subagent doctrine and handoff schemas:
- `subagents/<name>/agent.md` — identity and rules (unchanged)
- `subagents/<name>/doctrine.md` — governance matrix (unchanged)
- `subagents/<name>/handoff_schema.md` — packet schemas (unchanged)
- `orchestration/subagent_packet_lifecycle.md` — how packets move through the system (NEW)
- `orchestration/packet_validation_rules.md` — how packets are validated (NEW)

## Filesystem Layout

```
orchestration/
  task_orchestration_v0.0.5.md       # This document
  subagent_packet_lifecycle.md        # Packet lifecycle state machine
  packet_validation_rules.md          # Validation rules and schemas
  task_counter.json                   # Sequential task ID counter
  tasks/                              # Task state directory
    task-0001.json                    # Individual task records
    task-0002.json
    ...
  examples/
    task_cryer_to_pyper_flow.json     # Multi-hop flow example
    task_knower_to_pyper_flow.json   # Research → outreach flow
    task_coder_patch_flow.json        # Code task flow
tools/
  validate_packet.py                  # Packet validation CLI
```

Each task record (`task-NNNN.json`) contains:

```json
{
  "task_id": "task-0001",
  "upstream_task_id": null,
  "created_at": "ISO8601",
  "created_by": "overcr",
  "assigned_subagent": "cryer",
  "domain": "recon",
  "description": "Public signal reconnaissance on Example Business",
  "state": "response_received",
  "revision_count": 0,
  "state_log": [
    {"state": "created", "timestamp": "ISO8601", "note": "Task created by OverCR"},
    {"state": "assigned", "timestamp": "ISO8601", "note": "Assigned to cryer"},
    {"state": "in_progress", "timestamp": "ISO8601", "note": "CryER acknowledged"},
    {"state": "response_received", "timestamp": "ISO8601", "note": "CryER produced cryer_recon packet"}
  ],
  "request_packet": { ... },
  "response_packet": { ... },
  "validation_result": null,
  "routing_decision": null,
  "operator_approval": null
}
```