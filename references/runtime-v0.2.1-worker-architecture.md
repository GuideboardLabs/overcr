# OverCR Runtime v0.2.1 — Worker Architecture

## Release Scope

v0.2.1 is a **stabilization and infrastructure** release. It hardens the live worker framework from v0.2.0 and adds KnowER as the second live worker. It does NOT add new capabilities (no web crawling, browser automation, outbound contact, autonomous loops, database dependencies, or shell command execution).

## New Modules

### runtime/worker_registry.py

Centralized registry for subagent workers. Each worker registers with:

| Field | Type | Description |
|-------|------|-------------|
| `subagent` | str | Subagent name (e.g., "coder", "knower") |
| `version` | str | Worker version (e.g., "0.2.1") |
| `supported_packet_types` | frozenset | Packet types this worker can produce |
| `capability_flags` | frozenset | Safety capability flags |
| `runtime_compat_version` | str | Required runtime version (major.minor must match) |
| `worker_path` | str | Relative path to the worker script |

Key behaviors:
- **Duplicate rejection**: Same subagent + version → `WorkerRegistryError`
- **Conflict rejection**: Same subagent, different version → `WorkerRegistryError` (must deregister first)
- **Packet type ownership**: Two subagents cannot claim the same packet type
- **Runtime compatibility**: Worker's `runtime_compat_version` must match runtime's major.minor

### runtime/worker_capabilities.py

Validates and inspects worker capability declarations:

| Flag | Meaning |
|------|---------|
| `no_network` | Worker makes no network calls |
| `no_shell` | Worker executes no shell commands |
| `no_fs_write` | Worker writes nothing outside temp |
| `no_outbound` | Worker has no outbound capability |
| `readonly_analysis` | Worker produces analysis only |

Required capabilities (every worker must declare): `no_outbound`

Expected per subagent:
- **coder**: `no_network`, `no_shell`, `readonly_analysis`
- **knower**: `no_network`, `no_shell`, `no_fs_write`, `no_outbound`, `readonly_analysis`

### runtime/worker_healthcheck.py

Verifies worker functionality with a minimal probe:

| Check | What it verifies |
|-------|-----------------|
| Launch | Worker starts and exits with code 0 |
| Response | Worker produces valid JSON on stdout |
| Schema | Response has all L1 required fields, correct values |
| Capabilities | Declared capabilities and packet types pass validation |

Safety: Healthcheck is informational only. Failed healthchecks never disable runtime or modify state.

### runtime/replay_runner.py

Deterministic replay of task lifecycle from filesystem state:

- Reconstructs state machine transitions from `state_log`
- Validates every transition against `VALID_TRANSITIONS`
- Runs `AuditIntegrityVerifier` for audit consistency
- Detects tampered audit history
- Checks timestamp ordering
- **Strictly read-only**: never modifies task records, audit logs, or state
- **Deterministic**: same filesystem state → same replay result

### subagents/knower/worker.py

KnowER live worker producing three packet types:

| Packet Type | Domain Trigger | Description |
|-------------|---------------|-------------|
| `knower_research` | research (default) | Full research with findings, sources, gaps |
| `knower_assessment` | analysis | Focused claim verification with verdict |
| `knower_myth_separation` | myth_separation | Myth/fact separation with confidence |

Safety constraints:
- No network access, no shell execution, no filesystem writes
- No outbound capability, no governance override claims
- Confidence ratings: 1 (speculative) to 4 (confirmed)
- All handoffs target `overcr` only

## Worker Contract (unchanged from v0.2.0)

| Aspect | Specification |
|--------|--------------|
| Input | JSON request packet on stdin |
| Output | JSON response packet on stdout |
| Exit 0 | Success — stdout contains valid response |
| Exit nonzero | Failure — caller must NOT trust stdout |
| Timeout | Configurable (default 30s), subprocess killed |
| Side effects | None — workers produce analysis, not changes |

## Capability Checks Flow

```
Task Created
    │
    ▼
SubagentAdapter.invoke()
    │
    ├─→ WorkerRegistry.lookup(subagent) → WorkerRegistration
    │       │
    │       ├─ Compatibility check: runtime_compat_version major.minor matches
    │       └─ Packet type check: worker declares required_packet_type
    │
    ▼
WorkerRunner.run()
    │
    ▼
SubagentAdapter parses response
    │
    ▼
OverCRRuntime.receive_response() + validate_response()
    │
    ▼
6-level validation (unchanged)
```

