# OverCR Testing Reference — v0.2.3

## Consolidated Test Suite

As of v0.2.3, all regression tests are unified under a single runner.

### Running Tests

```bash
# Run the full suite
python3 tests/run_all.py

# Stop on first failure
python3 tests/run_all.py --fail-fast

# Run only governance tests
python3 tests/run_all.py --category governance

# Run a single test by name
python3 tests/run_all.py --test approval_boundary
```

All tests use `$OVERCR_ROOT` or dynamic `Path(__file__)` derivation — no hardcoded paths.

### Test Manifest

The test suite is defined in `tests/test_manifest.json`. Each entry specifies:

| Field | Description |
|-------|-------------|
| `name` | Short test identifier |
| `module` | Python module path (under `examples/`) |
| `callable` | Function to call, or `null` if the module's `main()` is the entry point |
| `category` | Grouping: governance, validation, sovereignty, recovery, audit, worker, routing |
| `description` | Human-readable summary |
| `accepts_workspace` | Whether the callable accepts a workspace path argument |
| `returns_exit_code` | Whether the callable returns 0/1 as pass/fail |
| `signal` | How the test signals results: `exit_code`, `global_flag`, `sys_exit`, `exception_only`, `run_functions` |

### Result Signaling

Tests use different conventions for signaling pass/fail:

| Signal | How it works | Examples |
|--------|-------------|----------|
| `exit_code` | Callable returns `0` (pass) or `1` (fail) | approval_boundary, governance_bypass, rejection_loop, malformed_packet, live_coder_worker |
| `global_flag` | Module sets `FAILED` or `_FAILED` global | live_knower_worker, model_router |
| `sys_exit` | Module's `main()` calls `sys.exit(code)` — runner intercepts | direct_subagent_routing, doctrine_conflict, cold_start_reconstruction, audit_integrity |
| `exception_only` | No explicit signal — pass if no exception | audit_integration |
| `run_functions` | Runner calls a list of functions by name | model_policy_violations |

The runner intercepts `sys.exit()` calls so individual test failures don't abort the suite.

### Test Categories

| Category | Tests | What they verify |
|----------|-------|-----------------|
| governance | approval_boundary, governance_bypass, rejection_loop, doctrine_conflict | Approval gates, bypass prevention, revision loops, L5 pattern detection |
| validation | malformed_packet | 6-level packet validation |
| sovereignty | direct_subagent_routing | No subagent-to-subagent handoffs, L1+L5 rejection |
| recovery | cold_start_reconstruction | Filesystem-first reconstruction after runtime loss |
| audit | audit_integrity, audit_integration | Audit log integrity, policy violation logging |
| worker | live_coder_worker, live_knower_worker | Live subprocess worker execution, validation, safety |
| routing | model_router, model_policy_violations | Model routing, policy downgrade/sovereignty enforcement |

### Test Descriptions

| Test | Assertions | Key guarantees |
|------|-----------|----------------|
| approval_boundary | 51 | PypER always gated; outbound blocked until approved; operator summary gate-authenticated |
| governance_bypass | 24 | 3 independent enforcement layers block PypER bypass |
| rejection_loop | 24 | 3 revision cycles then abandonment; state machine prevents advancement |
| malformed_packet | 29 | L1 structural rejection; invalid packets never advance state |
| direct_subagent_routing | 15 phases | L1+L5 reject direct subagent addressing; state machine blocks forward progress |
| doctrine_conflict | 15 phases | L5 catches governance override claims; immutable approval gates |
| cold_start_reconstruction | 66 | Task counter, state, audit trail, pending approvals all reconstruct from filesystem |
| audit_integrity | 17 | Missing entries, invalid transitions, tampered states detected; runtime continues |
| live_coder_worker | 6 scenarios | Happy path, malformed, timeout, governance override, nonzero exit, audit summaries |
| live_knower_worker | 4 suites | KnowER 3 packet types, healthcheck, replay, registry+capabilities |
| model_router | 6 | Basic routing, subagent override, task-type override, fallback, audit, validation |
| model_policy_violations | 3 | Downgrade violation, sovereignty violation, minimum-class violation — all rejected |
| audit_integration | Policy events | Policy violations logged to audit trail |

### Individual Demos (preserved in examples/)

The following are demos, not regression tests — they produce narrative output but have no pass/fail assertions:

- `examples/runtime_demo_cryer_to_pyper.py` — Full multi-hop flow demo
- `examples/runtime_demo_live_coder.py` — Live CodER worker demo
- `examples/runtime_demo_live_knower.py` — Live KnowER worker demo

These remain in `examples/` and can still be run individually.

### Architecture

```
tests/
  run_all.py              # Unified test runner
  test_manifest.json      # Test registry (name, module, callable, category, signal type)

examples/                 # Original test scripts (unchanged, still individually runnable)
  test_approval_boundary.py
  test_failure_governance_approval_bypass.py
  test_rejection_loop.py
  test_malformed_packet.py
  test_direct_subagent_routing.py
  test_doctrine_conflict.py
  test_cold_start_reconstruction.py
  test_audit_integrity.py
  test_live_coder_worker.py
  test_v021.py                       # KnowER + registry + healthcheck + replay
  test_model_router.py
  test_v021_routing_policy_violations.py
  test_audit_integration.py
```

The test runner imports directly from `examples/` — no wrappers, no duplication. Tests remain in their original location. The runner intercepts `sys.exit()` so individual test failures don't abort the suite.

### Pitfalls

- **sys.exit interception**: Tests that call `sys.exit()` directly are intercepted by the runner. Only `main()` entry points are intercepted; if a test spawns subprocesses that exit, those are not intercepted.
- **Workspace cleanup**: Tests that create workspaces have them cleaned up by the runner via `tempfile.mkdtemp()` + `shutil.rmtree()`.
- **Global FAILED flags**: Modules using `FAILED` or `_FAILED` globals are checked after execution. If a test resets the flag mid-run, the final value is what counts.
- **Model policy tests**: `test_v021_routing_policy_violations` runs two explicit test functions (`test_policy_violation_scenarios` and `test_downgrade_constraint`) — the runner calls both sequentially.
- **No runtime behavior changes**: The test runner only observes; it does not modify runtime code, routing policy, or governance rules.