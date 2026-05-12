# OverCR Runtime v0.2.0 — Architecture Reference

> Scope: SubagentAdapter, WorkerRunner, CodER worker contract, validation
> boundary, audit-safe summaries, and what v0.2.0 deliberately omits.
> This document describes what exists. It does not prescribe new features.

---

## 1. Overview

v0.2.0 is the smallest safe bridge between OverCRRuntime and real subagent
worker execution. It moves one subagent (CodER) from simulated responses to
live subprocess-based execution while preserving every v0.1.0 safety
guarantee: approval gates, 6-level packet validation, no autonomous outbound
contact, filesystem-first state, and operator-in-the-loop governance.

The bridge is two classes and one worker script:

```
OverCRRuntime
    │
    ▼
SubagentAdapter          ← resolves subagent → worker script
    │
    ▼
WorkerRunner             ← runs subprocess with timeout and capture
    │
    ▼
subagents/coder/worker.py ← stdin JSON → stdout JSON
```

Nothing else changes. CryER, PypER, and KnowER still use simulated
responses. The approval gate still gates. The validator still validates.

---

## 2. SubagentAdapter

**File:** `runtime/subagent_adapter.py`

### 2.1 Purpose

SubagentAdapter is the interface layer between OverCRRuntime and subagent
worker processes. It does three things:

1. **Resolve** a subagent name to a worker script path.
2. **Invoke** the worker with the task's request packet.
3. **Return** a structured result — without advancing state, validating
   packets, or making routing decisions.

### 2.2 Worker Registry

```python
WORKER_REGISTRY = {
    "coder": "subagents/coder/worker.py",
}

LIVE_WORKER_DOMAINS = {
    "code": "coder",
    "diagnostics": "coder",
}
```

Only `coder` has a live worker. All other subagent names return `None` from
`resolve_worker()`, which tells the runtime to fall back to simulated
responses.

### 2.3 Key Methods

| Method | What it does | What it does NOT do |
|---|---|---|
| `resolve_worker(subagent)` | Maps name to filesystem path; returns `None` if no live worker exists | Does not invoke the worker |
| `has_live_worker(subagent)` | Boolean check for live worker availability | — |
| `has_live_worker_for_domain(domain)` | Boolean check via domain-to-subagent mapping | — |
| `invoke(subagent, request_packet, task_id, timeout)` | Runs the worker, returns result dict | Does not validate, advance state, or route |
| `invoke_for_task(runtime, task_id, timeout)` | Loads task from runtime, resolves subagent, calls `invoke()` | Does not advance state |

### 2.4 invoke() Result Dict

```python
{
    "success": bool,           # Worker produced a parseable JSON response
    "response_packet": dict|None,  # Parsed response (None on failure)
    "exit_code": int,         # Process exit code (0=success, -1=error/timeout)
    "timed_out": bool,        # Whether the worker exceeded timeout
    "stdout_summary": str,    # Audit-safe summary (truncated, control chars stripped)
    "stderr_summary": str,    # Audit-safe summary (truncated, control chars stripped)
    "error": str|None,        # Error message on failure
    "worker_path": str,       # Absolute path to the worker script invoked
}
```

The adapter attempts JSON parsing on `stdout_raw` only when `exit_code == 0`.
On timeout, nonzero exit, empty output, or parse failure, `success` is `False`
and `response_packet` is `None`.

### 2.5 Responsibility Boundary

The adapter is intentionally narrow:

- It does NOT validate the response packet. That is the runtime's job via
  `tools/validate_packet.py`.
- It does NOT advance task state. The caller must call
  `runtime.receive_response()` and `runtime.validate_response()`.
- It does NOT make routing decisions.
- It does NOT trust worker output. The `success=True` flag means "the worker
  produced parseable JSON" — it does NOT mean "the packet is valid."

---

## 3. WorkerRunner

**File:** `runtime/worker_runner.py`

### 3.1 Purpose

WorkerRunner executes a subagent worker as a local subprocess with strict
timeout enforcement, full output capture, and audit-safe summaries.

### 3.2 WorkerResult Dataclass

```python
@dataclass
class WorkerResult:
    exit_code: int = -1
    timed_out: bool = False
    stdout_raw: str = ""
    stderr_raw: str = ""
    stdout_summary: str = ""
    stderr_summary: str = ""
    elapsed_seconds: float = 0.0
    error: Optional[str] = None
```

### 3.3 Execution Model

```python
subprocess.run(
    [sys.executable, str(worker_script)],
    input=input_json,       # Request packet as JSON string on stdin
    capture_output=True,
    text=True,
    timeout=timeout,        # Default 30 seconds
)
```

- **Input:** The request packet dict is JSON-serialized and piped to stdin.
- **Output:** stdout is treated as the response packet (JSON). stderr is
  captured for diagnostics only — never parsed as packet data.