## Healthcheck Flow

```
WorkerHealthcheck.check_worker_health()
    │
    ├─→ Launch probe (WorkerRunner.run with minimal request)
    │       │
    │       ├─ Check 1: Exit code 0
    │       ├─ Check 2: Valid JSON response
    │       ├─ Check 3: L1 schema fields present and valid
    │       └─ Check 4: Capabilities match registration
    │
    ▼
HealthcheckResult
    {healthy, launch_ok, response_ok, schema_ok,
     capabilities_ok, errors, warnings}
```

## Replay Flow

```
ReplayRunner.replay_all(root)
    │
    ├─→ TaskStore(root) — read all task records
    │
    ├─→ For each task: replay_task()
    │       │
    │       ├─ Walk state_log entries
    │       ├─ Validate each transition against VALID_TRANSITIONS
    │       └─ Flag invalid transitions
    │
    ├─→ AuditIntegrityVerifier.verify()
    │       │
    │       ├─ Cross-reference audit log with task records
    │       ├─ Detect: missing entries, invalid transitions, tampering
    │       └─ Produce integrity_risk: none/low/medium/high
    │
    ├─→ Timestamp ordering check
    │
    ▼
ReplayResult
    {tasks_replayed, steps, inconsistencies,
     integrity_risk, tamper_detected, audit_consistent,
     state_machine_violations, timestamp_ordering_ok}
```

## Updated Adapter: KnowER Registration

```python
SubagentAdapter.WORKER_REGISTRY = {
    "coder": "subagents/coder/worker.py",
    "knower": "subagents/knower/worker.py",
}

SubagentAdapter.LIVE_WORKER_DOMAINS = {
    "code": "coder",
    "diagnostics": "coder",
    "research": "knower",
    "analysis": "knower",
}
```

## Runtime Capabilities (v0.2.1)

| Capability | Status |
|-----------|--------|
| Live subagent process spawning (CodER) | Executable |
| Live subagent process spawning (KnowER) | Executable |
| Worker registry with compatibility checks | Executable |
| Worker capability validation | Executable |
| Worker healthcheck (launch/response/schema/capabilities) | Executable |
| Replay runner (deterministic, read-only) | Executable |
| Worker request/response via subprocess stdin/stdout | Executable |
| Worker timeout enforcement with process kill | Executable |
| Stdout/stderr capture with audit-safe summaries | Executable |
| Failed output never advances task state | Executable (enforced) |
| Governance override claim rejection (Level 5) | Executable |
| Duplicate/conflicting worker registration rejection | Executable |
| Packet type ownership enforcement | Executable |
| Audit consistency verification during replay | Executable |
| Tamper detection for audit history | Executable |
| CryER / PypER workers | Simulated (not yet implemented) |
| Web crawling / data gathering | Not implemented |
| Outbound action | Blocked by design |

## New Guarantees

1. **Registration integrity**: No duplicate or conflicting worker registrations — rejected at registration time
2. **Packet type ownership**: Each packet type belongs to exactly one subagent — conflicts are rejected
3. **Runtime compatibility**: Workers declaring incompatible runtime versions cannot register
4. **Healthcheck safety**: Failed healthchecks are informational only — they never disable runtime or block existing workers
5. **Replay determinism**: Same filesystem state always produces the same replay result
6. **Replay read-only**: Replay never modifies any state — it only reads and reports
7. **Tamper detection**: Replay detects inconsistencies between audit log and task records (missing entries, impossible transitions, out-of-order timestamps)
8. **KnowER safety**: KnowER worker has no network, no shell, no filesystem write, no outbound — produces analysis only

## Remaining Limitations

1. **CryER and PypER workers not yet live** — still simulated
2. **KnowER has no live network access** — research findings are based on input context only
3. **Healthcheck probe is minimal** — does not exercise all packet schemas, just L1 structural
4. **Replay is offline** — it replays from filesystem state, not from live runtime events
5. **No worker sandboxing** — safety is enforced by policy (capability declarations + validation), not OS-level isolation
6. **Worker versioning is manual** — changing a worker requires updating the version string and re-registering