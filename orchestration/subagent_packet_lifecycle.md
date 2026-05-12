# Subagent Packet Lifecycle

## Overview

This document defines how packets move through the OverCR system — from task creation through subagent processing, validation, routing, and closure. It is the state machine that governs every packet.

## Lifecycle Phases

### 1. Task Creation (OverCR)

OverCR creates a task when:
- The operator requests work
- An upstream packet's `next_steps_recommendation` suggests a downstream subagent
- An alert packet (e.g., `cryer_alert`) requires follow-up

OverCR:
1. Reads `orchestration/task_counter.json` and increments
2. Creates `orchestration/tasks/task-NNNN.json` with state `created`
3. Selects the appropriate subagent based on task domain
4. Constructs a **request packet** — the instruction to the subagent

The request packet is NOT a handoff schema packet (those are subagent → OverCR). It is an OverCR → subagent instruction:

```json
{
  "task_id": "task-0001",
  "assigned_subagent": "cryer",
  "domain": "recon",
  "instruction": "Conduct public signal reconnaissance on Example Business. Focus on reviews, engagement, hiring, and directory presence.",
  "input_context": {
    "entity": "Example Business",
    "type": "business",
    "focus_areas": ["reviews", "engagement", "hiring", "directory"],
    "upstream_task_id": null
  },
  "constraints": [
    "Public signals only. No private data.",
    "No outbound contact.",
    "No automated scraping beyond publicly accessible sources."
  ],
  "required_packet_type": "cryer_recon",
  "created_at": "ISO8601"
}
```

### 2. Subagent Acknowledgment

When a subagent picks up the task (currently simulated):
1. Task state transitions: `created` → `assigned`
2. Subagent logs acknowledgment in `state_log`
3. Subagent begins work: state transitions `assigned` → `in_progress`

### 3. Response Packet Production

The subagent produces a typed response packet according to its `handoff_schema.md`. This packet:
- Must conform to the schema for its `packet_type`
- Must have `source` = the subagent's name
- Must have `target` = `"overcr"`
- Must have `task_id` = the OverCR-assigned task ID
- Must include an `audit_trail` with collection methods and timestamps

Task state transitions: `in_progress` → `response_received`

### 4. Validation

OverCR validates the response packet using `packet_validation_rules.md` and `tools/validate_packet.py`.

**On pass:**
- Task state transitions: `response_received` → `validation_passed`
- Validation result recorded in task record
- Proceed to routing

**On fail:**
- Task state transitions: `response_received` → `validation_failed`
- Validation errors recorded in task record
- OverCR decides: route back to subagent for revision (max 3 loops) or abandon

### 5. Routing Decision

After validation passes, OverCR inspects the packet's `next_steps_recommendation` and makes a routing decision:

| Routing Target | When |
|---------------|------|
| Another subagent | The packet's output is input for a downstream task |
| Operator review | The packet requires human judgment, approval, or action |
| Archive | The task is complete and no further routing is needed |

Task state transitions: `validation_passed` → `routed`

If the packet has `approval_required: true`, the state transitions: `routed` → `approval_pending`

### 6. Multi-Hop (Downstream Task Creation)

If OverCR routes to another subagent:
1. OverCR creates a **new task** for the downstream subagent
2. The new task's `upstream_task_id` references the original task
3. The upstream packet's relevant output becomes `input_context` for the downstream task
4. The cycle repeats from Phase 2

This is how CryER → PypER flows work: two separate tasks, linked by `upstream_task_id`.

### 7. Operator Approval

When a task reaches `approval_pending`:
1. OverCR presents the packet to the operator
2. Operator approves or rejects

**On approval:**
- Task state transitions: `approval_pending` → `approved`
- If a downstream step was waiting on approval, it proceeds
- If the task is terminal, state transitions: `approved` → `completed`

**On rejection:**
- Task state transitions: `approval_pending` → `rejected`
- OverCR may route back to the originating subagent for revision
- If revision limit (3) is reached, task state: `rejected` → `abandoned`

### 8. Completion

A task reaches `completed` when:
- All routing is done
- Operator approval has been granted where required
- No further hops are needed

A task reaches `abandoned` when:
- Validation fails and revision limit is exceeded
- Operator rejects and no revision is possible
- The task is explicitly cancelled by the operator

On completion:
- OverCR may promote relevant findings to shared memory
- The task record is finalized and archived
- The task counter is NOT decremented (IDs are never reused)

## Packet Flow Diagram

```
Operator
   │
   ▼
OverCR ←──────────────────────────────┐
   │                                  │
   │ create task                      │ route to
   │ assign subagent                  │ downstream
   │ construct request packet          │ subagent
   │                                  │
   ▼                                  │
Subagent (CryER/PypER/CodER/KnowER)   │
   │                                  │
   │ produce response packet          │
   │                                  │
   ▼                                  │
OverCR                                │
   │                                  │
   │ validate packet                  │
   │                                  │
   ├── pass → routing decision ───────┤
   │                                  │
   ├── fail → revision loop ──────────┤
   │         (max 3)                   │
   │                                  │
   ├── approval_required              │
   │         │                        │
   │         ▼                        │
   │      Operator                    │
   │      approve/reject              │
   │                                  │
   └── archive → completed            │
                                      │
              (no loops: OverCR is     │
               the sole orchestrator) │
                                      │
              ──────────────────────────┘
```

No subagent ever addresses another subagent. All packets have `target: "overcr"`. All routing goes through OverCR.

## Revision Loop Detail

```
response_received → validation_failed
                         │
                         ▼
                   OverCR decision
                   ├── revision_count < 3 → route back to subagent
                   │                          (new state: assigned,
                   │                           revision_count++)
                   └── revision_count >= 3 → abandon task
                                              (state: abandoned)
```

Each revision must produce a new response packet the subagent. The old failed packet is retained in the task record's `response_packet` history.

## Operator-Facing Final Packet

When a task reaches a terminal state (`completed`, `abandoned`) or requires operator action (`approval_pending`), OverCR produces an **operator-facing final packet**:

```json
{
  "operator_packet_type": "task_summary",
  "task_id": "task-0001",
  "upstream_task_id": null,
  "state": "completed",
  "subagent": "cryer",
  "packet_type": "cryer_recon",
  "summary": "Plain-language summary for the operator",
  "key_findings": [
    "Bullet-pointed findings from the subagent packet"
  ],
  "risk_flags": [
    "Any risk flags identified"
  ],
  "approval_required": false,
  "next_steps": [
    "Suggested next actions the operator can take"
  ],
  "routing_suggestion": "Route to PypER for outreach drafting",
  "timestamp": "ISO8601"
}
```

This is the packet the operator actually sees. Raw subagent packets are stored in the task record but the operator-facing packet is the human-readable distillation.

## Anti-Patterns

- **Never** allow a subagent to create a task. Only OverCR creates tasks.
- **Never** allow a subagent to route directly to another subagent. All `target` fields are `"overcr"`.
- **Never** allow a subagent to bypass validation. Every response packet is validated.
- **Never** allow a subagent to approve its own output. `approval_required: true` in PypER packets is enforced, not advisory.
- **Never** allow unlimited revision loops. Max 3 before abandonment.
- **Never** allow task state to exist only in memory. Every transition is written to the task record on disk.