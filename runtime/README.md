# OverCR Runtime v0.1.0

The first real runtime driver for the OverCR orchestration system.

## What It Is

A minimal, filesystem-first runtime that drives the existing orchestration spec (v0.0.5) into executable operation. It creates task records, assigns IDs, selects subagents, generates request packets, validates response packets, advances lifecycle states, enforces approval gates, writes audit entries, and stores all state on disk.

## What It Is Not

- No live subagent process spawning
- No web crawling or API integration
- No autonomous outbound action
- No database dependency
- No new subagents
- No uncontrolled loops

## Architecture

```
orchestration/                  # Existing core (unchanged)
  task_orchestration_v0.0.5.md
  subagent_packet_lifecycle.md
  packet_validation_rules.md
  task_counter.json
  tasks/                         # Per-task state records
  examples/

runtime/                        # NEW — v0.1.0 runtime
  __init__.py                   # Version marker
  task_store.py                 # Filesystem-backed task CRUD + state machine
  audit_writer.py               # Append-only JSONL audit log
  approval_gate.py              # Enforces approval_required gates
  overcr_runtime.py             # Main runtime driver (ties everything together)
  README.md                     # This file

examples/
  runtime_demo_cryer_to_pyper.py  # Full multi-hop demo
```

## Modules

### task_store.py

Filesystem-backed task record management. Every state transition is written to disk immediately. The filesystem is canonical truth — no task state lives only in memory.

Key operations:
- `create_task()` — assign sequential ID, write request packet, set state to `created`
- `advance_state()` — validate state transitions against the 12-state machine, write to disk
- `load_task()` / `list_tasks()` — read from disk
- `select_subagent()` — map domain to subagent
- `task_summary()` — generate operator-facing summary packet

### audit_writer.py

Append-only audit log writer. Every state transition, validation, routing decision, approval action, and operator interaction is recorded as a JSONL entry.

- Log location: `runtime/audit.jsonl`
- Entry types: `state_transition`, `task_created`, `validation_result`, `routing_decision`, `approval_action`, `revision_loop`, `task_completed`, `task_abandoned`, `runtime_start`, `runtime_stop`, `error`
- Never truncated or rewritten — append only

### approval_gate.py

Enforces the approval_required gate. Key rules:

- PypER packets: always `approval_required=true` (no exceptions)
- Outreach domains: always gated
- From state `routed`, tasks requiring approval MUST go through `approval_pending` — not directly to `completed`
- Outbound action is blocked until explicit operator approval is recorded
- Maximum 3 revision loops before abandonment

### overcr_runtime.py

The main driver that ties everything together:

1. **Create task** — subagent selection, ID assignment, request packet generation
2. **Simulate acknowledgment** — advance through `created → assigned → in_progress`
3. **Receive response** — store response packet, advance to `response_received`
4. **Validate** — run 6-level validator, advance to `validation_passed` or `validation_failed`
5. **Route** — determine next hop (subagent, operator, archive), advance to `routed`
6. **Approval gate** — enforce approval_required, advance to `approval_pending` if needed
7. **Process approval** — operator approve/reject, with revision loop tracking
8. **Outbound block** — final safety check: no outbound action without approval

### Operator Summary Trust Boundary

The `operator_summary()` method enforces a strict trust boundary between untrusted packet payloads and runtime-authenticated governance state:

| Field | Source | Trust Level |
|---|---|---|
| `governance.approval_required` | `ApprovalGate.check_approval_required()` | Runtime-authenticated |
| `governance.outbound_blocked` | `ApprovalGate.should_block_outbound()` | Runtime-authenticated |
| `governance.execution_authority` | Task state + approval record | Runtime-authenticated |
| `governance.validation_passed` | Stored validation result | Runtime-authenticated |
| `packet_claims.approval_required` | Raw response packet | Untrusted — what the packet said |
| `packet_claims.next_steps_recommendation` | Raw response packet | Untrusted — what the packet suggested |
| `packet_claims.outbound_contact` | Raw response packet | Untrusted — what the packet claimed |
| `next_steps` | Task state machine | Runtime-authoritative |

Key guarantees:
- `governance.approval_required` is computed from the approval gate — it can NEVER be `False` for PypER or outreach domains, even if the packet claims otherwise
- `governance.outbound_blocked` reflects the actual enforcement state, not what the packet says
- `packet_claims` honestly records what the packet claimed, but these fields are clearly labeled as untrusted
- `next_steps` are derived from the task's validated state, never from `packet_claims.next_steps_recommendation`

## State Machine

```
created → assigned → in_progress → response_received
    ↓                                      ↓
abandoned                          validation_passed → routed
                                        ↓                ↓
   validation_failed              approval_pending → approved → completed
                                        ↓
                                   rejected
                                        ↓
                              (revision loop or abandoned)
```

Every transition is recorded in the task's `state_log` array and in `runtime/audit.jsonl`.

## Quick Start

Run the demo (uses a temporary workspace):

```bash
cd $OVERCR_ROOT
python examples/runtime_demo_cryer_to_pyper.py --workspace /tmp/overcr-demo
```

Clean up after:

```bash
rm -rf /tmp/overcr-demo
```

## Validation

All response packets are validated using the existing `tools/validate_packet.py` (6-level validation). The runtime imports it dynamically and runs validation on every response packet received.

## Relationship to v0.0.5

The runtime implements the task lifecycle defined in `orchestration/task_orchestration_v0.0.5.md` and `orchestration/subagent_packet_lifecycle.md`. It does not modify any existing doctrine — it provides the executable driver for the static spec.

What changed from v0.0.5 to v0.1.0:
- **New**: Runtime code (`runtime/`) that executes the lifecycle
- **New**: Audit log system (`runtime/audit.jsonl`)
- **New**: Approval gate enforcement module
- **New**: Demo script exercising full CryER→PypER flow
- **Unchanged**: All orchestration spec files, all subagent doctrine, all packet schemas, the validator

## Filesystem Guarantees

- Task records are written to `orchestration/tasks/task-NNNN.json` — never held only in memory
- Task counter is in `orchestration/task_counter.json` — IDs are never reused
- Audit log is append-only at `runtime/audit.jsonl`
- Cold start reads the filesystem to reconstruct in-flight tasks