- **Invocation:** Uses `sys.executable` to ensure the same Python
  interpreter that runs OverCR also runs the worker.

### 3.4 Timeout Behavior

On `subprocess.TimeoutExpired`:

- `exit_code` is set to `-1` (not a real process exit code).
- `timed_out` is set to `True`.
- `stdout_raw` and `stderr_raw` are populated from the exception's captured
  output (may be empty or partial).
- `error` contains a message like `"Worker timed out after 30.0s (task_id=...)"`.
- The subprocess is killed by Python's `subprocess.run` (SIGKILL on POSIX,
  TerminateProcess on Windows).
- The task is NOT advanced — the caller (SubagentAdapter) returns
  `success=False`, and the runtime leaves the task in its current state.

### 3.5 Failure Behavior

| Condition | exit_code | timed_out | success | What happens to the task |
|---|---|---|---|---|
| Worker exits 0, valid JSON | 0 | False | True | Normal flow — packet goes to validation |
| Worker exits 0, invalid JSON | 0 | False | False | Adapter reports parse error; task not advanced |
| Worker exits nonzero | N | False | False | Adapter reports exit code + stderr; task not advanced |
| Worker times out | -1 | True | False | Adapter reports timeout; task not advanced |
| Worker script not found | -1 | False | False | Adapter reports missing script |
| Worker produces empty output | 0 | False | False | Adapter reports "no output" |
| Unhandled exception in subprocess.run | -1 | False | False | Adapter reports execution failure |

In all failure cases, the response_packet is `None` and the task remains in
its current state (`in_progress` or equivalent). The runtime never
auto-advances a failed task.

### 3.6 Audit-Safe Output Summaries

Worker output is never trusted raw. Both stdout and stderr are summarized
before being returned or logged:

```python
MAX_STDOUT_SUMMARY = 2000
MAX_STDERR_SUMMARY = 1000
```

The `_truncate_for_audit()` function:

1. Strips control characters (non-printable chars are replaced with `\xNN`
   escape sequences).
2. Collapses whitespace to single spaces for single-line audit entries.
3. Truncates to the max length with a `[...truncated, N chars total]` marker.

This prevents a misbehaving worker from flooding audit logs or injecting
uncontrolled multi-line content.

### 3.7 What WorkerRunner Does NOT Do

