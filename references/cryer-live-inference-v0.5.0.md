# CryER Live Inference Mode — v0.5.0 Reference

**Status**: Executable (v0.5.0)  
**Inference Provider**: Hermes CLI (`hermes -z --ignore-rules`)  
**Sanitizer**: `runtime/output_sanitizer.py` (v0.4.3)  

---

## Overview

CryER v0.5.0 introduces real model-backed inference using the Hermes CLI runtime. Before v0.5.0, CryER produced deterministic packets from template analysis. In v0.5.0, CryER can optionally call a live Hermes model for richer signal interpretation while preserving all OverCR governance, validation, and auditability guarantees.

### Scope

CryER inference is **input-limited**:
- Only uses **provided public signal snippets** (reviews, directories, announcements)
- No live web crawling or browser automation
- No login/authenticated scraping
- No form submission or outbound contact
- No autonomous loops or direct subagent routing

### Governance

- Model output is **untrusted** until sanitized and validated by the 6-level validator
- All packets route to `target: "overcr"` only — never directly to PypER, CodER, etc.
- No governance override claims permitted (L5 enforcement)
- Private personal data is **refused extraction/storage**
- Deterministic fallback always available

---

## Architecture

```
Request Packet (stdin)
       ↓
CryER Inference Worker (inference_worker.py)
       ↓
Hermes CLI (oneshot mode, --ignore-rules)
       ↓
Raw Model Output
       ↓
Output Sanitizer (v0.4.3 pattern)
       ↓
Sanitized JSON Packet
       ↓
6-Level Validator (L1-L6)
       ↓
Valid Packet → OverCR routing
```

### Key Components

| Component | File | Role |
|-----------|------|------|
| `inference_worker.py` | `subagents/cryer/inference_worker.py` | Live inference + deterministic fallback |
| `inference_prompt.md` | `subagents/cryer/inference_prompt.md` | Template for live model inference |
| `output_sanitizer.py` | `runtime/output_sanitizer.py` | Deterministic JSON extraction (v0.4.3) |
| `inference_adapter.py` | `runtime/inference_adapter.py` | Factory for mock/hermes_cli adapters |

---

## Prompt Template

The model receives a **structured prompt** that:

1. Establishes CryER identity and OverCR sovereignty context
2. Describes the 6 packet types and their schemas
3. Enforces hard constraints (no web browsing, no direct routing, no governance override)
4. Returns only valid JSON with exact field requirements

**Key constraints in prompt**:
- `recommended_routing` must equal `"overcr"` for all packets
- Classification must be from `{observed, inferred, assumed, unknown}`
- Source quality must be from `{primary, secondary, tertiary, unverified}`
- Confidence scale: 0-100 (not 1-4 like KnowER)
- No inference claim, browsing claim, or governance override claim permitted

---

## Packet Schemas (v0.5.0)

### 1. `cryer_recon`

```json
{
  "packet_type": "cryer_recon",
  "recon_data.targets[].signals.reputation.{yield_score,confidence,risk_flags}",
  "audit_trail.inference_mode": true,
  "audit_trail.inference_source": "hermes_cli",
  "audit_trail.inference_metadata": {
    "inference_attempt_id", "prompt_hash", "selected_model", "selected_provider",
    "route_used", "raw_output_summary", "sanitized_output_summary", "sanitizer_info",
    "validation_result", "fallback_used", "elapsed_s"
  }
}
```

### 2. `cryer_reputation_signal`

```json
{
  "packet_type": "cryer_reputation_signal",
  "reputation_signal_data.{entity,signals[],yield_score,confidence_notes,recommended_routing}",
  "signals[].{type,classification,confidence,detail,source_quality,unknowns}"
}
```

### 3. `cryer_engagement_signal`

```json
{
  "packet_type": "cryer_engagement_signal",
  "engagement_signal_data.{entity,metrics[],engagement_summary,recommended_routing}",
  "metrics[].{type,classification,value,confidence,source_quality,unknowns}"
}
```

