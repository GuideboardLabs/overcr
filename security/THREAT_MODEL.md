# OverCR Threat Model — v0.9.0

## Overview

OverCR is a portable AI orchestration substrate. It coordinates subagent workers
through a governed task lifecycle, but it does NOT execute models itself. The host
runtime (typically Hermes) handles model invocation. This threat model covers the
OverCR substrate only — not the host runtime or model providers.

---

## Trust Boundaries

| Boundary | Inside (Trusted) | Outside (Untrusted) |
|---|---|---|
| Operator → OverCR | Operator CLI decisions, approvals | Any external input or user |
| OverCR → Subagent | OverCR task records, routing decisions | Subagent stdout/stderr (model output) |
| OverCR → Filesystem | Task state, audit log, configs | Any file not written by OverCR |
| OverCR → Network | None — OverCR has no network stack | All network access (blocked by policy) |

## Asset Inventory

| Asset | Location | Sensitivity | Recovery |
|---|---|---|---|
| Task records | `orchestration/tasks/task-*.json` | Medium — operational state | Reconstructible from audit log |
| Audit log | `runtime/audit.jsonl` | High — integrity-critical | Append-only, tamper-detected by `audit_integrity.py` |
| Config files | `config/*.yaml` | Medium — policy definitions | Source-controlled, static |
| Worker output | Task `response_packet` field | Low — always validated before use | Re-run task |
| soul.md | Root | High — identity/doctrine | Source-controlled, integrity-checked |
| Boot state | `overcr_state.json`, `HQ_BOOT_MANIFEST.md` | Low — regenerated each boot | Auto-generated |

## Threat Catalog

### T1: Malicious Subagent Output

**Description:** A subagent worker (compromised or hallucinating model) returns a
packet that contains shell injection, network access instructions, or governance
override claims.

**Attack Vector:** Subagent stdout (stdin/stdout JSON contract).

**Mitigations:**
- 6-level packet validation (L1 structural through L6 type-specific payload)
- `WorkflowPolicy.FORBIDDEN_SHELL_PATTERNS` and `FORBIDDEN_NETWORK_PATTERNS`
- `ApprovalGate` blocks outbound for any task requiring approval
- Failed/timed-out workers never advance task state
- `output_sanitizer.py` strips control chars before audit logging

**Residual Risk:** Pattern-based scanning is not a sandbox. Novel evasion patterns
may bypass string-matching checks. Mitigated by defense-in-depth: even if content
slips through, approval gates block outbound action.

### T2: Governance Override via Packet Claim

**Description:** A subagent packet claims `approval_required: false` or
`governance_override: true` to bypass operator review.

**Attack Vector:** Packet `approval_required` field or governance metadata.

**Mitigations:**
- `ApprovalGate` ignores packet claims for domains/subagents with mandatory approval
  (`ALWAYS_APPROVAL_DOMAINS`, `ALWAYS_APPROVAL_SUBAGENTS`)
- `WorkflowPolicy` enforces per-node and per-edge approval policies
- L5 validation rejects governance override claims in unapproved contexts
- Operator approval is required via explicit `process_approval()`, never inferred

**Residual Risk:** None — approval requirements are defined by OverCR policy, not
by packet claims. Packet claims are informational only.

### T3: Audit Log Tampering

**Description:** An attacker or tool modifies `audit.jsonl` entries to hide
policy violations or state transitions.

**Attack Vector:** Direct filesystem access to `runtime/audit.jsonl`.

**Mitigations:**
- Append-only design — no entries are deleted or modified in normal operation
- `audit_integrity.py` cross-references audit entries against task records
- Tamper detection: missing entries, timestamp inconsistencies, state mismatches
- Audit log is the authoritative record for state reconstruction

**Residual Risk:** If an attacker has filesystem write access and modifies both
audit log AND task records consistently, tampering could go undetected. However,
this requires simultaneous coordinated writes to multiple files and would not
survive a cold-start reconstruction from a clean checkout.

### T4: Direct Subagent-to-Subagent Communication

**Description:** A subagent attempts to route directly to another subagent,
bypassing OverCR's routing and governance.

**Attack Vector:** Worker code or model output that addresses another worker.

**Mitigations:**
- Workers only communicate via stdin/stdout JSON with OverCR as the intermediary
- `WorkflowPolicy.check_edge_handoff()` enforces sovereignty — only valid
  `VALID_HANDOFF_PATHS` are allowed