- Does NOT parse response packets (SubagentAdapter's job).
- Does NOT validate packets (runtime's job).
- Does NOT advance task state (runtime's job).
- Does NOT execute arbitrary shell commands beyond invoking the worker process.
- Does NOT modify the filesystem beyond what `subprocess.run` does.
- Does NOT enforce network isolation (that is a worker policy, not a sandbox).

---

## 4. CodER Worker Contract

**File:** `subagents/coder/worker.py`

### 4.1 Contract

```
Input:  JSON request packet on stdin
Output: JSON response packet on stdout
Exit 0: success (response packet is valid for validation)
Exit nonzero: failure (caller must not trust output)
```

The worker reads the entire stdin stream, parses it as JSON, and writes
exactly one JSON object to stdout. It writes nothing else to stdout.
Diagnostics and errors go to stderr.

### 4.2 Request Packet Fields (input)

The worker reads these fields from the request packet:

| Field | Purpose | Used by |
|---|---|---|
| `task_id` | Task identifier | All packet types |
| `instruction` | What the worker should do | All packet types |
| `domain` | Task domain (`code` or `diagnostics`) | Determines packet type |
| `input_context` | Context dict (entity, upstream task ID, etc.) | All packet types |
| `required_packet_type` | Explicit override for response type | Overrides domain-based routing |

### 4.3 Response Packet Types (output)

| Packet type | When produced | Approval required |
|---|---|---|
| `coder_completion` | Domain `code` (or default) | `False` |
| `coder_diagnostic` | Domain `diagnostics` | `False` |
| `coder_blocked` | `required_packet_type = "coder_blocked"` | `False` |

All CodER packets have `approval_required: False` because CodER produces
analysis and plans — not filesystem changes. The worker never modifies files
or sends outbound contact.

### 4.4 What CodER Does

- Receives a task instruction and input context.
- For `code` domain: produces a `coder_completion` packet with findings and
  deliverable descriptions (plan documents, not file changes).
- For `diagnostics` domain: produces a `coder_diagnostic` packet with issue
  analysis and severity ratings.
- All deliverables describe what *should* be done. The worker never makes
  filesystem changes.

### 4.5 What CodER Does NOT Do

- Never modifies files (produces plans, not patches).
- Never sends emails, HTTP requests, or contacts external services.
- Never modifies OverCR state files.
- Never executes arbitrary code beyond the worker script itself.
- Never sets `approval_required: True` (CodER output is analysis-only).

### 4.6 OUTBOUND_PATTERN Constraint

The 6-level validator's L5 check scans worker output for forbidden patterns:

```python
OUTBOUND_PATTERN = re.compile(
    r'(?:contact|reach\.?out|dm\b|message\s+them)',
    re.IGNORECASE
)
```

Worker output fields (findings, recommendations, diagnostics, summary) must
NOT contain strings matching this regex, except within exempt paths
(`audit_trail`, `raw_sources`, `evidence`).

**Pitfall:** The word "contact" in phrases like "No outbound contact" will
trigger L5 validation failure. CodER uses "No external action" instead.
Workers for other subagents must follow the same convention.

---

## 5. Validation Boundary

After SubagentAdapter returns a result with `success=True`, the runtime still
must validate the packet through all 6 levels of `tools/validate_packet.py`
before any state advancement.

```
Worker output (stdout)
    │
    ▼
SubagentAdapter: JSON parse → success=True
    │
    ▼
OverCRRuntime: receive_response() → store
    │
    ▼
OverCRRuntime: validate_response() → 6-level validation
    │
    ├─ PASS → advance state
    └─ FAIL → validation_failed (task does not advance)
```

The validation levels:

| Level | Name | Checks |
|---|---|---|
| L1 | Structural Integrity | Required fields present, correct types, non-empty summary |
| L2 | Source Integrity | Valid source, permitted packet_type for that source |
| L3 | Temporal Integrity | Valid timestamp, no future dates |
| L4 | Content Completeness | Required payload fields for the packet type |
| L5 | Forbidden Action Flags | No outbound contact instructions, no governance override claims |
| L6 | Required Payload Fields | Type-specific required fields (findings, diagnostics, etc.) |

A packet that passes SubagentAdapter's JSON parse but fails any validation
level is placed in `validation_failed` state. The task does not advance, and
no outbound action occurs.

This means: even if a live worker produces well-formed JSON, the runtime
still enforces the full validation boundary before accepting it.

---

## 6. Approval Gate (Preserved from v0.1.0)

v0.2.0 does not change the approval gate. The gate remains the same:

1. Subagent produces a response packet.
2. Packet passes 6-level validation.
3. If `approval_required: True`, the runtime pauses the task and records
   operator approval before proceeding.
4. If `approval_required: False`, the task auto-advances.

For CodER, all packets have `approval_required: False` because CodER output
is analysis-only. CryER recon packets also have `approval_required: False`
(research is passive). PypER approval packets have
`approval_required: True` by design — outreach drafts require human sign-off
before any outbound action.

The operator approval is recorded in the task record and audit log.
Outbound action (sending an email, making a call) still requires explicit
human action outside the OverCR runtime. The system does not and cannot
execute outbound contact autonomously.

---

## 7. What Remains Simulated

As of v0.2.0, the following subagents still use simulated (hardcoded)
responses built inside OverCRRuntime:

| Subagent | Status | Simulation |
|---|---|---|
| CryER | Simulated | Research/recon packets generated by the runtime |
| PypER | Simulated | Outreach draft packets generated by the runtime |
| KnowER | Simulated | Research/assessment packets generated by the runtime |
| CodER | **Live** | Worker subprocess via SubagentAdapter + WorkerRunner |

To add a live worker for another subagent:

1. Create `subagents/<name>/worker.py` implementing the stdin→stdout contract.
2. Add `<name>: "subagents/<name>/worker.py"` to `SubagentAdapter.WORKER_REGISTRY`.
3. Add domain mappings to `SubagentAdapter.LIVE_WORKER_DOMAINS`.
4. Add a `build_<name>_*_packet()` function in the worker script for each
   packet type that subagent produces.
5. Validate all packet types through the 6-level validator.
6. Test with boundary conditions (timeout, malformed input, nonzero exit).

---

## 8. What v0.2.0 Deliberately Does NOT Include

These are explicit scope exclusions, not missing features or TODOs:

1. **No additional live workers.** Only CodER is live. Adding CryER, PypER,
   or KnowER workers is future work, each requiring its own testing and
   validation boundary analysis.

2. **No network sandbox.** WorkerRunner does not enforce network isolation.
   Workers are constrained by policy (the worker script simply does not
   make network calls), not by OS-level sandboxing. Network sandboxing
   (namespaces, seccomp, containers) is a future infrastructure concern.

3. **No parallel or batch worker execution.** Workers are invoked one at a
   time via `subprocess.run`. There is no worker queue, no concurrency, no
   batch dispatch.

4. **No worker-to-worker communication.** Each worker invocation is
   isolated. Workers cannot call other workers or share state through the
   runtime during execution.

5. **No persistent worker processes.** Each invocation starts a fresh
   subprocess. Workers are stateless — they receive all context in the
   request packet and return all output in the response packet.

6. **No worker health monitoring.** Workers are fire-and-forget subprocesses.
   There is no heartbeat, no readiness check, no restart policy.

7. **No dynamic worker discovery.** The `WORKER_REGISTRY` is a hardcoded
   dict. Workers cannot be registered or removed at runtime.

8. **No output streaming.** Worker stdout is captured in full after the
   process exits. There is no streaming or partial output during execution.

9. **No resource limits beyond timeout.** Workers are limited by wall-clock
   time only. There are no memory limits, CPU limits, or file descriptor
   limits enforced by WorkerRunner.

10. **No changes to the approval gate or governance model.** The v0.1.0
    approval flow is preserved exactly. CodER packets with
    `approval_required: False` skip the gate; PypER packets with
    `approval_required: True` still require human sign-off.

11. **No autonomous outbound contact.** No worker, adapter, or runtime
    component sends email, makes HTTP requests, or contacts external
    services. Outbound action is manual and human-initiated by design.

---

## 9. Data Flow: End to End

### 9.1 CodER (Live Worker)

```
1. Operator submits task (domain=code)
2. OverCRRuntime creates task record (filesystem)
3. OverCRRuntime assigns subagent="coder"
4. SubagentAdapter.has_live_worker_for_domain("code") → True
5. SubagentAdapter.invoke_for_task(runtime, task_id, timeout=30)
6.   WorkerRunner.run(worker_script, request_packet, timeout)
7.     subprocess.run([python, worker.py], input=request_json)
8.     worker.py reads stdin → builds packet → writes stdout
9.     subprocess.run returns (exit_code=0, stdout, stderr)
10.  WorkerRunner produces WorkerResult (raw + summaries)
11.  SubagentAdapter parses stdout JSON → success=True
12.  SubagentAdapter returns result dict to runtime
13. OverCRRuntime.receive_response(response_packet)
14. OverCRRuntime.validate_response() → L1..L6
15. If validation passes → advance task state
16. If validation fails → task enters validation_failed
```

### 9.2 Simulated Subagent (CryER, PypER, KnowER)

```
1. Operator submits task (domain=research)
2. OverCRRuntime creates task record (filesystem)
3. OverCRRuntime assigns subagent="cryer"
4. SubagentAdapter.has_live_worker_for_domain("research") → False
5. OverCRRuntime falls back to simulated response generation
6. Validation and state advancement proceed as above (steps 13-16)
```

---

## 10. Testing

### 10.1 Test Files

| File | Scenarios | Status |
|---|---|---|
| `examples/test_live_coder_worker.py` | 6 scenarios (happy, malformed, timeout, governance, nonzero exit, audit summaries) | All pass |
| `examples/runtime_demo_live_coder.py` | 8-phase live demo | All pass |
| `examples/test_approval_boundary.py` | 51 assertions (v0.1.0 regression) | All pass |
| `examples/test_failure_governance_approval_bypass.py` | Governance bypass (v0.1.0 regression) | All pass |
| `examples/test_rejection_loop.py` | Rejection loop (v0.1.0 regression) | All pass |

### 10.2 Key Test Patterns

- **Timeout:** WorkerRunner kills the subprocess after the timeout; task is
  not advanced; result has `timed_out=True`, `success=False`.
- **Nonzero exit:** Worker exits with code 1; `success=False`; caller does
  not attempt to parse stdout.
- **Malformed JSON:** Worker exits 0 but produces invalid JSON; adapter
  reports parse error; `success=False`.
- **Governance override:** Worker produces a packet claiming authority;
  L5 catches it; packet fails validation.
- **OUTBOUND_PATTERN:** Worker output containing "contact", "reach out",
  "dm", or "message them" triggers L5 failure (except in exempt paths).

---

## 11. File Map

```
runtime/
  __init__.py                  # Version 0.2.0
  overcr_runtime.py             # Core runtime (unchanged from v0.1.0)
  task_store.py                 # Filesystem task store (unchanged)
  approval_gate.py              # Approval gate (unchanged)
  audit_writer.py               # Audit log writer (unchanged)
  subagent_adapter.py           # NEW: Interface to worker processes
  worker_runner.py              # NEW: Subprocess executor with timeout/capture

subagents/
  coder/
    worker.py                   # NEW: CodER live worker
    worker_README.md            # NEW: Worker documentation

tools/
  validate_packet.py            # 6-level validator (unchanged)

examples/
  test_live_coder_worker.py     # NEW: 6 test scenarios
  runtime_demo_live_coder.py    # NEW: 8-phase demo
  test_approval_boundary.py     # v0.1.0 regression (51 assertions)
  test_failure_governance_approval_bypass.py  # v0.1.0 regression
  test_rejection_loop.py        # v0.1.0 regression
  runtime_demo_cryer_to_pyper.py # v0.1.0 demo
```