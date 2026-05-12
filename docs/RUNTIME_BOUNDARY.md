# OverCR Runtime Boundary — v1.0.0

## Substrate Framing

- **OverCR is a Hermes-first portable orchestration substrate.** Hermes is the reference execution runtime.
- **Open WebUI is an optional secondary visual layer.** Other runtimes are possible but compatibility is not guaranteed.
- **Filesystem-first source of truth.** All canonical state lives on disk. Chat history is ephemeral.
- **No autonomous outbound contact.** OverCR has no network stack; any outbound action requires explicit operator approval.
- **No autonomous filesystem mutation.** Workers produce packets; they do not write files, open sockets, or modify state directly.

## Purpose

This document defines what the OverCR substrate does and does NOT do at the
runtime level. The boundary is strict: OverCR is an orchestration substrate,
not a runtime engine.

---

## 1. OverCR Owns

| Responsibility | Implementation | Notes |
|---|---|---|
| Task lifecycle management | `task_store.py` | 12-state machine, filesystem-backed |
| Packet validation | `tools/validate_packet.py` | 6-level validation |
| Routing decisions | `overcr_runtime.py` ROUTING_TABLE | Domain/subagent-based |
| Approval gate enforcement | `approval_gate.py` | Hard blocks, no override |
| Audit logging | `audit_writer.py` | Append-only JSONL |
| Workflow orchestration | `workflow_graph.py`, `workflow_policy.py`, `workflow_runner.py` | DAG with policy |
| Content safety scanning | `workflow_policy.py` | Shell/network pattern blocks |
| Worker registration | `worker_registry.py` | Compatibility + duplicate checks |
| Model routing (intent) | `model_router.py` | Config-driven model selection |
| Model policy (validation) | `model_policy.py` | Governance constraints on routing |
| Replay / cold start | `replay_runner.py` | Deterministic, read-only |
| Output sanitization | `output_sanitizer.py` | Control char stripping |

---

## 2. OverCR Does NOT Own

| Responsibility | Owner | Why |
|---|---|---|
| Model execution | Host runtime (Hermes) | OverCR is runtime-agnostic |
| Network requests | Host runtime / provider | OverCR has no network stack |
| API key management | Host runtime | OverCR never stores keys |
| Process sandboxing | Host OS / container | OverCR delegates to WorkerRunner |
| Model failover | Host runtime | OverCR provides routing config only |
| Provider connections | Host runtime | OverCR provides intent, not connection |
| UI / TUI | Host runtime | OverCR has no interface layer |

---

## 3. Interface Contracts

### 3.1 Subagent Worker Contract

```
OverCR → Worker:  JSON on stdin  (task request packet)
Worker → OverCR:  JSON on stdout  (response packet)
OverCR ← Worker:  stderr captured  (diagnostics, not state)
```

- Workers MUST produce valid JSON on stdout
- Workers MUST NOT write files, open sockets, or access the network
- Workers MUST exit within timeout or be killed
- Failed/timeout workers: output discarded, task stays in safe state

### 3.2 Host Runtime Contract

```
OverCR → Runtime:  routing decision (model, provider, timeout, prompt)
Runtime → OverCR:  inference result (text/JSON)
```

- OverCR provides WHAT to request (model, domain, prompt template)
- Runtime provides HOW to execute (API call, local inference, cloud provider)
- Runtime MUST respect OverCR's approval gates — no auto-approve
- Runtime MUST NOT modify OverCR's task state or audit log

### 3.3 Operator Contract

```
Operator → OverCR:  approval/rejection decisions, policy configs
OverCR → Operator:  task summaries, approval requests, audit records
```

- Operator decisions are recorded with timestamp and identity
- Operator CANNOT bypass governance (see GOVERNANCE_BOUNDARIES.md)
- Operator CAN: approve/reject, set configs, trigger replay

---

## 4. State Ownership

| State | Written By | Read By | Modified By |
|---|---|---|---|
| Task records | OverCR (TaskStore) | OverCR, audit, replay | OverCR only |
| Audit log | OverCR (AuditWriter) | OverCR, audit_integrity | Append-only |
| Config YAML | Operator (source control) | OverCR (runtime) | Operator only |
| Worker output | N/A (validated, stored in task) | OverCR | Never modified after validation |
| Workflow traces | OverCR (WorkflowRunner) | OverCR, replay | Append-only |
| Boot state | OverCR (generated) | Host runtime | Regenerated each boot |

---

## 5. Failure Modes

| Failure | Detection | Recovery |
|---|---|---|
| Worker timeout | WorkerRunner timeout | Task stays `in_progress`, no state advance |
| Worker crash | Non-zero exit code | Task stays `in_progress`, output discarded |
| Invalid packet | L1-L6 validation | Task enters `validation_failed` |
| Governance violation | Policy engine | Workflow stops, audit entry written |
| Audit log corruption | audit_integrity.py | Tamper detected, operator alerted |
| Config error | Runtime bootstrap | Validation fails, safe defaults applied |
| Model unavailable | Host runtime | Deterministic fallback (if policy allows) |

**Key invariant:** No failure mode can advance task state past an unapproved gate.
A failed worker always leaves the task in a safe, inspectable state.

---

## 6. Swap Compatibility

The substrate is designed to survive runtime swaps:

| Component | Swappable | Requirement |
|---|---|---|
| Host runtime (Hermes → other) | Yes | Must implement runtime contract |
| Model provider (Ollama → other) | Yes | Must provide text/JSON inference |
| Subagent workers | Yes | Must implement stdin/stdout JSON contract |
| Config format (YAML) | No | OverCR reads its own configs directly |
| Audit format (JSONL) | No | Structured log, not for external consumption |
| Task state format (JSON) | No | OverCR-internal filesystem format |

If Hermes is replaced with another runtime, OverCR continues to function as long
as the replacement implements the host runtime contract. Governance, validation,
audit, and routing remain entirely within OverCR's domain.

## 7. Model Output Trust Boundary

All model and subagent output is **untrusted until sanitized and validated**.
OverCR's `output_sanitizer.py` strips control characters, and `validate_packet.py`
enforces 6-level validation (L1–L6) before any packet is used to advance task
state. The host runtime (Hermes) delivers raw inference results; OverCR governs
whether those results become trusted state.

## 8. PypER and CodER Advisory Boundaries

PypER and CodER are **advisory-only** subagents within the workflow boundary:

- **PypER** produces `pyper_execution_plan` packets. These are structured plans,
  not autonomous actions. Operator approval is required before any host runtime
  (Hermes) executes a PypER plan.
- **CodER** produces patch plans and code review packets. No filesystem mutation
  is performed autonomously; operator approval is required before any patch is
  applied.

Workflow choreography remains bounded, audited, and approval-aware at all times.