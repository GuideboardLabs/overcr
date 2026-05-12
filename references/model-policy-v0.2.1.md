# OverCR v0.2.1 Model Policy — Governance Hardening Layer

## Overview

The model policy layer adds **governance constraints** to the model routing system. It:

1. **Enforces capability boundaries** - Blocks forbidden capabilities per route/subagent
2. **Prevents authority escalation** - Models can only downgrade, never gain authority
3. **Tracks capability restrictions** - All restrictions logged in audit trail
4. **Validates sovereign boundaries** - Respects local network restrictions
5. **Enforces minimum model classes** - Governance-sensitive tasks require minimum capabilities

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    OverCR Runtime                                 │
│                                                                   │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  Model Router (runtime/model_router.py)                   │  │
│  │  ┌─────────────────────────────────────────────────────┐  │  │
│  │  │  1. Request routing (domain, subagent, task_type) │  │  │
│  │  │  2. Policy validation (model_policy.yaml)          │  │  │
│  │  │  3. Capability check (allowed/forbidden)           │  │  │
│  │  │  4. Minimum class enforcement                      │  │  │
│  │  │  5. Approval gate check                            │  │  │
│  │  │  6. Sovereignty check                              │  │  │
│  │  └─────────────────────────────────────────────────────┘  │  │
│  │         │                                                    │  │
│  │         ▼                                                    │  │
│  │  Model Policy Layer (runtime/model_policy.py)              │  │
│  │  ┌─────────────────────────────────────────────────────┐  │  │
│  │  │  P1. Load policy config                             │  │  │
│  │  │  P2. Validate capabilities                          │  │  │
│  │  │  P3. Check downgrade constraints                    │  │  │
│  │  │  P4. Enforce minimum model class                    │  │  │
│  │  │  P5. Validate approval gates                        │  │  │
│  │  │  P6. Check sovereignty                              │  │  │
│  │  └─────────────────────────────────────────────────────┘  │  │
│  │                                                              │  │
│  └───────────────────────────────────────────────────────────┘  │
│        ▲                                                          │
│        │                                                          │
│  OverCRRuntime.invoke_subagent()                                │
└──────────────────────────────────────────────────────────────────┘
```

## Configuration (`config/model_policy.yaml`)

### Structure

```yaml
version: "0.2.1"

_routes:
  <route_name>:
    allowed_capabilities: [...]
    forbidden_capabilities: [...]
    minimum_model_class: "secure"|"basic"|"standard"|"advanced"|"expert"
    preferred_model_class: "secure"|"basic"|"standard"|"advanced"|"expert"
    approval_required: true|false
    sovereignty: "local"|"external"

_subagents:
  <subagent_name>:
    allowed_capabilities: [...]
    forbidden_capabilities: [...]
    minimum_model_class: "secure"|"basic"|"standard"|"advanced"|"expert"
    preferred_model_class: "secure"|"basic"|"standard"|"advanced"|"expert"
    approval_required: true|false
    sovereignty: "local"|"external"

_model_classes:
  <class_name>:
    capabilities: [...]
    max_token_output: <int>
    max_context: <int>
    network_allowed: true|false

approval_gate:
  tasks_requiring_approval: [...]
  tasks_allowed_without_approval: [...]

audit_policy:
  required_fields: [...]
  log_fallback_decisions: true|false
  log_capability_check: true|false
  log_sovereignty_violation: true|false
