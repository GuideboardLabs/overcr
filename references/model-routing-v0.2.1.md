# OverCR v0.2.1 Model Routing Extension — Reference Documentation

## Overview

The model routing extension adds a **config-driven** routing layer to OverCR that:

1. Assigns different models/providers by **route**, **subagent**, and **task type**
2. Supports **automatic fallback** on timeout or empty response
3. Records all routing decisions in the **audit log**
4. **Never advances task state** on routing failure
5. Remains **runtime-agnostic** — not a provider lock-in

## Architecture Clarification

### OverCR Is a Substrate, Not a Runtime

**OverCR is a portable orchestration substrate** — it defines contracts, state, governance, and coordination, but does NOT execute models itself.

- **Hermes** is the primary reference runtime and operator interface
- **Open WebUI** is optional as a secondary visual layer
- Other runtimes may adopt OverCR substrate contracts at their discretion
- Hermes is the **supported test path** and runtime integration

```
┌─────────────────────────────────────────────────────────────┐
│                    OverCR Substrate                          │
│                                                               │
│  Model Routing Layer (runtime/model_router.py)               │
│  Model Policy Layer (runtime/model_policy.py)                │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  Policy Layer                                          │  │
│  │  ┌─────────────────────────────────────────────────┐  │ │
│  │  │  Config-driven routing decisions                 │  │ │
│  │  │  • Route-based model selection                   │  │ │
│  │  │  • Capability constraints                        │  │ │
│  │  │  • Minimum model class enforcement               │  │ │
│  │  │  • Approval gate enforcement                     │  │ │
│  │  │  • Sovereignty constraints                       │  │ │
│  │  └─────────────────────────────────────────────────┘  │ │
│  │  ┌─────────────────────────────────────────────────┐  │ │
│  │  │  Intent layer (NOT execution)                   │  │ │
│  │  │  • Model: "glm-5.1:cloud"                       │  │ │
│  │  │  • Provider: "ollama-cloud"                    │  │ │
│  │  │  • Timeout: 60s                                │  │ │
│  │  └─────────────────────────────────────────────────┘  │ │
│  └───────────────────────────────────────────────────────┘  │
│        ▲                                                      │
│        │                                                      │
│  Request routing (domain, subagent, task_type)              │
└──────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│                    Host Runtime (Hermes)                     │
│                                                               │
│  Provider Layer (Ollama Cloud, etc.)                        │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  Model Execution:                                      │  │
│  │  • glm-5.1:cloud on ollama-cloud                     │  │
│  │  • Timeout enforcement                               │  │
│  │  • Response capture                                 │  │
│  │  • Failover to fallback model (if supported)        │  │
│  └───────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

### Provider Failover: Policy-Mode Only

**Provider failover is policy-mode unless the host runtime supports actual model switching.**

- OverCR's policy layer **suggests** fallback models based on config
- Real failover happens in the host runtime/provider layer
- Hermes (as reference executor) implements provider fallback
- Other runtimes may implement failover differently or not at all

```yaml
# Policy defines intent, not execution
_routes:
  research:
    preferred_model: "glm-5.1:cloud"
    fallback_model: "qwen3-coder-next"
    provider: "ollama-cloud"
    timeout: 120

# In practice:
# 1. Policy layer selects "glm-5.1:cloud" for research tasks
# 2. Host runtime (Hermes) attempts to execute with that model
# 3. On timeout, runtime attempts fallback to qwen3-coder-next
# 4. Policy layer logs the fallback decision (audit trail)
```

## Configuration (`config/model_routing.yaml`)

### Structure

```yaml
version: "0.2.1"

_routes:
  <route_name>:
    preferred_model: "<model:tag>"
    fallback_model: "<model:tag>"
    provider: "<provider_name>"
    timeout: <seconds>

_subagents:
  <subagent_name>:
    preferred_model: "<model:tag>"
    fallback_model: "<model:tag>"
    provider: "<provider_name>"
    timeout: <seconds>

_routes_to_subagents:
  <route_name>: <subagent_name>

_audit:
  enabled: true
  log_model_selection: true
  log_fallback_count: true
  log_failure_reason: true
