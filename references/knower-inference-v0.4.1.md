# KnowER Inference Mode — v0.4.1 Reference

> OverCR v0.4.1 adds controlled inference-backed worker mode to KnowER,
> the research and analysis subagent. This document covers the architecture,
> governance guarantees, and operational semantics.

## Overview

**What changed**: KnowER workers can now optionally use model-assisted reasoning
(inference) for the `claim_review` and `myth_fact` domains. Previously, all
KnowER workers were deterministic templates. The inference mode wraps model
output into the same typed packet envelope and subjects it to the same 6-level
validator — no new trust boundary, no new bypass path.

**What didn't change**: CryER, PypER, and CodER are untouched. The
deterministic KnowER worker remains the default fallback. No real model calls
occur in v0.4.1 — all inference is simulated via `MockInferenceAdapter`.

## Architecture

```
                                    ┌─────────────────┐
                                    │  Request (JSON) │
                                    │     on stdin     │
                                    └────────┬────────┘
                                             │
                                    ┌────────▼────────┐
                                    │ inference_       │
                                    │ worker.py        │
                                    └────────┬────────┘
                                             │
                              ┌───────────────┼────────────────┐
                              │               │                │
                   domain in                  domain not        │
                   {claim_review,             in inference     │
                    myth_fact}?               domains?          │
                              │               │                │
                     ┌────────▼────────┐  ┌──▼──────────┐     │
                     │ InferenceAdapter│  │ worker.py    │     │
                     │ (Mock/Hermes)   │  │ deterministic│     │
                     └────────┬────────┘  └──┬──────────┘     │
                              │               │                │
                     ┌────────▼────────┐  ┌──▼──────────┐     │
                     │ 6-level validator│  │ 6-level     │     │
                     │ (L1-L6 + inference │ │ validator   │     │
                     │  governance)      │ │ (L1-L6)     │     │
                     └────────┬────────┘  └──┬──────────┘     │
                              │               │                │
                     ┌────────▼────────────────▼────────────┐ │
                     │         Validated packet (stdout)      │ │
                     └────────────────────────────────────────┘ │
                                                              │
                     ┌─────────────────────────────────────────┘
                     │
              If inference fails AND fallback
              fails → exit nonzero (task does NOT
              advance state)
```

### Fallback Chain

1. **Inference path**: domain is `claim_review` or `myth_fact` → load config → invoke adapter → validate → emit
2. **If inference fails or validation rejects**: fall back to deterministic `worker.py`
3. **If deterministic also fails**: exit 1 — task stays in safe state

## New Files

| File | Purpose |
|------|---------|
| `config/inference_routing.yaml` | Inference mode config: domains, adapters, timeout, audit, governance |
| `runtime/inference_result.py` | `InferenceResult`, `InferenceMetadata`, `InferenceStatus` dataclasses |
| `runtime/inference_adapter.py` | `BaseInferenceAdapter` ABC, `MockInferenceAdapter`, `HermesInferenceAdapter`, `get_adapter()` factory |
| `subagents/knower/inference_prompt.md` | System prompt template for inference-mode KnowER |
| `subagents/knower/inference_worker.py` | Inference-mode KnowER worker (wraps deterministic fallback) |
| `examples/runtime_demo_knower_inference_claim_review.py` | End-to-end demo of inference mode |
| `tests/test_knower_inference_mode.py` | 16-assertion test suite for inference mode |

## Modified Files

| File | Change |
|------|--------|
| `tools/validate_packet.py` | Added L5 direct-routing & browsing-claim patterns; L6 inference governance validator |
| 6 example/test files | Replaced "Route to PypER" → "Submit to OverCR for routing" (governance compliance) |
| `tests/test_manifest.json` | Added `knower_inference_mode` test entry |

## Governance Guarantees

### L5 — New pattern detectors

| Pattern | Regex | What it catches |
|---------|-------|-----------------|
| Direct routing | `route to (?:pyp?er\|coder\|knower\|cryer)`, `route directly to`, `skip overcr`, `skip.*oversight` | Model claiming it can route directly to another subagent |
| Browsing claims | `live browsing`, `web browsing`, `crawled`, `scraped.*live`, `browsed the web` | Model claiming it performed live web crawling |

### L6 — Inference governance validator

`_validate_inference_governance()` checks inference-mode packets (`audit_trail.inference_mode == True`):

1. **Required inference audit fields**: `inference_source`, `inference_attempt_id`, `inference_model` must be non-empty
2. **No classification bypass**: Classification values must be from allowed enums
3. **No direct routing claims** (delegates to L5)
4. **No browsing claims** (delegates to L5)

### Invariant: model output cannot change doctrine

The validator enforces at L5 and L6:
- Model output cannot bypass approval gates
- Model output cannot route directly to another subagent
- Model output cannot claim live browsing occurred
- Model output is UNTRUSTED until validated through 6-level validator
- On inference failure, task MUST NOT advance state

## Inference Adapter Interface

```python
class BaseInferenceAdapter(ABC):
    @property
    @abstractmethod
    def adapter_type(self) -> str: ...

    @abstractmethod
    def invoke(self, prompt: str, config: dict) -> InferenceResult: ...

    @abstractmethod
    def is_available(self) -> bool: ...
```

### MockInferenceAdapter

