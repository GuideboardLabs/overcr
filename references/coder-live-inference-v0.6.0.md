# CodER Live Inference Mode — v0.6.0 Reference

**Status**: Executable (v0.6.0)  
**Inference Provider**: Hermes CLI (`hermes -z --ignore-rules`)  
**Sanitizer**: `runtime/output_sanitizer.py` (v0.4.3)  
**Packet Type**: `coder_patch_plan`  

---

## Overview

CodER v0.6.0 introduces controlled live inference mode for code analysis and patch planning. Before v0.6.0, CodER was a deterministic worker producing template-based code review packets. In v0.6.0, CodER can optionally call a live Hermes model for richer code analysis, bug diagnosis, and advisory patch plan generation — while preserving all OverCR governance, validation, and auditability guarantees.

### Scope

CodER inference is **advisory-only**:
- Produces code inspection summaries, bug diagnoses, patch plans, proposed diffs, test plans, and rollback plans
- **No file mutation** — proposed diffs are advisory artifacts only
- **No shell execution** — no commands run automatically
- **No package installation** — no dependency changes
- **No git push** — no repository changes
- No autonomous code application
- All mutation requires OverCR approval gate

### Governance

- Model output is **untrusted** until sanitized and validated by the 6-level validator
- All packets route to `target: "overcr"` only — never directly to PypER, CodER, KnowER, or CryER
- No governance override claims permitted (L5 enforcement)
- `approval_required` must be `true` for `coder_patch_plan` (L4 hard error)
- Deterministic fallback always available
- Inference failure must not advance state

---

## Architecture

```
Request Packet (stdin)
       ↓
CodER Inference Worker (inference_worker.py)
       ↓
┌──────────────────────────────────────┐
│  Inference available?                │
│    YES → Hermes CLI (oneshot mode)    │
│           ↓                          │
│         Raw Model Output              │
│           ↓                          │
│         Output Sanitizer (v0.4.3)    │
│           ↓                          │
│         Sanitized JSON Packet        │
│    NO  → Deterministic Worker        │
└──────────────────────────────────────┘
       ↓
6-Level Validator (L1-L6)
       ↓
Valid Packet → OverCR routing (→ operator for review)
```

### Routing

`coder_patch_plan` routes to `operator` (not another subagent) because advisory plans containing proposed file modifications require human review before any action.

### Key Components

| Component | File | Role |
|-----------|------|------|
| `inference_worker.py` | `subagents/coder/inference_worker.py` | Live inference + deterministic fallback |
| `inference_prompt.md` | `subagents/coder/inference_prompt.md` | Template for live model inference |
| `worker.py` | `subagents/coder/worker.py` | Deterministic fallback worker |
| `output_sanitizer.py` | `runtime/output_sanitizer.py` | Deterministic JSON extraction (v0.4.3) |
| `inference_adapter.py` | `runtime/inference_adapter.py` | Factory for mock/hermes_cli adapters |
| `validate_packet.py` | `tools/validate_packet.py` | 6-level validator with L6 `_validate_coder_patch_plan` |

---

## Prompt Template

The model receives a **structured prompt** that:

1. Establishes CodER identity and OverCR sovereignty context
2. Describes the `coder_patch_plan` packet schema and required fields
3. Enforces hard constraints:
   - `target` must be `"overcr"`
   - `approval_required` must be `true`
   - No shell execution, no file mutation, no git push
   - No governance override, no direct subagent routing
4. Returns only valid JSON with exact field requirements
5. Proposed diffs are advisory artifacts — never applied automatically

**Key constraints in prompt**:
- `approval_required` must be `true` (L4 enforced)
- `target` must be `"overcr"` (L1 enforced)
- `proposed_diff` is advisory text only
- `files_to_modify` lists _intended_ targets, not already-modified files
- `risk_notes` must include `level` (low/medium/high), `factors` (≥1), `mitigations` (≥1)
- `bug_diagnosis.confidence` must be float 0.0–1.0
- `estimated_complexity` must be one of: low, medium, high

---

## Packet Schema (v0.6.0)

### `coder_patch_plan`

