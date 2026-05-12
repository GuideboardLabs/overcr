# OverCR Governance Boundaries — v1.0.0

## Substrate Identity

- **OverCR is a Hermes-first portable orchestration substrate.** Hermes is the reference execution runtime.
- **Open WebUI is an optional secondary visual layer.** Other runtimes are possible but compatibility is not guaranteed.
- **Filesystem-first source of truth.** All canonical state lives on disk. Chat history is ephemeral.

## Purpose

This document defines the hard boundaries between OverCR's governance layer
and the rest of the system. These boundaries are enforced in code, not advisory.

---

## 1. Subagent Sovereignty

**Rule:** OverCR is the only router. Subagents NEVER call each other directly.

|| From | To | Path | Status |
|---|---|---|---|
|| KnowER | CryER | KnowER→OverCR→CryER | Allowed |
|| CryER | PypER | CryER→OverCR→PypER | Allowed |
|| CodER | PypER | CodER→OverCR→PypER | Allowed |
|| Any | Any (direct) | Subagent→Subagent | FORBIDDEN |

**Enforcement:** `WorkflowPolicy.check_edge_handoff()` rejects any edge not in
`VALID_HANDOFF_PATHS`. `check_direct_subagent_routing` test (L1+L5 rejection)
verifies this at runtime.

---

## 2. Approval Gates

**Rule:** No outbound action without explicit operator approval.

|| Condition | Approval Required | Override Possible |
|---|---|---|---|
|| PypER packet of any type | ALWAYS | No |
|| Outreach/outreach_draft domain | ALWAYS | No |
|| Packet claims `approval_required: true` | ALWAYS | No |
|| Packet claims `approval_required: false` | Check policy (claims ignored) | N/A |
|| Packet claims `governance_override: true` | ALWAYS (claim rejected at L5) | No |

**Enforcement:** `ApprovalGate.enforce_gate()` hard-blocks state transitions.
`ApprovalGate.check_approval_required()` uses `ALWAYS_APPROVAL_SUBAGENTS` and
`ALWAYS_APPROVAL_DOMAINS` — packet claims cannot override these.

---

## 3. Outbound Blocking

**Rule:** No autonomous outbound contact. Ever.

The `ApprovalGate.should_block_outbound()` method is the final safety gate.
It returns `(blocked=True, reason)` unless:
1. The task has `approval_required=False` (by policy, not by packet claim), OR
2. The operator has explicitly approved with `process_approval(decision="approved")`

No code path in OverCR initiates outbound network requests, sends email,
makes API calls, or writes to external systems.

---

## 4. Model Output Trust Boundary

**Rule:** All model/subagent output is UNTRUSTED until validated.

|| Validation Level | Check | Failure Action |
|---|---|---|---|
|| L1 | Structural (required fields present) | Reject packet |
|| L2 | Type registration (known packet_type) | Reject packet |
|| L3 | Source-packet consistency | Reject packet |
|| L4 | Approval gate enforcement | Block outbound |
|| L5 | Forbidden action scan | Reject packet |
|| L6 | Type-specific payload validation | Reject packet |

Model output is NEVER used to advance task state without passing all 6 levels.
Failed validation → task enters `validation_failed` state. No retry without
operator intervention or policy-allowed retry.

---

## 5. Audit Integrity

**Rule:** The audit log is append-only and cross-referenced.

- `audit_writer.py` only appends entries — no update, no delete
- `audit_integrity.py` cross-references audit entries against task records
- Tamper detection: missing entries, timestamp inconsistencies, state mismatches
- Cold-start reconstruction can rebuild task state from audit log + filesystem

**Inviolable:** No code path may delete or modify an audit entry after writing.

---

## 6. Workflow Policy Boundaries

|| Policy | Rule | Enforcement |
|---|---|---|---|
|| No shell execution | FORBIDDEN_SHELL_PATTERNS blocked in packets | `WorkflowPolicy._check_packet_content_safety()` |
|| No network access | FORBIDDEN_NETWORK_PATTERNS blocked in packets | `WorkflowPolicy._check_packet_content_safety()` |
|| No filesystem mutation by inference | Workers cannot write files | `WorkerRunner` captures stdout only |
|| Deterministic fallback | Only when inference fails AND policy allows | `WorkflowPolicy.check_deterministic_fallback()` |
|| Retry limits | Hard max per node (default 2) | `WorkflowPolicy.check_retry_allowed()` |
|| Revision loops | Hard max 3 revision cycles | `ApprovalGate.MAX_REVISION_LOOPS` |

All workflow choreography is **bounded, audited, and approval-aware**. Every
workflow DAG undergoes pre-flight policy checking, produces append-only audit
traces, and respects approval gates at each handoff.

---

## 7. PypER and CodER Advisory Boundaries

**Rule:** PypER and CodER are advisory-only. They produce plans, not actions.

- **PypER** outputs `pyper_execution_plan` packets. These are structured
  execution plans. They are NEVER executed autonomously. Operator approval is
  required before any host runtime (Hermes) acts on a PypER plan.
- **CodER** outputs patch plans and code review packets. No filesystem write
  is performed autonomously. Operator approval is required before any patch
  is applied.

**Enforcement:** `ApprovalGate` blocks all PypER packets (`ALWAYS_APPROVAL_SUBAGENTS`).
Workflow policy pre-flight checks ensure no shell or network patterns appear
in advisory output. Deterministic fallback may provide a safe plan if live
inference fails, but even fallback plans require approval.

---

## 8. Operator Trust Boundary

**Rule:** The operator is trusted for decisions, untrusted for governance bypass.

- Operator CAN: approve/reject tasks, provide context, set policies
- Operator CANNOT: bypass approval gates, override sovereignty rules, modify
  audit entries, route packets around validation

Even the operator cannot make OverCR skip validation. If a packet fails L1-L6,
no operator override mechanism exists — the packet is simply invalid.

---

## 9. Runtime vs Governance Boundary

|| Layer | Owns | Cannot |
|---|---|---|---|
|| Governance (OverCR) | Routing decisions, approval gates, audit, validation | Execute models, access network, modify filesystem |
|| Runtime (Hermes/host) | Model invocation, provider connections, timeout enforcement | Bypass governance, skip validation, auto-approve tasks |
|| Subagents | Domain-specific inference and packet production | Route to other subagents, approve own output, write to audit |

This boundary is structural, not configurable. No YAML flag or environment variable
can weaken governance enforcement.
