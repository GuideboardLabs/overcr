# OverCR v0.2.1 Architecture Clarification

## Executive Summary

**OverCR is a portable orchestration substrate — NOT a model runtime.**

This document clarifies OverCR's role in the AI orchestration ecosystem and
how model routing fits into the architecture.

## Core Identity

### What OverCR Is

1. **Orchestration Substrate** — coordinates workloads, manages state, enforces governance
2. **Portable Layer** — contracts designed to survive runtime/model swaps
3. **State Manager** — filesystem-first task state with audit trail
4. **Governance Layer** — approval gates, capability constraints, sovereignty checks

### What OverCR Is NOT

1. **Model Runtime** — does not execute models directly
2. **Provider Interface** — does not manage provider connections
3. **Hermes Replacement** — does not replace or compete with Hermes
4. **Standalone Execution** — requires host runtime for model invocation

## Architecture Layers

```
┌─────────────────────────────────────────────────────────────┐
│                    OverCR Substrate                          │
│                                                               │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  Model Routing Layer (runtime/model_router.py)        │  │
│  │  • Route-based model selection                        │  │
│  │  • Provider assignment (intent only)                 │  │
│  │  • Timeout configuration                             │  │
│  │  • Fallback model selection (intent)                │  │
│  │  • Audit logging (routing decisions)                │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                               │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  Model Policy Layer (runtime/model_policy.py)         │  │
│  │  • Capability constraints                            │  │
│  │  • Minimum model class enforcement                   │  │
│  │  • Approval gate validation                          │  │
│  │  • Sovereignty constraint checking                   │  │
│  │  • Downgrade constraint enforcement                  │  │
│  │  • Audit logging (validation decisions)              │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                               │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  Runtime Layer (runtime/overcr_runtime.py)            │  │
│  │  • Task lifecycle management                         │  │
│  │  • Subagent adapter (bridging to host runtime)      │  │
│  │  • Worker invocation                                 │  │
│  │  • State advancement (filesystem-first)              │  │
│  │  • Policy validation (before state advancement)      │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                               │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  Audit Layer (runtime/audit_writer.py)                │  │
│  │  • Application-only audit trail                      │  │
│  │  • State transitions                                 │  │
│  │  • Routing decisions                                 │  │
│  │  • Validation results                                │  │
│  │  • Governance policy decisions                       │  │
│  └───────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
            │
            ▼
┌─────────────────────────────────────────────────────────────┐
│                    Host Runtime (Hermes)                     │
│                                                               │
│  SubagentAdapter (runtime/subagent_adapter.py)              │
│  • Bridges OverCRRuntime to host runtime                    │
│  • Worker process invocation                                │
│  • Timeout enforcement                                       │
│  • Response capture                                         │
│        │
│        ▼
│  Provider Layer (configured in Hermes/ollama configs)
│  • Model invocation (Ollama, OpenAI, etc.)
│  • Timeout handling
│  • Failover to fallback model (if supported)
│  • Response formatting
└──────────────────────────────────────────────────────────────┘
```

## Model Routing: Intent Layer

OverCR's model routing is an **intent layer**, not an execution layer:

### What It Does (Intent)

1. **Selects models** based on route/subagent configuration
2. **Assigns providers** (provider name only, no auth)
3. **Configures timeouts** per route/subagent
4. **Suggests fallback models** on timeout/empty response
5. **Logs routing decisions** to audit trail

### What It Does NOT Do (Execution)

1. **Invoke models** — host runtime handles this
2. **Manage provider connections** — host runtime handles this
3. **Enforce timeouts** — host runtime's timeout mechanisms
4. **Perform failover** — host runtime implements failover logic
5. **Handle errors** — host runtime reports errors to OverCRRuntime

### Example Flow

```yaml
# Config (OverCR substrate)
_routes:
  research:
    preferred_model: "glm-5.1:cloud"
    fallback_model: "qwen3-coder-next"
    provider: "ollama-cloud"
    timeout: 120
```

```
1. OverCR routing layer decides: "glm-5.1:cloud" for research task
2. Policy layer validates: ✓ capability constraints satisfied
3. OverCRRuntime passes routing intent to host runtime
4. Host runtime (Hermes) invokes provider: "glm-5.1:cloud"
5. On timeout, Hermes attempts fallback: "qwen3-coder-next"
6. OverCR audit logs both decisions (intent layer)

Note: Step 5 (failover) is implemented in Hermes, not OverCR
```

## Host Runtime (Hermes)

### Hermes as Reference Implementation