```json
{
  "packet_type": "coder_patch_plan",
  "version": "1.0",
  "timestamp": "2025-05-11T03:00:00+00:00",
  "source": "coder",
  "target": "overcr",
  "task_id": "task-0600",
  "summary": "CodER patch plan: diagnose and fix off-by-one in array indexing",
  "patch_plan_data": {
    "code_inspection_summary": "Array indexing uses i <= len instead of i < len",
    "bug_diagnosis": {
      "summary": "Off-by-one error in loop termination",
      "root_cause": "Loop condition uses <= instead of <",
      "confidence": 0.85
    },
    "patch_plan": {
      "description": "Change loop condition from <= to <",
      "files_to_modify": ["src/utils/array.py"],
      "approach": "Single-line fix in loop condition",
      "estimated_complexity": "low"
    },
    "proposed_diff": "--- a/src/utils/array.py\n+++ b/src/utils/array.py\n@@ -10,3 +10,3 @@\n-    for i in range(0, len(arr) <= 1):\n+    for i in range(0, len(arr) < 1):\n",
    "test_plan": {
      "strategy": "Verify fix prevents IndexError at boundary",
      "test_cases": ["Test array access with maximum valid index"],
      "verification_steps": ["Run existing test suite"]
    },
    "rollback_plan": "Revert single-line change via git checkout",
    "risk_notes": {
      "level": "low",
      "factors": ["Single-line change with narrow scope"],
      "mitigations": ["Existing test coverage is comprehensive for this module"]
    }
  },
  "audit_trail": {
    "worker_version": "0.6.0",
    "execution_timestamp": "2025-05-11T03:00:00+00:00",
    "files_modified": [],
    "rollback_instructions": "No filesystem changes made. Advisory plan only.",
    "inference_mode": true,
    "inference_source": "hermes_cli",
    "inference_attempt_id": "infer-patch_plan-0600-001",
    "prompt_hash": "a1b2c3d4e5f67890",
    "selected_model": "glm-5.1:cloud",
    "selected_provider": "ollama-cloud",
    "route_used": "coder/patch_plan/inference",
    "raw_model_output_summary": "...",
    "sanitized_model_output_summary": "...",
    "validation_result": "passed",
    "fallback_used": false,
    "elapsed_s": 2.34
  },
  "approval_required": true,
  "next_steps_recommendation": "Review advisory patch plan. Apply changes only after operator approval."
}
```

---

## Validation Rules (v0.6.0)

All 6 L1-L6 levels apply to `coder_patch_plan` packets, with CodER-specific checks:

### L3: Packet Type + Required Fields

- `packet_type` must be `"coder_patch_plan"` (registered in `PACKET_TYPES_BY_SOURCE["coder"]`)
- `patch_plan_data` field must be present and non-empty

### L4: Approval Gate Enforcement

- `approval_required` MUST be `true` for `coder_patch_plan`
- If `false` or absent, L4 returns a hard error (not a warning)
- This prevents any model output from bypassing the approval gate

### L5: Forbidden Patterns (Inference-Specific)

| Pattern | Message |
|---------|---------|
| `route to pyper`, `send to coder`, `target: knower`, `direct handoff to cryer` | Direct routing rejected |
| `may submit`, `no approval needed`, `permitted to bypass`, `self-approved` | Governance override rejected |
| `applied patch`, `files updated`, `changes made`, `ran command` | Premature mutation claim rejected |

### L6: CodER Patch Plan Governance

`_validate_coder_patch_plan()` enforces:

| Field | Requirement |
|-------|-------------|
| `code_inspection_summary` | Non-empty string |
| `bug_diagnosis.summary` | Non-empty string |
| `bug_diagnosis.root_cause` | Non-empty string |
| `bug_diagnosis.confidence` | Float 0.0–1.0 |
| `patch_plan.description` | Non-empty string |
| `patch_plan.files_to_modify` | List with ≥1 entry |
| `patch_plan.approach` | Non-empty string |
| `patch_plan.estimated_complexity` | One of: low, medium, high |
| `proposed_diff` | Non-empty string (advisory text) |
| `test_plan.strategy` | Non-empty string |
| `test_plan.test_cases` | List with ≥1 entry |
| `rollback_plan` | Non-empty string |
| `risk_notes.level` | One of: low, medium, high |
| `risk_notes.factors` | List with ≥1 entry |
| `risk_notes.mitigations` | List with ≥1 entry |

When `audit_trail.inference_mode == true`, L6 also validates:
- `inference_attempt_id` present and non-empty
- `prompt_hash` present and non-empty
- `selected_model` present and non-empty
- `selected_provider` present and non-empty
- `route_used` present and non-empty
- `inference_source` ∈ {"mock", "hermes_cli", "deterministic"}

---

## Inference Routing Config

```yaml
_coder:
  patch_plan:
    enabled: true
    adapter: "mock"                    # "hermes_cli" for production
    model: "glm-5.1:cloud"
    fallback_model: "qwen3-coder-next"
    provider: "ollama-cloud"
    timeout_s: 45
    max_retries: 1
    fallback_to_deterministic: true
    prompt_template: "subagents/coder/inference_prompt.md"
  _all_domains:
    enabled: false                      # catch-all safety net
```

### Governance Rules Config

```yaml
_governance:
  coder_patch_plan_approval_required: true
  coder_no_auto_apply: true
  coder_no_shell_exec: true
  coder_no_fs_mutation: true
  coder_proposed_diffs_advisory_only: true
  coder_risk_notes_levels: ["low", "medium", "high"]
  coder_complexity_levels: ["low", "medium", "high"]
```

---

## Runtime Registration