```

### Routes

| Route | Description | preferred_model | fallback_model | provider | timeout |
|-------|-------------|-----------------|----------------|----------|---------|
| `overcr_hq` | OverCR HQ tasks | `glm-5.1:cloud` | `qwen3-coder-next` | `ollama-cloud` | 60s |
| `code` | Code tasks | `qwen3-coder-next` | `glm-5.1:cloud` | `ollama-cloud` | 90s |
| `research` | Research tasks | `glm-5.1:cloud` | `qwen3-coder-next` | `ollama-cloud` | 120s |
| `diagnostics` | Diagnostics | `qwen3-coder-next` | `glm-5.1:cloud` | `ollama-cloud` | 90s |
| `analysis` | Analysis tasks | `glm-5.1:cloud` | `qwen3-coder-next` | `ollama-cloud` | 120s |
| `outreach` | Outreach tasks | `glm-5.1:cloud` | `qwen3-coder-next` | `ollama-cloud` | 90s |
| `recon` | Recon tasks | `glm-5.1:cloud` | `qwen3-coder-next` | `ollama-cloud` | 90s |
| `local_boot` | Local boot tasks | `qwen3:4b` | `glm-5.1:cloud` | `ollama` | 180s |
| `default` | Default route | `qwen3-coder-next` | `glm-5.1:cloud` | `ollama-cloud` | 60s |

### Subagents

| Subagent | preferred_model | fallback_model | provider | timeout |
|----------|-----------------|----------------|----------|---------|
| `coder` | `qwen3-coder-next` | `glm-5.1:cloud` | `ollama-cloud` | 90s |
| `knower` | `glm-5.1:cloud` | `qwen3-coder-next` | `ollama-cloud` | 120s |
| `cryer` | `glm-5.1:cloud` | `qwen3-coder-next` | `ollama-cloud` | 90s |
| `pyper` | `glm-5.1:cloud` | `qwen3-coder-next` | `ollama-cloud` | 120s |

## Resolution Priority

1. **Task override** — explicit `task_type` in request packet
2. **Subagent-specific model** — `subagents.<name>.preferred_model`
3. **Route-specific model** — `routes.<route>.preferred_model`
4. **Default fallback** — `routes.default.preferred_model`

### Fallback Policy

- **First failure** (timeout/empty response) → automatic fallback to `fallback_model`
- **Second failure** → routing decision recorded, task state NOT advanced
- **No outbound action** — routing failure is internal only
- **All decisions logged** in audit entries

## API

### `ModelRouter.route(task_id, domain, assigned_subagent, task_type, request_packet)`

Route a task to an appropriate model/provider.

```python
from runtime.model_router import ModelRouter

router = ModelRouter()
result = router.route(
    task_id="task-0001",
    domain="research",
    assigned_subagent="knower",
    task_type=None,  # Optional override
)
# result.model → "glm-5.1:cloud"
# result.provider → "ollama-cloud"
# result.route_used → "research"
```

### `RoutingResult` Object

| Field | Type | Description |
|-------|------|-------------|
| `model` | str | Selected model (e.g., `"glm-5.1:cloud"`) |
| `provider` | str | Selected provider (e.g., `"ollama-cloud"`) |
| `route_used` | str | Route used (e.g., `"research"`) |
| `fallback_used` | bool | Whether fallback model was used |
| `fallback_reason` | str | Why fallback was needed (if applicable) |
| `task_id` | str | Task identifier (for audit) |
| `subagent` | str | Assigned subagent (if known) |

### Audit Log

Each routing decision produces an audit entry:

```json
{
  "entry_type": "model_selection",
  "details": {
    "model_selected": "glm-5.1:cloud",
    "provider": "ollama-cloud",
    "route_used": "research",
    "fallback_used": false,
    "task_id": "task-0001",
    "subagent": "knower"
  }
}
```

On fallback:

```json
{
  "entry_type": "model_fallback",
  "details": {
    "model_selected": "qwen3-coder-next",
    "provider": "ollama-cloud",
    "route_used": "research",
    "fallback_used": true,
    "fallback_reason": "Empty response or timeout on preferred model",
    "task_id": "task-0001"
  }
}
```

## Integration with Hermes (Reference Runtime)

### OverCR Substrate Layer (Current)

```
runtime/model_router.py  →  Config-driven routing decisions
runtime/model_policy.py  →  Governance constraints
```

### Hermes Runtime Layer (Execution)

```python
# Hermes implements actual execution
# OverCR substrate provides routing/policy decisions
# Hermes delegates to appropriate provider/model

from runtime.model_router import ModelRouter
from runtime.model_policy import ModelPolicy

router = ModelRouter()
policy = ModelPolicy()

# 1. Determine intended model via routing policy
routing = router.route(task_id, domain, subagent)

# 2. Validate against governance policy
policy_valid = policy.validate_routing(
    model=routing.model,
    route=routing.route_used,
    subagent=subagent
)

# 3. Execute via Hermes provider layer
if policy_valid:
    response = hermes_executor.invoke(
        model=routing.model,
        provider=routing.provider,
        prompt=prompt
    )
else:
    reject_task("Policy violation")
```

### Provider Failover in Hermes

```yaml
# Policy defines intent
_routes:
  research:
    preferred_model: "glm-5.1:cloud"
    fallback_model: "qwen3-coder-next"
    provider: "ollama-cloud"
    timeout: 120

# Execution in Hermes
hermes_executor.invoke(
    model="glm-5.1:cloud",
    provider="ollama-cloud",
    timeout=120
)
# On timeout → automatically retry with fallback_model
```

## Usage in OverCRRuntime

```python
# In OverCRRuntime.invoke_subagent()
from runtime.model_router import ModelRouter
from runtime.model_policy import ModelPolicy