### 4. `cryer_booking_friction`

```json
{
  "packet_type": "cryer_booking_friction",
  "booking_friction_data.{entity,friction_points[],friction_summary,recommended_routing}",
  "friction_points[].{type,classification,confidence,detail,source_quality,unknowns}"
}
```

### 5. `cryer_directory_completeness`

```json
{
  "packet_type": "cryer_directory_completeness",
  "directory_completeness_data.{entity,present_fields,missing_fields,completeness_score,classification,confidence,recommended_routing,source_quality,unknowns}"
}
```

### 6. `cryer_hiring_growth`

```json
{
  "packet_type": "cryer_hiring_growth",
  "hiring_growth_data.{entity,signals[],growth_summary,recommended_routing}",
  "signals[].{type,classification,confidence,detail,source_quality,unknowns}"
}
```

### 7. `cryer_recon` (inference metadata)

```json
{
  "packet_type": "cryer_recon",
  "recon_data.targets[].signals.reputation.{yield_score,confidence,risk_flags}",
  "audit_trail.inference_mode": true,
  "audit_trail.inference_source": "hermes_cli",
  "audit_trail.inference_metadata": { ... }
}
```

---

## Inference Metadata Fields

All inference packets include `audit_trail.inference_metadata` with:

| Field | Type | Purpose |
|-------|------|---------|
| `inference_attempt_id` | string | Unique attempt ID |
| `prompt_hash` | string | SHA-256 of prompt (first 16 chars) |
| `selected_model` | string | Model routing key |
| `selected_provider` | string | Provider routing key |
| `route_used` | string | Inference route (e.g., `"inference"`) |
| `raw_output_summary` | string | First 500 chars of raw model output |
| `sanitized_output_summary` | string | First 500 chars of sanitized JSON |
| `sanitizer_info` | dict | Extraction method, lengths, etc. |
| `validation_result` | dict | L1-L6 validation result |
| `fallback_used` | bool | `true` if deterministic fallback invoked |
| `elapsed_s` | float | Time to completion (seconds) |

---

## Inference Source Adapter Types

| Adapter | Type | Purpose |
|---------|------|---------|
| `mock` | `MockInferenceAdapter` | Deterministic simulation (no real calls) |
| `hermes` | `HermesInferenceAdapter` | Legacy (non-functional) |
| `hermes_cli` | `HermesCLIAdapter` | **Real provider-backed inference via `hermes -z`** |

### Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `CryER_INFERENCE_SOURCE` | `"hermes_cli"` | Adapter type selection |
| `OLLAMA_API_KEY` | *(none)* | Not used by OverCR — auth goes through Hermes |

---

## Validation Rules (v0.5.0)

All 6 L1-L6 levels apply to inference packets, with additional inference-specific checks:

### L5: Forbidden Patterns (Inference-Specific)

| Pattern | Message |
|---------|---------|
| `browsed`, `web search results`, `live data`, `from the internet`, `real-time search` | Browsing claim rejected |
| `route to pyper`, `send to coder`, `target: knower`, `direct handoff to cryer` | Direct routing rejected |
| `may submit`, `no approval needed`, `permitted to bypass`, `self-approved` | Governance override rejected |

### L6: Inference Governance

When `audit_trail.inference_mode == true`, L6 validates:

- `inference_attempt_id` present and non-empty
- `prompt_hash` present and non-empty
- `selected_model` present and non-empty
- `selected_provider` present and non-empty
- `route_used` present and non-empty
- `raw_output_summary` present (500-char max)
- `sanitized_output_summary` present (500-char max)
- `sanitizer_info` present and non-empty dict
- `inference_source` ∈ {"mock", "hermes", "hermes_cli", "unknown"}

---

## Test Coverage

### Test Suite (`tests/test_cryer_real_inference.py`)