```

## Model Class Hierarchy

Model classes form a capability hierarchy where lower classes are **subsets** of higher classes.

| Class | Capabilities | Max Tokens | Max Context | Network |
|-------|-------------|------------|-------------|---------|
| `secure` | readonly | 1K | 4K | ❌ |
| `basic` | readonly, local_only | 2K | 8K | ❌ |
| `standard` | analysis, local_only | 4K | 16K | ❌ |
| `advanced` | research, diagnostics | 8K | 32K | ❌ |
| `expert` | code_generation, outreach, recon | 16K | 64K | ✅ |

### Downgrade Rule
- **Models can only move DOWN the hierarchy** (expert → advanced → standard → basic → secure)
- **Downgrade NEVER gains capabilities** - only removes them
- **Fallback model must have fewer or equal capabilities** than preferred model

## Policy Enforcement Rules

### R1: Capability Validation
```python
# For each routing decision:
allowed = all(caps in route.allowed_capabilities for cap in model.capabilities)
forbidden = any(caps in route.forbidden_capabilities for cap in model.capabilities)
assert forbidden == False
assert allowed == True
```

### R2: Downgrade Constraint
```python
# Preferred and fallback models must satisfy:
preferred_class_level >= fallback_class_level
# (where secure=0, basic=1, standard=2, advanced=3, expert=4)
```

### R3: Minimum Model Class
```python
# Governance-sensitive tasks must have:
routing_result.model_class >= route.minimum_model_class
```

### R4: Approval Gate
```python
# Required tasks must not proceed without approval:
if route.approval_required and not routing_result.approved:
    reject_routing("Approval gate not satisfied")
```

### R5: Sovereignty Check
```python
# Local models cannot be used for network/retrieval tasks:
if route.sovereignty == "local" and "network" in route.allowed_capabilities:
    reject_routing("Local model cannot perform network operations")