| Component | Registration |
|-----------|-------------|
| `PACKET_TYPES_BY_SOURCE["coder"]` | Added `coder_patch_plan` |
| `SUBAGENT_PACKET_TYPES["coder"]` | Added `coder_patch_plan` |
| `DOMAIN_SUBAGENT_MAP["patch_plan"]` | `"coder"` |
| `_default_packet_type["coder"]` | `"coder_patch_plan"` for domain `"patch_plan"` |
| `LIVE_WORKER_DOMAINS["patch_plan"]` | `"coder"` |
| `EXPECTED_PACKET_TYPES["coder"]` | `coder_patch_plan` in frozenset |
| OverCR routing | `coder_patch_plan → operator` with `requires_downstream=True` |

---

## Test Coverage

### Test Suite (`tests/test_coder_patch_plan.py`)

| Test | Category | What it Proves |
|------|----------|----------------|
| **1** | happy path | Mock inference → validated coder_patch_plan packet |
| **2** | L1-L6 validation | Generated patch plan validates all 6 levels |
| **3** | advisory only | Proposed diff captured but not applied (zero mutation) |
| **4** | forbidden shell | Shell command request produces advisory plan, no execution |
| **5** | governance override | Governance override claim rejected; L4 approval enforced |
| **6** | direct routing | Direct target=pyper/coder/knower/cryer rejected at L1 |
| **7** | deterministic fallback | Deterministic worker still works when inference unavailable |
| **8** | approval_required L4 | `approval_required=false` and `None` both rejected at L4 |

### Running Tests

```bash
cd $OVERCR_ROOT
python3 tests/test_coder_patch_plan.py
python3 tests/run_all.py --test coder_patch_plan
```

---

## Audit Trail

Every inference produces an audit entry recording:

| Field | Type | Purpose |
|-------|------|---------|
| `selected_model` | string | Model routing key |
| `selected_provider` | string | Provider routing key |
| `route_used` | string | Inference route (e.g., `coder/patch_plan/inference`) |
| `inference_attempt_id` | string | Unique attempt ID |
| `prompt_hash` | string | SHA-256 of prompt (first 16 chars) |
| `raw_model_output_summary` | string | First 500 chars of raw model output |
| `sanitized_model_output_summary` | string | First 500 chars of sanitized JSON |
| `validation_result` | string | L1-L6 validation outcome |
| `fallback_used` | bool | `true` if deterministic fallback invoked |
| `elapsed_s` | float | Time to completion (seconds) |

---

## Safety Guarantees

1. **No filesystem mutation**: CodER inference mode never modifies files; `files_modified` is always `[]`
2. **No shell execution**: No commands run automatically; shell references in model output are advisory text only
3. **No autonomous application**: Proposed diffs are advisory artifacts — never auto-applied
4. **Approval gate enforced**: `approval_required=true` is L4 hard error; cannot be bypassed
5. **Model output untrusted**: Always sanitized + validated through 6-level validator
6. **Direct routing blocked**: L1 + L5 reject subagent targets
7. **Governance override blocked**: L5 rejects claims of bypass authority
8. **Deterministic fallback**: `worker.py` always available as backup
9. **Inference source tracked**: `hermes_cli`, `mock`, or `deterministic` explicitly recorded
10. **State never advances on failure**: Inference failure produces no state change

---

## Success Condition

**One Hermes-backed CodER response becomes a validated advisory patch-plan packet, with zero filesystem mutation.**

- Output is NOT trusted until sanitized
- Validation produces `(valid, errors, warnings)` tuple
- `approval_required=true` enforced at L4 (hard error if missing/false)
- `files_modified` is always `[]`
- Proposed diffs exist as advisory text only
- All required fields validated at L6

---

## Status Summary

| Aspect | Status |
|--------|--------|
| Inference worker | ✅ Executable (v0.6.0) |
| Prompt template | ✅ Complete (`inference_prompt.md`) |
| Packet registration | ✅ L1-L6 registered |
| Approval gate (L4) | ✅ Hard error enforcement |
| L6 validator | ✅ `_validate_coder_patch_plan()` complete |
| Runtime routing | ✅ `coder_patch_plan → operator` |
| Config | ✅ `inference_routing.yaml` updated |
| Deterministic fallback | ✅ Worker.py remains functional |
| Test suite | ✅ 8 test cases |
| Governance docs | ✅ This document |
| Runtime demo | ✅ `examples/runtime_demo_coder_patch_plan.py` |
| Safety guarantees | ✅ 10 guarantees verified |

---

## Related Documents

- `subagents/coder/inference_worker.py` — CodER inference worker (v0.6.0)
- `subagents/coder/worker.py` — Deterministic fallback worker
- `tools/validate_packet.py` — 6-level validator (L1-L6)
- `runtime/output_sanitizer.py` — JSON extraction logic (v0.4.3)
- `runtime/inference_adapter.py` — Adapter factory (mock, hermes_cli)
- `references/cryer-live-inference-v0.5.0.md` — CryER v0.5.0 reference
- `references/knower-inference-v0.4.1.md` — KnowER inference reference