- Simulates model responses — no real network calls, no API keys needed
- Produces structurally correct `claim_review` and `myth_fact` packets
- `is_available()` always returns `True`
- Used in all v0.4.1 tests and the runtime demo

### HermesInferenceAdapter

- Shells out to the Hermes runtime for live model calls
- Requires `OLLAMA_API_KEY` and a running Hermes gateway
- NOT exercised in v0.4.1 tests (future activation)

## Config Structure

```yaml
# config/inference_routing.yaml
_inference_defaults:
  enabled: true
  adapter: mock
  timeout_s: 30
  max_retries: 1
  fallback_to_deterministic: true
  record_audit: true

_knower:
  claim_review:
    enabled: true
    adapter: mock
    model: glm-5.1:cloud
    provider: ollama-cloud
    timeout_s: 45
  myth_fact:
    enabled: true
    adapter: mock
    model: glm-5.1:cloud
    provider: ollama-cloud
    timeout_s: 45

_governance:
  model_output_cannot:
    - change_doctrine
    - bypass_approval_gates
    - route_directly
    - claim_browsing
  classifications:
    claim_review: [fact, inference, assumption, rumor]
    myth_fact: [myth, fact, partial_truth, unverified]
  fallback: deterministic
  on_failure: task_must_not_advance
```

## Test Coverage

| Test | Category | Assertions |
|------|----------|------------|
| Inference claim review happy path | Worker | 16 |
| Inference myth/fact happy path | Worker | 11 |
| Governance: direct routing | Governance | 2 |
| Governance: browsing claims | Governance | 2 |
| Governance: override claims | Governance | 2 |
| L6 inference governance (missing metadata) | Validation | 2 |
| Deterministic fallback (no regression) | Worker | 5 |
| Inference adapter basics | Runtime | 8 |
| Adapter factory | Runtime | 3 |
| Config loading | Config | 4 |
| Prompt rendering | Runtime | 4 |
| Inference result types | Data | 13 |
| Mock adapter domain coverage | Runtime | 6 |
| Direct inference worker invocation | Subprocess | 4 |
| Non-inference domain fallback | Edge case | 2 |
| Combined governance violations | Governance | 4 |

**Total: 16 test phases, all pass (0.20s)**

Full suite: **17/17 tests pass (3.21s)**

## Executable vs Simulated

| Component | Executable | Simulated | Notes |
|-----------|-----------|-----------|-------|
| MockInferenceAdapter | ✓ | — | Produces structural packets, no model calls |
| HermesInferenceAdapter | — | ✓ (defined, not exercised) | Requires live Hermes gateway |
| Deterministic fallback | ✓ | — | Full template-based worker (v0.4.0) |
| 6-level validation | ✓ | — | Real validation, real governance enforcement |
| L5 direct routing detector | ✓ | — | Catches "Route directly to PypER" etc. |
| L5 browsing claim detector | ✓ | — | Catches "I browsed the web" etc. |
| L6 inference governance | ✓ | — | Requires audit metadata on inference packets |
| Inference prompt template | ✓ | — | Rendered with `{{variable}}` substitution |
| Config loading (YAML) | ✓ | — | Reads `config/inference_routing.yaml` |

**No real model calls occurred.** All inference is simulated via `MockInferenceAdapter`.
The `HermesInferenceAdapter` class exists but is not tested with live models in v0.4.1.

## Safety Guarantees

1. **Model output is untrusted until validated**: All inference packets go through
   the same 6-level validator as deterministic packets, plus additional L6 inference
   governance checks.

2. **No autonomous loops**: Inference is single-shot per task. No retry loops,
   no chaining, no recursive inference calls.

3. **Deterministic fallback always available**: If inference fails (timeout, error,
   malformed output, validation failure), the deterministic worker produces a
   packet that is structurally identical to v0.4.0 output.

4. **Task state safety**: If both inference and deterministic fail, the task does
   NOT advance state. The worker exits nonzero, and the runtime keeps the task
   in `in_progress`.

5. **No outbound contact**: Model output cannot claim live browsing, crawling,
   or outbound network activity. The L5 validator catches these patterns.

6. **No direct subagent routing**: Model output cannot route directly to another
   subagent. Phrases like "Route directly to PypER" or "Skip OverCR oversight"
   are caught by L5.

7. **No doctrine changes**: Model output cannot claim authority to bypass approval
   gates, override governance, or change operational doctrine.

8. **Audit trail integrity**: Every inference attempt records model, provider,
   attempt ID, elapsed time, fallback status, and validation result in the
   packet's `audit_trail`.

9. **Classification constraints**: Model output that uses invalid classification
   values is coerced to safe defaults ("unknown" for claims, "unverified" for
   myth/fact items).

10. **Hermes-first runtime boundary**: The `HermesInferenceAdapter` is the only
    path to live model inference, and it runs through the Hermes runtime — not
    directly from the worker. Workers never hold API keys or make HTTP calls.

## Freeze Status

**v0.4.1 is ready to freeze.**

- 17/17 tests pass
- All governance patterns enforced (L5 direct routing, browsing claims, override; L6 inference metadata)
- Deterministic fallback verified (no regression from v0.4.0)
- No real model calls — MockInferenceAdapter only
- Documentation complete (this reference + test suite)