- All cross-subagent handoffs must go through a recognized OverCR workflow edge
- L1 validation rejects packets with unrecognized `source` fields

**Residual Risk:** If a host runtime routes packets around OverCR, this protection
is bypassed. This is outside OverCR's threat boundary — the host runtime must
respect the substrate's routing contract.

### T5: Path Traversal / Filesystem Escape

**Description:** A subagent attempts to read or write files outside its
designated workspace.

**Attack Vector:** Worker subprocess with filesystem access.

**Mitigations:**
- `WorkerRunner` captures stdout/stderr and does not forward file handles
- Task state is written by OverCR, never by workers directly
- Workers receive input via stdin JSON and return output via stdout JSON
- OverCR does not pass file paths to workers for direct file access

**Residual Risk:** If a worker subprocess is compromised (e.g., code injection in
a model-generated script), it could access the filesystem. This is mitigated by
running workers with minimal privileges and by the host runtime's sandboxing.

### T6: Denial of Service — Excessive Retries

**Description:** A failing subagent triggers unlimited retry loops, consuming
resources.

**Attack Vector:** Repeated task failures with retry requests.

**Mitigations:**
- `ApprovalGate.MAX_REVISION_LOOPS = 3` — hard limit on revision cycles
- `WorkflowNode.max_retries` per node — configurable, defaults to 2
- `WorkflowPolicy.check_retry_allowed()` enforces limits
- After max retries, task enters terminal failure state

**Residual Risk:** None — retry limits are enforced by policy, not advisory.

### T7: Model Prompt Injection via Task Input

**Description:** An attacker crafts task input that injects instructions into the
model prompt when a subagent processes the task.

**Attack Vector:** `input_context` field in task creation.

**Mitigations:**
- Task input is treated as untrusted data by OverCR
- Packet content safety checks scan output (not input) for forbidden patterns
- Approval gates on output limit damage of injected actions
- Workers are expected to sanitize/validate their own inputs

**Residual Risk:** Input-side prompt injection is not directly mitigated by OverCR
because OverCR is a routing/governance layer, not a model execution layer. The
host runtime and model provider are responsible for prompt injection defenses.
OverCR mitigates the *impact* by blocking unapproved outbound actions.

### T8: Config Manipulation

**Description:** Modification of routing or policy configs to weaken governance.

**Attack Vector:** Direct filesystem write to `config/*.yaml`.

**Mitigations:**
- Configs are source-controlled and should be file-permission protected
- `ModelPolicy` validates routing decisions against policy at runtime
- Invalid/corrupt configs cause validation failures, not silent bypass
- Release cleanliness checks verify no unauthorized config changes

**Residual Risk:** If an attacker has filesystem write access to config files and
modifies them between policy loads, weakened governance could take effect. Mitigated
by file permissions and source control integrity.

---

## Threats Outside Scope

These are explicitly NOT part of OverCR's threat model:

| Threat | Reason |
|---|---|
| Model execution security | Host runtime responsibility (Hermes, etc.) |
| Network-level attacks | OverCR has no network stack |
| Provider API key exposure | Not stored or managed by OverCR |
| Model hallucination accuracy | Model output is always untrusted until validated |
| Host OS compromise | Infrastructure security, not application security |

---

## Risk Summary

| ID | Threat | Severity | Likelihood | Mitigation Strength |
|---|---|---|---|---|
| T1 | Malicious subagent output | High | Medium | Strong (defense-in-depth) |
| T2 | Governance override claim | High | Low | Strong (policy overrides claims) |
| T3 | Audit log tampering | Medium | Low | Moderate (cross-reference only) |
| T4 | Direct subagent routing | High | Low | Strong (sovereignty enforced) |
| T5 | Path traversal / filesystem escape | Medium | Low | Moderate (depends on host sandbox) |
| T6 | Excessive retries / DoS | Low | Medium | Strong (hard limits) |
| T7 | Prompt injection via input | High | Medium | Moderate (impact only, not prevention) |
| T8 | Config manipulation | Medium | Low | Moderate (file permissions) |

---

## v0.9.0 Hardening Status

- [x] Threat model documented
- [x] Attack vectors identified with mitigations
- [x] Out-of-scope boundaries defined
- [ ] Penetration testing (deferred — substrate has no network surface)
- [ ] Third-party security audit (deferred — v1.0 milestone)