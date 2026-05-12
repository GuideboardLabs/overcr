# PypER Live Execution — v0.7.0 Reference

## Overview

PypER (Python Execution & Runtime) v0.7.0 introduces **controlled live execution planning mode** using the established Hermes-backed inference pipeline. This upgrade promotes PypER from simulated-only to model-assisted execution planning — without granting any autonomous execution authority.

## Critical Principle

> PypER may PREPARE and DESCRIBE execution.  
> PypER may NOT autonomously mutate the system.

This principle is enforced at multiple validation levels (L4, L5, L6) and cannot be overridden by model output, configuration, or governance claims.

## New Packet Types

### pyper_execution_plan

A structured description of planned execution steps with safety classifications and dry-run summaries. No commands are executed.

**Required fields:**
- `execution_plan_data.plan_description` — what the plan intends to do
- `execution_plan_data.entity` — target entity
- `execution_plan_data.steps[]` — ordered list of planned steps
  - `step_index` — step position
  - `description` — what the step does
  - `safety_classification` — "safe" or "forbidden"
  - `risk_notes` — risk assessment
- `execution_plan_data.risk_level` — "low", "medium", or "high"
- `execution_plan_data.dependency_analysis` — what the plan depends on
- `execution_plan_data.dry_run_summary` — SIMULATED execution results
- `execution_plan_data.rollback_plan` — how to revert if execution goes wrong
- `execution_plan_data.sandbox_recommendation` — isolation guidance

**Enforced constraints:**
- `approval_required` = True (L4 + L6)
- `execution_authority` = "none" (L4 + L6)
- All steps must have `safety_classification` in ("safe", "forbidden")
- `risk_level` must be in ("low", "medium", "high")

### pyper_execution_receipt

A record of what happened during simulated execution. Receipts may only describe simulated or dry-run results — never claim real execution.

**Required fields:**
- `receipt_data.execution_type` — must be "simulated"
- `receipt_data.step_receipts[]` — per-step results
  - `actual_execution` — must be False
  - `step_index` — step position
- `receipt_data.overall_result` — must contain "SIMULATED"
- `receipt_data.side_effects` — must be empty list

**Enforced constraints:**
- `execution_type` must be "simulated" (L6)
- `actual_execution` must be False for every step receipt (L6)
- `overall_result` must contain the word "SIMULATED" (L6)
- `side_effects` must be empty (L6)

### pyper_execution_refusal

Issued when PypER refuses to produce an execution plan due to safety violations.

**Required fields:**
- `refusal_data.reason` — why execution was refused
- `refusal_data.refusal_category` — one of:
  - `unsafe_command`
  - `package_install_forbidden`
  - `remote_execution_forbidden`
  - `privilege_escalation_forbidden`
  - `governance_violation`
  - `sovereignty_violation`
  - `autonomous_execution_forbidden`
  - `safety_violation`
- `refusal_data.safety_violations[]` — specific violations detected
- `refusal_data.operator_action_required` — must be True
- `refusal_data.suggested_alternatives[]` — safe alternatives

**Enforced constraints:**
- `operator_action_required` must be True (L6)
- `approval_required` must be True (L6)

## Execution Safety Protections (L5)

v0.7.0 adds five new L5 protection patterns to the validator:

| Pattern | Regex | Blocks |
|---|---|---|
| SHELL_INJECTION_PATTERN | `\|\s*(ba)?sh\b|bash\s+-c|&&\s*(sudo\|rm\|chmod)` | Shell chain injection |
| REMOTE_EXECUTION_PATTERN | `curl\s+.*\|\s*(ba)?sh|wget\s+.*\|\s*(ba)?sh` | Remote code execution |
| PACKAGE_INSTALL_PATTERN | `(apt\|apt-get\|yum\|dnf\|pip\|pip3\|npm)\s+install` | Package installation |
| PRIVILEGE_ESCALATION_PATTERN | `sudo\s+|doas\s+|pkexec\s+|run0\s+` | Privilege escalation |
| DECEPTIVE_EXECUTION_PATTERN | `execution\s*(complete\|succeeded\|finished\|done)` | False execution claims |

