# Hermes as Reference Runtime for OverCR

## What Hermes Is

Hermes Agent is a CLI AI agent — a terminal-based operational runtime that executes
model calls, manages sessions, and provides tool access. It is the **primary
reference runtime** for OverCR.

OverCR is a **Hermes-first portable orchestration substrate**. Hermes is its **reference execution runtime**. It defines contracts (doctrine, state,
governance, coordination) but does **not** execute models itself. Hermes provides
the execution layer: model invocation, provider connections, timeout enforcement,
failover, and session management.

## Relationship

```
┌─────────────────────────────────────────────────────────┐
│  OverCR Substrate                                        │
│  (doctrine, state, governance, coordination, CAG)         │
│                                                          │
│  ModelRouter ──► routing decision                        │
│  ModelPolicy ──► governance check                        │
│  TaskStore   ──► filesystem state                        │
│  AuditWriter ──► audit trail                             │
│  Workers     ──► subagent execution                      │
└──────────────────────┬──────────────────────────────────┘
                       │
                       │ OverCR outputs routing/policy
                       │ decisions; Hermes executes them
                       ▼
┌─────────────────────────────────────────────────────────┐
│  Hermes Agent (Reference Runtime)                        │
│  (model execution, provider connections, sessions)       │
│                                                          │
│  - Receives routing decision from OverCR                 │
│  - Invokes the selected model via provider API           │
│  - Handles timeout enforcement                           │
│  - Implements failover to fallback models                │
│  - Manages provider connections (Ollama, OpenAI, etc.)   │
│  - Streams responses back into OverCR task records       │
└─────────────────────────────────────────────────────────┘
```

## Substrate Framing

- **OverCR is a Hermes-first portable orchestration substrate.** Hermes is the reference execution runtime.
- **Open WebUI is an optional secondary visual layer.** Other runtimes are possible but compatibility is not guaranteed.
- **Filesystem-first source of truth.** The filesystem is the canonical interface; chat history is ephemeral.
- **Model output is untrusted until sanitized and validated.** All subagent output passes 6-level validation before state advancement.
- **No autonomous outbound contact.** OverCR never initiates network requests without operator approval.
- **No autonomous filesystem mutation.** Workers produce packets; they do not write files, open sockets, or modify state directly.
- **Workflow choreography is bounded, audited, and approval-aware.** Every workflow DAG is pre-flight checked by policy and produces append-only audit traces.

## How Hermes Drives OverCR

### Boot Sequence

1. User runs `./boot.sh` from `$OVERCR_ROOT`
2. `boot.sh` ensures workspace directories exist, verifies `soul.md` is present
3. `boot.sh` prints a Hermes launch command using `soul.md` as the system file
4. User (or automation) launches Hermes with that command
5. Hermes reads `soul.md` and `prompts/hq_compact_boot.md` to bootstrap context
6. OverCR reconstructs operational identity from filesystem state

### Model Routing Flow

1. A task enters OverCR (domain, instruction, input context)
2. `ModelRouter` produces a routing decision (model, subagent, route)
3. `ModelPolicy` validates the decision against governance rules
4. If policy passes, the routing decision is recorded in the task record
5. Hermes reads the routing decision and invokes the selected model
6. Model response flows back through OverCR for validation and state advancement

### Subagent Worker Execution

1. OverCR creates a task and assigns it to a subagent
2. `SubagentAdapter` resolves the worker path from `WORKER_REGISTRY`
3. `WorkerRunner` launches the worker as a subprocess
4. Worker receives a JSON request on stdin, produces a JSON response on stdout
5. OverCR validates the response (6-level validation)
6. If valid, the task advances through its lifecycle
7. If invalid (malformed, governance override, timeout), the task stays in a safe state

### What OverCR Does NOT Delegate to Hermes

- **Governance enforcement** — approval gates, outbound blocking, sovereignty checks
  are all enforced by OverCR's runtime, not by the model provider
- **Audit logging** — `AuditWriter` writes to the filesystem directly
- **Task state management** — `TaskStore` manages state transitions through the
  12-state machine; Hermes does not advance states directly
- **Packet validation** — `validate_packet.py` enforces 6-level validation before
  any state advancement; Hermes output does not bypass this

## Open WebUI (Optional)

Open WebUI may be used as a secondary visual oversight layer. It provides a
browser-based interface for monitoring tasks, reviewing audit logs, and inspecting
subagent outputs. It does not replace Hermes as the execution runtime.

## Other Runtimes

Other AI agent runtimes or harnesses may adapt the contracts defined here
(`soul.md`, task records, worker protocol, validation rules). Compatibility
is not guaranteed — the filesystem is the canonical interface. Any runtime
that can read/write the OverCR directory structure and honor the governance
contracts can drive OverCR, but only Hermes is tested as the reference
implementation.

## Key Files

| File | Role |
|------|------|
| `boot.sh` | Cold-start script, generates workspace directories, prints Hermes launch command |
| `soul.md` | Identity, rules, workflow — the supreme document |
| `soul_reference.md` | Integrity-check copy |
| `runtime/model_router.py` | Config-driven model selection (intent layer) |
| `runtime/model_policy.py` | Governance constraints (validation layer) |
| `runtime/overcr_runtime.py` | Main driver: creates tasks, validates, routes, advances states |
| `runtime/subagent_adapter.py` | Bridges OverCRRuntime to worker processes |
| `runtime/worker_runner.py` | Subprocess execution with timeout, capture, kill |
| `tools/validate_packet.py` | 6-level packet validator (CLI) |

## Configuration

Hermes-specific configuration is in `$HERMES_HOME` (typically `~/.hermes/`), not in
the OverCR workspace. OverCR configuration is in:

- `config/model_routing.yaml` — domain-to-model mapping
- `config/model_policy.yaml` — capability/class/sovereignty/approval rules
- `configs/*.tpl` — deployment templates (fill and strip `.tpl` extension on deploy)

## Model Output Trust Boundary

All model and subagent output is **untrusted until sanitized and validated**.
Hermes streams raw inference results back to OverCR, but no result is used to
advance task state without passing 6-level validation (L1–L6). OverCR's
`validate_packet.py` is the gate; Hermes does not bypass it.

## PypER and CodER Advisory Boundaries

PypER and CodER are **advisory-only** subagents:

- **PypER** produces `pyper_execution_plan` packets — structured execution
  plans, not executed commands. The plan requires operator approval before any
  host runtime acts on it.
- **CodER** produces patch plans and code review outputs. No code is written
  to the filesystem autonomously; all patch application requires operator
  approval.

These boundaries are enforced by OverCR's governance layer, not by Hermes.