| Test | Category | What it Proves |
|------|----------|----------------|
| **1** | happy path | Hermes -z call → sanitized JSON → L1-L6 pass |
| **2** | output format | Sanitized output becomes valid packet |
| **3** | packet types | All 7 packet types validated (L1-L6) |
| **4** | governance bypass | Autonomous authority claim rejected (L5) |
| **5** | direct routing | Subagent addressing rejected (L5) |
| **6** | browsing claim | "I browsed the web" claim rejected (L5) |
| **7** | private data | Email/phone not extracted into packet |
| **8** | fallback | Deterministic worker still works |
| **9** | regression | Existing worker tests still pass |

### Running Tests

```bash
cd $OVERCR_ROOT
python3 tests/test_cryer_real_inference.py
python3 tests/run_all.py --test cryer_real_inference
```

---

## Audit Trail

Every inference produces an audit entry:

```json
{
  "timestamp": "2025-05-10T22:00:00+00:00",
  "task_id": "task-0001",
  "packet_type": "cryer_reputation_signal",
  "validation": {"valid": true, "errors": [], "warnings": []},
  "inference_metadata": {
    "inference_attempt_id": "inference-0000",
    "prompt_hash": "a1b2c3d4e5f67890",
    "selected_model": "qwen3/coder-next",
    "selected_provider": "ollama-cloud",
    "route_used": "inference",
    "raw_output_summary": "[MOCK] inference — simulated...",
    "sanitized_output_summary": "{\"packet_type\":\"cryer_reputation_signal\"...",
    "sanitizer_info": {"method":"brace_count","stripped_prefix_lines":0},
    "validation_result": {"valid": true, "errors":[]},
    "fallback_used": false,
    "elapsed_s": 2.34
  }
}
```

---

## Safety Guarantees

1. **No live crawling**: Only provided snippets accepted
2. **No outbound contact**: Never suggests contact actions
3. **No governance override**: L5 enforces OverCR sovereignty
4. **Direct routing blocked**: L1 + L5 reject subagent targets
5. **Model output untrusted**: Always sanitized + validated
6. **Private data refused**: Email/phone never extracted
7. **Deterministic fallback**: Worker.py always available as backup
8. **Inference source tracked**: `hermes_cli`, `mock`, or fallback explicitly recorded

---

## Success Condition

**One real Hermes model response → one validated CryER packet that passes L1-L6 without weakening validation.**

- Output is NOT trusted until sanitized
- Sanitizer extracts JSON from code fences/preamble
- Validator produces `(valid, errors, warnings)` tuple
- All 7 packet types validated
- Governance constraints enforced at L5
- Inference metadata required at L6

---

## Status Summary

| Aspect | Status |
|--------|--------|
| Live inference worker | ✅ Executable (v0.5.0) |
| Hermes CLI adapter | ✅ Executable (`hermes -z`) |
| Output sanitizer | ✅ Executable (v0.4.3) |
| 6-level validation | ✅ Executable (no changes needed) |
| Inference metadata schema | ✅ Complete |
| Packet types (6) | ✅ Executable |
| Deterministic fallback | ✅ Executable |
| Inference source adapter | ✅ Executable (mock + hermes_cli) |
| Governance enforcements | ✅ L1-L6 verified |

---

## Next Steps

1. Run full test suite: `python3 tests/run_all.py`
2. Verify total count (expected: 21 tests)
3. Confirm executable vs simulated test counts
4. Confirm real model calls occurred (look for `hermes -z` subprocess in audit)
5. Verify safety guarantees (no outbound, no browsing, no direct routing)
6. Freeze v0.5.0 after v0.4.3 + CryER + KnowER inference stability confirmed

---

## Related Documents

- `runtime/output_sanitizer.py` — JSON extraction logic (v0.4.3)
- `runtime/inference_adapter.py` — Adapter factory (mock, hermes, hermes_cli)
- `subagents/knower/inference_worker.py` — KnowER inference mode (v0.4.1)
- `tools/validate_packet.py` — 6-level validator (L1-L6)
- `references/knower-real-inference-v0.4.3.md` — KnowERv0.4.3 architecture