```

## Policy Validation Flow

```
┌───────────────────────────────────────────────────────────────┐
│                    Policy Validation                          │
│                                                               │
│  Request routing decision (model, provider, route)           │
│        │                                                        │
│        ▼                                                        │
│  ┌─────────────────────────────────────────────────────┐     │
│  │ 1. Load policy for route/subagent                   │     │
│  │    - Get allowed/forbidden capabilities             │     │
│  │    - Get minimum/preferred model class              │     │
│  │    - Get approval requirement                       │     │
│  │    - Get sovereignty constraints                    │     │
│  └─────────────────────────────────────────────────────┘     │
│        │                                                        │
│        ▼                                                        │
│  ┌─────────────────────────────────────────────────────┐     │
│  │ 2. Check capability overlap                         │     │
│  │    - Model capabilities ⊆ allowed                  │     │
│  │    - Model capabilities ∩ forbidden = ∅            │     │
│  └─────────────────────────────────────────────────────┘     │
│        │                                                        │
│        ▼                                                        │
│  ┌─────────────────────────────────────────────────────┐     │
│  │ 3. Validate downgrade                               │     │
│  │    - fallback_class_level ≤ preferred_class_level   │     │
│  └─────────────────────────────────────────────────────┘     │
│        │                                                        │
│        ▼                                                        │
│  ┌─────────────────────────────────────────────────────┐     │
│  │ 4. Enforce minimum model class                      │     │
│  │    - model_class_level ≥ minimum_class_level        │     │
│  └─────────────────────────────────────────────────────┘     │
│        │                                                        │
│        ▘                                                        │
│  ┌─────────────────────────────────────────────────────┐     │
│  │ 5. Check approval gate                              │     │
│  │    - approval_required → has approval               │     │
│  └─────────────────────────────────────────────────────┘     │
│        │                                                        │
│        ▼                                                        │
│  ┌─────────────────────────────────────────────────────┐     │
│  │ 6. Check sovereignty                                │     │
│  │    - local sovereignty ↔ network_allowed            │     │
│  └─────────────────────────────────────────────────────┘     │
│        │                                                        │
│        ▼                                                        │
│  Validation Result (pass/fail, errors, warnings)             │
└───────────────────────────────────────────────────────────────┘
```

## Audit Logging Requirements

### Required Fields

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `model_selected` | str | Selected model name | `"glm-5.1:cloud"` |
| `provider` | str | Provider identifier | `"ollama-cloud"` |
| `route_used` | str | Route that was selected | `"research"` |
| `subagent` | str | Assigned subagent | `"knower"` |
| `capability_restrictions_applied` | list | Forbidden capabilities blocked | `["network", "retrieval"]` |
| `minimum_class_enforced` | str | Minimum model class required | `"advanced"` |
| `fallback_reason` | str (optional) | Why fallback was triggered | `"timeout on preferred"` |
| `approval_satisfied` | bool | Whether approval gate passed | `true` |
| `sovereignty_verified` | bool | Whether sovereignty rules passed | `true` |

### Example Audit Entry

```json
{
  "entry_type": "policy_validation",
  "timestamp": "2026-05-10T01:15:30.123456+00:00",
  "policy_result": {
    "model_selected": "glm-5.1:cloud",
    "route": "research",
    "subagent": "knower",
    "model_class": "expert",
    "minimum_class_required": "advanced",
    "downgrade_valid": false,
    "capabilities_blocked": [],
    "approval_required": false,
    "approval_satisfied": true,
    "sovereignty_verified": true,
    "validation_status": "passed"
  }
}
```

### Fallback Audit Entry

```json
{
  "entry_type": "policy_fallback",
  "timestamp": "2026-05-10T01:15:30.456789+00:00",
  "policy_result": {
    "preferred_model": "glm-5.1:cloud",
    "fallback_model": "qwen3-coder-next",
    "fallback_reason": "timeout_after_60s",
    "downgrade_was_valid": true,
    "downgrade_details": {
      "preferred_class": "expert",
      "fallback_class": "advanced",
      "capabilities_removed": ["code_generation", "outreach", "recon"],
      "capabilities_retained": ["research", "analysis"]
    },
    "policy_status": "passed"
  }
}
```

## Policy Violations

### V1: Capability Overlap Error
```
Error: Model capabilities conflict with route policy
Route: outreach
Model: qwen3-coder-next
Conflicting capabilities: ["network"]
Route forbidden: ["local_only"]
```

### V2: Downgrade Violation
```
Error: Downgrade would increase authority
Preferred: glm-5.1:cloud (expert)
Fallback: qwen3-coder-next (advanced)
Issue: Fallback model lacks capabilities that preferred had
Resolution: Use qwen3-coder-next as preferred, not fallback
```

### V3: Minimum Class Violation
```
Error: Model class below minimum for route
Route: overcr_hq
Minimum class: expert
Selected class: standard
Required: Increase model class or change route
```

### V4: Approval Gate Violation
```
Error: Route requires approval but none provided
Route: cryer.recon
Approval required: true
Current status: not_passed
Action: Obtain operator approval before proceeding
```

### V5: Sovereignty Violation
```
Error: Model cannot perform network operations
Model: qwen3:4b (local_only capability)
Route: recon (requires network capability)
Sovereignty: local
Issue: Local model may not perform network reconnaissance
Resolution: Use a network-capable model or change route
```

## Policy Levels

| Level | Checks Performed | Use Case |
|-------|-----------------|----------|
| 1 | Syntax validation | Development/testing |
| 2 | Capability overlap | Basic validation |
| 3 | Approval gates | Production with approval flow |
| 4 | Sovereignty + all | Production (recommended) |
| 5 | Full + logging | High-security environments |

## Implementation Notes

### Non-Features (By Design)

- ❌ No model execution (runtime handles execution)
- ❌ No new subagents (existing runtime handles spawning)
- ❌ No network contact (policy is config-only)
- ❌ No browser automation (manual approval flow)
- ❌ No dynamic policy updates (requires file edit)

### Integration Points

1. **ModelRouter.route()** — Policy validation called before routing
2. **AuditWriter** — Policy violations logged to audit trail
3. **SubagentAdapter** — Policy checks before worker invocation

### Future Enhancements

1. Policy hot-reload (watch config files for changes)
2. Policy versioning and migration
3. Policy tests (unit tests for policy rules)
4. Policy UI (visual editor for non-technical users)

## Revision History

- **v0.2.1** — Init: Policy structure, capability constraints, model classes
- **v0.2.2** (future) — Policy versioning, hot-reload, policy tests

## Summary

The model policy layer provides **governance hardening** by:

1. ✅ Enforcing capability boundaries (allowed/forbidden)
2. ✅ Preventing authority escalation (downgrade only)
3. ✅ Tracking restrictions in audit log
4. ✅ Respecting local/sovereign constraints
5. ✅ Validating approval gates

All constraints are **config-driven** and **statically validated** — no runtime behavior changes beyond what's configured.