All patterns are checked recursively through all packet fields except `audit_trail` (which contains descriptive context).

## Audit Trail Fields

Every PypER execution planning packet records:

| Field | Purpose |
|---|---|
| `selected_model` | Model used for inference |
| `selected_provider` | Provider used |
| `route_used` | Routing decision (e.g., "pyper/execution_plan/inference") |
| `inference_attempt_id` | Unique inference attempt identifier |
| `prompt_hash` | SHA-256 hash of the prompt (first 16 chars) |
| `raw_model_output_summary` | First 500 chars of raw model output |
| `sanitized_model_output_summary` | Output after sanitization |
| `validation_result` | 6-level validation outcome |
| `execution_authority` | Always "none" for PypER |
| `approval_required` | Always True for PypER |
| `fallback_used` | Whether deterministic fallback was used |
| `elapsed_s` | Wall-clock time for inference |
| `commands_executed` | Always 0 in inference mode |
| `inference_source` | "mock", "hermes", or "deterministic" |

## What PypER Cannot Do

The following are **permanently forbidden** in PypER inference mode:

1. Autonomous shell execution
2. Package installation (apt, pip, npm, etc.)
3. sudo / doas / pkexec operations
4. Filesystem mutation
5. Network scanning (nmap, nslookup, etc.)
6. Remote code execution (curl|bash, wget|sh)
7. Service/daemon management (systemctl, service)
8. Browser automation
9. Outbound network contact
10. Recursive task spawning
11. eval/exec dynamic Python patterns
12. Subprocess spawning from model-generated commands
13. Direct subagent routing (target must be "overcr")
14. Governance override claims

## Deterministic Fallback

If inference fails for any reason:
1. PypER falls back to a deterministic template-based execution plan
2. The deterministic plan uses safe, pre-defined steps
3. No task state is advanced on failure
4. The fallback packet is validated through the same 6-level validator
5. If the fallback also fails, the task remains in its current state

## Version History

| Version | Date | Change |
|---|---|---|
| v0.7.0 | 2026-05-11 | Controlled live execution planning mode, 3 new packet types, L5/L6 protections |
| v0.6.0 | 2026-05-10 | CodER patch plan inference |
| v0.5.0 | 2026-05-09 | KnowER inference pipeline |
| v0.4.2 | 2026-05-08 | Hermes CLI adapter, CryER v0.4.0 |
| v0.4.1 | 2026-05-07 | CryER live worker, inference adapter |
| v0.4.0 | 2026-05-06 | CryER reconnaissance subagent |
| v0.3.0 | 2026-05-05 | Approval gate enforcement |
| v0.2.1 | 2026-05-04 | Live worker subsystem |
| v0.2.0 | 2026-05-03 | Inference pipeline |
| v0.1.0 | 2026-05-02 | Initial runtime, KnowER + CodER |

## Runtime Registrations

| Component | Registration |
|---|---|
| task_store.SUBAGENT_PACKET_TYPES["pyper"] | execution_plan, execution_receipt, execution_refusal (added) |
| task_store.DOMAIN_SUBAGENT_MAP["execution_plan"] | "pyper" |
| task_store._default_packet_type["pyper"]["execution_plan"] | "pyper_execution_plan" |
| subagent_adapter.WORKER_REGISTRY["pyper"] | "subagents/pyper/worker.py" |
| subagent_adapter.LIVE_WORKER_DOMAINS["execution_plan"] | "pyper" |
| overcr_runtime.ROUTING_TABLE[("pyper","pyper_execution_plan")] | target=operator |
| overcr_runtime.ROUTING_TABLE[("pyper","pyper_execution_receipt")] | target=operator |
| overcr_runtime.ROUTING_TABLE[("pyper","pyper_execution_refusal")] | target=operator |
| inference_routing._pyper.execution_plan | enabled=true, adapter=mock |
| inference_adapter mock branch | execution_plan domain |