class OverCRRuntime:
    def __init__(self, root):
        # ... existing init ...
        self.model_router = ModelRouter(root)
        self.model_policy = ModelPolicy(root)

    def invoke_subagent(self, task_id, timeout=30.0):
        task = self.task_store.load_task(task_id)
        
        # Route to appropriate model (policy Intent Layer)
        routing = self.model_router.route(
            task_id=task_id,
            domain=task.get("domain"),
            assigned_subagent=task.get("assigned_subagent"),
        )
        
        # Validate against governance (Policy Enforcement Layer)
        policy_result = self.model_policy.validate_routing(
            model=routing.model,
            route=routing.route_used,
            subagent=routing.subagent,
        )
        
        # Record routing decision in audit
        self.audit.model_selection(task_id, routing.to_dict())
        
        # Execute only if policy valid
        if not policy_result.valid:
            self.audit.policy_violation(task_id, policy_result.to_dict())
            return {"success": False, "error": "Policy violation"}
        
        # Pass to host runtime (Hermes) for actual execution
        # Hermes delegates to provider/model based on routing decision
        return self.host_runtime.execute(task_id, routing)
```

## Integration Points

### 1. Task Creation (`create_task`)

```python
# After domain/subagent resolution, route before task creation
routing = self.model_router.route(
    task_id=task_id,
    domain=domain,
    assigned_subagent=subagent,
)
policy_result = self.model_policy.validate_routing(
    model=routing.model,
    route=routing.route_used,
    subagent=subagent,
)
if policy_result.valid:
    self.audit.model_selection(task_id, routing.to_dict())
    # Proceed with task creation
else:
    self.audit.policy_violation(task_id, policy_result.to_dict())
    return {"error": "Policy violation"}
```

### 2. Subagent Invocation (`invoke_subagent`)

```python
# Before worker invocation, inject routing info
task["routing"] = self.model_router.get_last_routing()
```

### 3. Audit Integration (`audit.py`)

```python
def model_selection(self, task_id: str, routing: dict):
    """Record model selection in audit log."""
    self._write_entry({
        "entry_type": "model_selection",
        "task_id": task_id,
        "details": routing,
    })

def model_fallback(self, task_id: str, routing: dict):
    """Record model fallback in audit log."""
    self._write_entry({
        "entry_type": "model_fallback",
        "task_id": task_id,
        "details": routing,
    })

def policy_violation(self, task_id: str, result: dict):
    """Record policy violation in audit log."""
    self._write_entry({
        "entry_type": "policy_violation",
        "task_id": task_id,
        "details": result,
    })
```

## Testing (`examples/test_model_router.py`)

```bash
# Run self-test
python runtime/model_router.py

# Run example tests
python examples/test_model_router.py

# Run v0.2.1 policy violation tests
python examples/test_v021_routing_policy_violations.py
```

Test coverage:

| Feature | Status |
|---------|--------|
| Config loading | ✓ |
| Route resolution | ✓ |
| Subagent override | ✓ |
| Task type override | ✓ |
| Fallback logic | ✓ |
| Audit logging | ✓ |
| Downgrade constraint | ✓ |
| Minimum model class enforcement | ✓ |
| Approval gate check | ✓ |
| Sovereignty check | ✓ |

## Non-Goals (By Design)

- No provider API calls (provider name only, no auth)
- No browser/crawling
- No new subagent spawning
- No outbound network contact
- No task state advancement on failure
- No provider lock-in (routes are provider-agnostic)
- **OverCR does NOT execute models** — runtime/delegation handles execution

## Future Enhancements

1. **Per-subagent model pools** — multiple models with weighted routing
2. **Health-based fallback** — skip models based on observed failures
3. **Latency-based selection** — choose fastest available model
4. **Cost-aware routing** — choose cheapest model that meets constraints
5. **Native provider failover** — runtime-level model switching (Hermes-specific)

## Substrate Contracts

OverCR defines contracts that host runtimes may implement:

| Contract | Description | Hermes Support |
|----------|-------------|----------------|
| Model routing | Intent: choose model by route/subagent | ✓ |
| Policy enforcement | Intent: validate against governance | ✓ |
| Audit trail | Event logging for routing decisions | ✓ |
| Fallback intent | Request fallback model on timeout | ✓ |
| State safety | Never advance task on routing failure | ✓ |

Hermes is the reference implementation of these contracts.
Other runtimes may implement contracts differently or not at all.

## Revision History

- **v0.2.1** — Init: config-driven routing, fallback support, audit logging, policy enforcement
- **v0.2.2** (future) — Health-aware routing, multi-model pools, native provider failover

## Summary

OverCR v0.2.1 model routing:

1. ✅ **Config-driven** routing decisions (no hardcoded models)
2. ✅ **Runtime-agnostic** — substrate layer, not execution layer
3. ✅ **Hermes as reference** — runtime integration point
4. ✅ **Policy mode only** — fallback intent, not execution
5. ✅ **Audit tracking** — all routing decisions logged
6. ✅ **No provider lock-in** — routes are abstraction over providers
