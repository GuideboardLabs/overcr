# OverCR v0.2.1 Model Routing Extension

## Overview

The model routing extension adds a **config-driven** routing layer to OverCR that:

1. Assigns different models/providers by **route**, **subagent**, and **task type**
2. Supports **automatic fallback** on timeout or empty response
3. Records all routing decisions in the **audit log**
4. **Never advances task state** on routing failure
5. Remains **runtime-agnostic** — not a provider lock-in

## Architecture

OverCR remains a **portable orchestration substrate** — it defines contracts, state, governance, and coordination, but does NOT execute models itself.

- **Hermes** is the primary reference runtime and operator interface
- **Open WebUI** is optional as a secondary visual layer
- Other runtimes may adopt OverCR substrate contracts at their discretion
- Hermes is the **supported test path** and runtime integration

```
OverCR Substrate (routing policy) → Host Runtime (Hermes) → Provider (Ollama Cloud, etc.)
         ↓                                   ↓
    Intent Layer                         Execution Layer
    • Route-based selection               • Actual model invocation
    • Capability constraints              • Timeout enforcement
    • Minimum class enforcement           • Failover to fallback
```

## Configuration

See `config/model_routing.yaml` for route definitions.

## Files

- `config/model_routing.yaml` — routing configuration
- `config/model_policy.yaml` — governance constraints
- `runtime/model_router.py` — config-driven model selection
- `runtime/model_policy.py` — governance validation layer
- `runtime/subagent_adapter.py` — bridging to host runtime (Hermes)
- `references/model-routing-v0.2.1.md` — full documentation
- `references/model-policy-v0.2.1.md` — policy layer documentation
- `examples/test_model_router.py` — basic routing tests
- `examples/test_v021_routing_policy_violations.py` — policy violation tests

## Usage

```python
from runtime.model_router import ModelRouter
from runtime.model_policy import ModelPolicy

router = ModelRouter()
policy = ModelPolicy()

# Determine intended model via routing policy
routing = router.route(task_id, domain, subagent)

# Validate against governance policy
policy_result = policy.validate_routing(
    model=routing.model,
    route=routing.route_used,
    subagent=subagent,
)

# Execute via host runtime (Hermes delegates to provider)
if policy_result.valid:
    response = hermes_executor.invoke(
        model=routing.model,
        provider=routing.provider,
        prompt=prompt
    )
```

## Key Points

1. **OverCR ≠ Runtime**: OverCR is orchestration substrate, not model execution
2. **Hermes = Reference**: Hermes is the primary runtime and integration point
3. **Policy Intent**: Routing decisions are intents, not direct execution commands
4. **Runtime Delegation**: Host runtime (Hermes) handles actual model invocation
5. **Failover**: Provider failover is policy-mode unless host runtime supports switching