1. **Primary Runtime**: OverCR's test path and integration point
2. **Provider Integration**: Manages Ollama, OpenAI, and other providers
3. **Execution Layer**: Handles actual model invocation
4. **Failover Implementation**: Implements fallback logic

### Hermes Responsibilities

1. Model invocation via configured provider
2. Timeout enforcement
3. Failover to fallback model (if timeout occurs)
4. Response capture and formatting
5. Error reporting to OverCRRuntime

### OverCR Responsibilities

1. Routing decisions (which model, which provider)
2. Governance constraints (what models are allowed)
3. State management (task lifecycle)
4. Audit logging (all decisions)
5. Worker orchestration (subagent processes)

## Integration Pattern

### Runtime-to-Host Workflow

```python
# OverCR runtime layer
routing = model_router.route(task_id, domain, subagent)
policy = model_policy.validate_routing(
    model=routing.model,
    route=routing.route_used,
    subagent=subagent,
)

if policy.valid:
    # Pass routing intent to host runtime
    return host_runtime.execute(
        task_id=task_id,
        model=routing.model,
        provider=routing.provider,
        timeout=routing.timeout,
    )
else:
    # Reject and log policy violation
    return {"success": False, "error": "Policy violation"}
```

### Host Runtime (Hermes) Implementation

```python
# Hermes provider layer
def execute(task_id, model, provider, timeout):
    try:
        response = ollama_client.invoke(
            model=model,
            prompt=task_context,
            timeout=timeout
        )
        return {"success": True, "response": response}
    except TimeoutError:
        # Failover to fallback model (Hermes-specific)
        fallback = get_fallback_model(model)
        response = ollama_client.invoke(
            model=fallback,
            prompt=task_context,
            timeout=timeout
        )
        return {"success": True, "response": response, "fallback_used": True}
```

## Provider Failover: Policy Mode vs Runtime Implementation

### Policy Mode (OverCR)

OverCR's policy layer **suggests** fallback models but does NOT execute them:

```yaml
# Policy defines intent
preferred_model: "glm-5.1:cloud"
fallback_model: "qwen3-coder-next"
```

### Runtime Implementation (Hermes)

Actual failover happens in the host runtime:

1. OverCR routing decides: "glm-5.1:cloud"
2. Hermes invokes provider, model times out
3. Hermes attempts fallback to "qwen3-coder-next" (runtime logic)
4. OverCR audit logs both decisions

**Key Point**: OverCR does NOT implement failover — it records intent and
the host runtime (Hermes) implements actual failover logic.

## Runtime-Agnostic Substrate

OverCR's design intentionally avoids provider lock-in:

### Runtime Swapping

OverCR should work with any runtime that implements the contracts:

```python
# Runtime A (Hermes)
overcr_runtime = OverCRRuntime(...)
overcr_runtime.host_runtime = HermesRuntime()

# Runtime B (OpenWebUI integration)
overcr_runtime = OverCRRuntime(...)
overcr_runtime.host_runtime = OpenWebUIRuntime()

# Runtime C (Custom harness)
overcr_runtime = OverCRRuntime(...)
overcr_runtime.host_runtime = CustomRuntime()
```

### Provider Swapping

OverCR routing decisions survive provider changes:

```yaml
# Switch from Ollama Cloud to local Ollama
_routes:
  research:
    # Same routing intent
    preferred_model: "glm-5.1:cloud"
    # Different provider (host runtime handles config)
    provider: "ollama-local"
```

## Substrate Contracts

OverCR defines contracts that runtimes may implement:

| Contract | Description | Required in Host Runtime |
|----------|-------------|--------------------------|
| Routing intent | Which model/provider to use | ✓ (Hermes implements) |
| Policy validation | Is routing allowed? | ✓ (OverCR enforces) |
| Task state | Filesystem-first state | ✓ (filesystem layer) |
| Audit trail | Decision logging | ✓ (OverCR writes) |
| Worker invocation | Subagent subprocess | ✓ (Hermes handles) |

## Summary

### OverCR Role

**OverCR is the orchestration substrate** — it:

1. Defines routing/policy contracts
2. Enforces governance constraints
3. Manages task state
4. Logs all decisions
5. Bridges to host runtime

### Host Runtime Role (Hermes)

**Hermes is the execution layer** — it:

1. Implements routing intent
2. Invokes models via providers
3. Handles timeouts
4. Implements failover
5. Reports errors

### Key Distinction

- OverCR: **Intent layer** (config-driven decisions)
- Hermes: **Execution layer** (model invocation, failover)

The model routing extension enables **config-driven model assignment**
within the OverCR substrate, not as a replacement for model execution.
