# CodER Worker

## Overview

CodER (Code, Operations, Diagnostics, Execution & Repair) is the code-focused subagent of the OverCR orchestration substrate. Starting with v0.2.0, CodER has a **live worker** that can be invoked as a local subprocess by the OverCR runtime.

## Worker Contract

| Aspect | Specification |
|--------|--------------|
| Input | JSON request packet on stdin |
| Output | JSON response packet on stdout |
| Exit code 0 | Success — stdout contains a valid response packet |
| Exit code nonzero | Failure — caller must NOT trust stdout |
| Timeout | Configurable, default 30 seconds |
| Side effects | None — the worker produces analysis and plans only |

## What CodER Worker Does

- Receives a task instruction and input context via request packet
- For **code** domain: produces a `coder_completion` packet with analysis/findings/plan
- For **diagnostics** domain: produces a `coder_diagnostic` packet with issue analysis
- Produces **harmless deliverables** — plans and reports, never filesystem changes

## What CodER Worker Does NOT Do

- Never modifies files on disk
- Never makes outbound network contact (no HTTP, no email, no API calls)
- Never executes arbitrary shell commands
- Never modifies OverCR doctrine or governance
- Never bypasses approval gates

## Safety Guarantees

1. **Worker output is never trusted.** Every response packet is validated by the OverCR runtime's 6-level validator before advancing task state.
2. **Failed worker output never advances state.** If the worker exits nonzero, times out, or produces invalid JSON, the task enters `validation_failed`, not `completed`.
3. **Timeout kills the process.** The `WorkerRunner` enforces a hard timeout. If the worker doesn't complete within the timeout, it is killed and the task is left in a safe `in_progress` state (the caller handles this).
4. **Stdout/stderr are audit summaries.** Raw output is truncated and control-character-stripped for audit trail storage. The raw output is only used for packet parsing on success.
5. **Governance is enforced at the runtime level.** Even if a worker tried to claim `approval_required: false` on a PypER-type packet, the Level 4 validator would reject it. CodER completion packets with `breaking_changes: true` trigger approval warnings.

## Packet Types

### coder_completion
Produced for code domain tasks. Contains:
- `completion_data.deliverables` — list of plan/report deliverables
- `completion_data.findings` — analysis findings
- `audit_trail.files_modified` — paths that would be affected (plans only, no actual changes)
- `audit_trail.rollback_instructions` — always states no changes made

### coder_diagnostic
Produced for diagnostics domain tasks. Contains:
- `diagnostics` — list of diagnostic findings with severity
- Analysis-only, no system changes

### coder_blocked
Produced when the worker cannot proceed. Contains:
- `blockers` — list of blocking issues with type and description

## Invocation

The worker is invoked by the `SubagentAdapter` through `WorkerRunner`:

```
python3 subagents/coder/worker.py < request_packet.json
```

The request packet is the standard OverCR task request packet containing:
- `task_id` — the task identifier
- `domain` — "code" or "diagnostics"
- `instruction` — what to analyze
- `input_context` — additional context (entity, upstream task, etc.)
- `constraints` — task constraints
- `required_packet_type` — expected response packet type

## Version

CodER worker v0.2.0 (part of OverCR v0.2.0)