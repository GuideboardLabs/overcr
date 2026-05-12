#!/usr/bin/env python3
"""
OverCR PypER Inference Worker — v0.7.0
========================================

Model-assisted execution planning mode for PypER. This worker extends
the simulated-only PypER with controlled live execution planning using
the Hermes-backed inference pipeline.

Architecture:
  - Receives request on stdin (same contract as deterministic worker)
  - Reads inference_routing.yaml config to determine if inference is enabled
  - If inference enabled: calls inference adapter -> model produces structured execution plan
  - Model output is merged into typed packet envelope
  - ALL packets (inferenced or deterministic) go through 6-level validator
  - If inference fails: falls back to deterministic template builder
  - If fallback fails: task does NOT advance state (safe failure)

PypER execution planning responsibilities:
  - execution planning
  - sandbox recommendations
  - dependency analysis
  - dry-run execution summaries
  - deterministic execution receipts
  - rollback recommendations
  - runtime diagnostics
  - bounded command classification

Governance (enforced regardless of model output):
  - Model output CANNOT change doctrine
  - Model output CANNOT bypass approval gates
  - Model output CANNOT route directly to another subagent
  - Model output CANNOT claim live browsing occurred
  - NO command is executed automatically from inference output
  - ALL execution plans require approval_required=true
  - Direct shell execution is FORBIDDEN in inference mode
  - Filesystem mutation is FORBIDDEN in inference mode
  - No subprocess spawning from model-generated commands
  - No package install commands allowed
  - No curl/wget remote execution patterns
  - No eval/exec dynamic Python patterns
  - Output target must always be "overcr"
  - Reject direct subagent routing
  - Reject governance override claims
  - Deterministic fallback remains available
  - Execution receipts may only describe simulated execution, deterministic
    dry-run results, and sandbox-safe observations
  - Receipts may NOT claim commands actually ran unless execution authority
    explicitly exists

Worker contract (same as other inference workers):
  - Input:  JSON request packet on stdin
  - Output: JSON response packet on stdout
  - Exit 0: success (response packet valid)
  - Exit nonzero: failure (caller must not trust output)
"""

import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# Resolve project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Add project root to path for imports
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(_PROJECT_ROOT / "runtime"))
sys.path.insert(0, str(_PROJECT_ROOT / "tools"))

# Import runtime modules
from runtime.inference_adapter import BaseInferenceAdapter, MockInferenceAdapter, HermesInferenceAdapter, get_adapter
from runtime.inference_result import InferenceResult, InferenceStatus, InferenceMetadata

# Import validator for post-inference validation
import importlib.util as _ilu
_val_spec = _ilu.spec_from_file_location(
    "validate_packet",
    str(_PROJECT_ROOT / "tools" / "validate_packet.py"),
)
_val_mod = _ilu.module_from_spec(_val_spec)
_val_spec.loader.exec_module(_val_mod)
validate_packet = _val_mod.validate_packet


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def load_inference_config() -> dict:
    """Load inference_routing.yaml config."""
    config_path = _PROJECT_ROOT / "config" / "inference_routing.yaml"
    if not config_path.exists():
        return {"_inference_defaults": {"enabled": False}}
    try:
        import yaml
        with open(config_path, "r") as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        return _parse_yaml_simple(config_path)


def _parse_yaml_simple(path: Path) -> dict:
    """Minimal YAML parser for inference_routing.yaml without PyYAML."""
    config = {}
    current_section = None
    current_subsection = None

    with open(path, "r") as f:
        for line in f:
            line = line.rstrip()
            if not line or line.lstrip().startswith("#"):
                continue
            stripped = line.lstrip()
            indent = len(line) - len(stripped)

            if ":" in stripped and not stripped.startswith("-"):
                key, _, value = stripped.partition(":")
                key = key.strip()
                value = value.strip()

                if "#" in value:
                    value = value[:value.index("#")].strip()

                if value and value not in ("null", "~", ""):
                    if value.startswith('"') and value.endswith('"'):
                        parsed = value[1:-1]
                    elif value.startswith("'") and value.endswith("'"):
                        parsed = value[1:-1]
                    elif value.lower() == "true":
                        parsed = True
                    elif value.lower() == "false":
                        parsed = False
                    elif value.isdigit():
                        parsed = int(value)
                    else:
                        try:
                            parsed = float(value)
                        except ValueError:
                            parsed = value

                    if indent == 0:
                        if key.startswith("_"):
                            config[key] = {}
                            current_section = key
                            current_subsection = None
                        else:
                            config[key] = parsed
                    elif indent >= 2:
                        if current_section and current_section in config:
                            if isinstance(config[current_section], dict):
                                if current_subsection and isinstance(config[current_section].get(current_subsection), dict):
                                    config[current_section][current_subsection][key] = parsed
                                else:
                                    config[current_section][key] = parsed

                elif not value:
                    if indent == 0:
                        if key.startswith("_"):
                            config[key] = {}
                            current_section = key
                            current_subsection = None
                    elif indent >= 2 and current_section:
                        if current_section not in config:
                            config[current_section] = {}
                        if isinstance(config[current_section], dict):
                            config[current_section][key] = {}
                            current_subsection = key
    return config


def get_domain_config(config: dict, domain: str) -> dict:
    """Get the inference config for a specific pyper domain."""
    defaults = config.get("_inference_defaults", {})
    pyper = config.get("_pyper", {})
    domain_cfg = pyper.get(domain, {})

    merged = dict(defaults)
    merged.update(domain_cfg)
    return merged


# ---------------------------------------------------------------------------
# Prompt rendering
# ---------------------------------------------------------------------------

def render_prompt(template_path: Path, task_id: str, domain: str,
                  instruction: str, input_context: dict) -> str:
    """Render the inference prompt template with task context."""
    if not template_path.exists():
        return (
            f"Task ID: {task_id}\n"
            f"Domain: {domain}\n"
            f"Instruction: {instruction}\n\n"
            f"Input context:\n{json.dumps(input_context, indent=2)}\n\n"
            f"Produce structured JSON output for the {domain} domain."
        )

    template_text = template_path.read_text()

    context = {
        "task_id": task_id,
        "domain": domain,
        "instruction": instruction,
        "input_context": json.dumps(input_context, indent=2) if isinstance(input_context, dict) else str(input_context),
    }

    result = template_text
    for key, value in context.items():
        result = result.replace("{{" + key + "}}", str(value))

    return result


# ---------------------------------------------------------------------------
# Execution safety: command classification
# ---------------------------------------------------------------------------

# Commands that are FORBIDDEN in any PypER execution plan
FORBIDDEN_COMMAND_PATTERNS = [
    # Package installation
    r'(?:apt|apt-get|yum|dnf|pip|pip3|npm|yarn|cargo|gem)\s+install',
    # Remote execution
    r'curl\s+.*\|\s*(?:bash|sh|python|python3)',
    r'wget\s+.*\|\s*(?:bash|sh|python|python3)',
    r'curl\s+.*(?:--exec|exec)',
    # Dynamic Python execution
    r'\beval\s*\(',
    r'\bexec\s*\(',
    r'subprocess\.(call|run|Popen|check_output|check_call)',
    r'os\.system\s*\(',
    r'os\.popen\s*\(',
    # Privilege escalation
    r'\bsudo\s+',
    r'\bsu\s+',
    r'chmod\s+[0-7]{3,4}\s+',
    r'chown\s+',
    # Network scanning
    r'\bnmap\s+',
    r'\bnc\s+-',
    r'\bnetcat\s+',
    # Daemon/service management
    r'\bsystemctl\s+',
    r'\bservice\s+',
    r'\bdaemonize\b',
]

import re

FORBIDDEN_COMMAND_RE = [re.compile(p, re.IGNORECASE) for p in FORBIDDEN_COMMAND_PATTERNS]


def classify_command_safety(command: str) -> dict:
    """
    Classify a command as safe or forbidden for PypER execution planning.

    Returns dict with:
      - safe: bool
      - forbidden_patterns: list of matched pattern descriptions
      - classification: 'safe' | 'forbidden'
    """
    if not command or not command.strip():
        return {"safe": True, "forbidden_patterns": [], "classification": "safe"}

    matched = []
    for i, pattern in enumerate(FORBIDDEN_COMMAND_PATTERNS):
        if re.search(pattern, command, re.IGNORECASE):
            matched.append(f"forbidden_pattern_{i+1}: {pattern}")

    if matched:
        return {"safe": False, "forbidden_patterns": matched, "classification": "forbidden"}

    return {"safe": True, "forbidden_patterns": [], "classification": "safe"}


# ---------------------------------------------------------------------------
# Inference worker core
# ---------------------------------------------------------------------------


def build_inference_packet(request: dict, adapter: BaseInferenceAdapter,
                           config: dict) -> Optional[dict]:
    """
    Attempt to build a packet using inference (model-assisted reasoning).

    Returns:
        - Packet dict on success (untrusted until validated)
        - None on failure (caller should use deterministic fallback)
    """
    domain = request.get("domain", "execution_plan")
    # Map domain to packet type
    domain_to_packet_type = {
        "execution_plan": "pyper_execution_plan",
    }
    packet_type = request.get("required_packet_type", "") or domain_to_packet_type.get(domain, "")
    task_id = request.get("task_id", "task-0000")
    instruction = request.get("instruction", "")
    input_context = request.get("input_context", {})

    if packet_type != "pyper_execution_plan":
        # Inference not supported for this domain yet
        return None

    # Render prompt from template
    template_path = _PROJECT_ROOT / "subagents" / "pyper" / "inference_prompt.md"
    prompt = render_prompt(template_path, task_id, domain, instruction, input_context)

    # Compute prompt hash for audit
    prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]

    # Build adapter config
    adapter_config = {
        "domain": domain,
        "model": config.get("model", "glm-5.1:cloud"),
        "provider": config.get("provider", "mock"),
        "timeout_s": config.get("timeout_s", 30.0),
        "task_id": task_id,
        "input_context": input_context,
        "instruction": instruction,
    }

    # Invoke the adapter
    start_time = time.time()
    result = adapter.invoke(prompt, adapter_config)
    elapsed = time.time() - start_time

    if result.metadata.status != InferenceStatus.SUCCESS or result.packet is None:
        # Inference failed
        return None

    # result.packet is the parsed JSON from the model
    model_data = result.packet

    # Classify any commands in the execution plan for safety
    plan_data = model_data.get("execution_plan_data", {})
    steps = plan_data.get("steps", [])
    command_safety_results = []
    for step in steps:
        cmd = step.get("command", "")
        if cmd:
            safety = classify_command_safety(cmd)
            command_safety_results.append({
                "step_index": step.get("step_index", 0),
                "command": cmd,
                "safe": safety["safe"],
                "classification": safety["classification"],
                "forbidden_patterns": safety["forbidden_patterns"],
            })
            # Override step safety classification
            step["safety_classification"] = safety["classification"]

    # Determine overall execution_authority
    has_forbidden = any(not s["safe"] for s in command_safety_results) if command_safety_results else False

    # Wrap in the full packet envelope
    packet = {
        "packet_type": "pyper_execution_plan",
        "version": "1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "pyper",
        "target": "overcr",
        "task_id": task_id,
        "summary": f"PypER execution plan: {instruction[:100]}",
        "execution_plan_data": plan_data,
        "command_safety_audit": command_safety_results if command_safety_results else [],
        "audit_trail": {
            "worker_version": "0.7.0",
            "execution_timestamp": datetime.now(timezone.utc).isoformat(),
            "files_modified": [],  # PypER inference never modifies files
            "rollback_instructions": "No filesystem changes made by inference worker. Execution plan is advisory only.",
            "inference_mode": True,
            "inference_source": adapter.adapter_type,
            "inference_attempt_id": result.metadata.inference_attempt_id,
            "inference_model": config.get("model", "unknown"),
            "prompt_hash": prompt_hash,
            "selected_model": config.get("model", "unknown"),
            "selected_provider": config.get("provider", "unknown"),
            "route_used": f"pyper/{domain}/inference",
            "raw_model_output_summary": result.metadata.raw_output_summary[:500],
            "sanitized_model_output_summary": result.metadata.sanitized_output_summary[:500] if result.metadata.sanitized_output_summary else "",
            "validation_result": None,  # filled after validation
            "execution_authority": "none",  # PypER never has execution authority
            "approval_required": True,  # ALL PypER requires approval
            "fallback_used": False,
            "elapsed_s": round(elapsed, 3),
            "inference_elapsed_s": round(elapsed, 3),
        },
        "approval_required": True,  # ALL PypER execution plans require approval
        "execution_authority": "none",  # PypER has NO execution authority
        "next_steps_recommendation": "Review execution plan. No command will be executed automatically. All steps require explicit operator approval and Hermes-mediated execution.",
    }

    if has_forbidden:
        packet["execution_plan_data"]["contains_forbidden_commands"] = True
        packet["next_steps_recommendation"] = (
            "EXECUTION PLAN CONTAINS FORBIDDEN COMMANDS. "
            "Review safety audit. Forbidden commands must be removed or replaced "
            "before approval. No execution will proceed."
        )

    # Validate the packet
    valid, errors, warnings = validate_packet(packet)
    packet["audit_trail"]["validation_result"] = {
        "valid": valid,
        "errors": errors,
        "warnings": warnings,
    }

    if not valid:
        return None  # Validation failed — fall back to deterministic

    return packet


def build_deterministic_execution_plan_packet(request: dict) -> dict:
    """
    Build a deterministic pyper_execution_plan response packet (fallback).

    This uses template-based execution planning with no model calls.
    No commands are executed. No filesystem changes are made.
    """
    task_id = request.get("task_id", "task-0000")
    instruction = request.get("instruction", "")
    input_context = request.get("input_context", {})
    entity = input_context.get("entity", "unspecified target")
    upstream_id = input_context.get("upstream_task_id", "")

    instruction_lower = instruction.lower()

    # Build execution plan steps (advisory only — never executed)
    steps = []

    # Step 1: Analysis
    steps.append({
        "step_index": 1,
        "description": f"Analyze requirements for: {entity}",
        "command": "",
        "safety_classification": "safe",
        "expected_outcome": "Requirements documented",
        "rollback": "No action taken; nothing to roll back",
    })

    # Step 2: Dry-run verification
    steps.append({
        "step_index": 2,
        "description": f"Dry-run verification for: {entity}",
        "command": "",
        "safety_classification": "safe",
        "expected_outcome": "Dry-run results captured without side effects",
        "rollback": "No action taken; nothing to roll back",
    })

    # Step 3: Dependency check (informational only)
    steps.append({
        "step_index": 3,
        "description": "Dependency analysis (informational only)",
        "command": "",
        "safety_classification": "safe",
        "expected_outcome": "Dependencies identified for operator review",
        "rollback": "No action taken; nothing to roll back",
    })

    # Build deterministic plan description
    plan_description = f"Execution plan for: {entity}"
    if "deploy" in instruction_lower or "install" in instruction_lower:
        plan_description = f"Advisory execution plan for deployment of: {entity}"
    elif "configure" in instruction_lower or "setup" in instruction_lower:
        plan_description = f"Advisory execution plan for configuration of: {entity}"
    elif "run" in instruction_lower or "execute" in instruction_lower:
        plan_description = f"Advisory execution plan for execution of: {entity}"
    elif "debug" in instruction_lower or "troubleshoot" in instruction_lower:
        plan_description = f"Advisory execution plan for diagnostics on: {entity}"

    # Build the execution plan packet
    packet = {
        "packet_type": "pyper_execution_plan",
        "version": "1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "pyper",
        "target": "overcr",
        "task_id": task_id,
        "summary": f"PypER execution plan: {instruction[:100]}",
        "execution_plan_data": {
            "plan_description": plan_description,
            "entity": entity,
            "steps": steps,
            "sandbox_recommendation": "Execute in isolated environment with no network access; use read-only filesystem mounts",
            "dependency_analysis": {
                "dependencies_identified": [],
                "missing_dependencies": [],
                "conflict_risks": [],
            },
            "dry_run_summary": "Deterministic fallback cannot perform live dry-run. Execution plan is advisory only.",
            "contains_forbidden_commands": False,
            "risk_level": "low",
            "estimated_duration": "unknown (deterministic fallback cannot estimate)",
            "rollback_plan": "No actions are taken by this worker. All execution must be operator-initiated via Hermes.",
        },
        "command_safety_audit": [],
        "audit_trail": {
            "worker_version": "0.7.0",
            "execution_timestamp": datetime.now(timezone.utc).isoformat(),
            "files_modified": [],  # Advisory-only: nothing actually modified
            "rollback_instructions": "No filesystem changes made by worker. Execution plan is advisory only.",
            "inference_mode": False,
            "inference_source": "deterministic",
            "fallback_used": False,
            "execution_authority": "none",
            "approval_required": True,
        },
        "approval_required": True,  # ALL PypER requires approval
        "execution_authority": "none",  # PypER has NO execution authority
        "next_steps_recommendation": "Review advisory execution plan. No command will be executed automatically. All steps require explicit operator approval.",
    }

    if upstream_id:
        packet["upstream_task_id"] = upstream_id

    return packet


def build_execution_refusal_packet(request: dict, reason: str) -> dict:
    """
    Build a pyper_execution_refusal packet when the requested execution
    is forbidden or unsafe.

    This is returned when:
      - The command contains forbidden patterns
      - The request requests autonomous execution
      - The request attempts governance override
      - The request targets a subagent directly
    """
    task_id = request.get("task_id", "task-0000")
    instruction = request.get("instruction", "")

    packet = {
        "packet_type": "pyper_execution_refusal",
        "version": "1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "pyper",
        "target": "overcr",
        "task_id": task_id,
        "summary": f"PypER execution refusal: {reason[:100]}",
        "refusal_data": {
            "reason": reason,
            "requested_action": instruction,
            "refusal_category": _classify_refusal(reason),
            "alternate_approach": _suggest_alternate(reason),
            "operator_action_required": True,
        },
        "audit_trail": {
            "worker_version": "0.7.0",
            "execution_timestamp": datetime.now(timezone.utc).isoformat(),
            "files_modified": [],
            "rollback_instructions": "No action taken; nothing to roll back",
            "inference_mode": False,
            "inference_source": "deterministic",
            "fallback_used": False,
            "execution_authority": "none",
            "approval_required": True,
        },
        "approval_required": True,
        "execution_authority": "none",
        "next_steps_recommendation": "Review refusal reason. Modify request or escalate to operator for governance decision.",
    }

    return packet


def _classify_refusal(reason: str) -> str:
    """Classify the refusal reason into a category."""
    reason_lower = reason.lower()
    if "forbidden command" in reason_lower or "shell injection" in reason_lower:
        return "unsafe_command"
    elif "package install" in reason_lower or "apt" in reason_lower or "pip" in reason_lower:
        return "package_install_forbidden"
    elif "remote execution" in reason_lower or "curl" in reason_lower:
        return "remote_execution_forbidden"
    elif "privilege escalation" in reason_lower or "sudo" in reason_lower:
        return "privilege_escalation_forbidden"
    elif "governance override" in reason_lower:
        return "governance_violation"
    elif "direct subagent" in reason_lower or "target" in reason_lower:
        return "sovereignty_violation"
    elif "autonomous execution" in reason_lower:
        return "autonomous_execution_forbidden"
    else:
        return "safety_violation"


def _suggest_alternate(reason: str) -> str:
    """Suggest an alternate approach for a refused execution."""
    reason_lower = reason.lower()
    if "forbidden command" in reason_lower or "shell injection" in reason_lower:
        return "Request operator to review command safety and execute manually via Hermes if approved."
    elif "package install" in reason_lower:
        return "Document required packages in plan. Operator can install manually after review."
    elif "remote execution" in reason_lower:
        return "Download content locally first, verify integrity, then review before any execution."
    elif "privilege escalation" in reason_lower:
        return "Run with minimal required privileges. Document why elevated access is needed for operator review."
    elif "governance override" in reason_lower:
        return "Submit governance change request through OverCR governance process. No self-override permitted."
    elif "autonomous execution" in reason_lower:
        return "Prepare an execution plan with approval_required=true. Operator must approve each step before execution."
    else:
        return "Modify request to comply with PypER safety constraints. Request operator review if needed."


def build_execution_receipt_packet(request: dict, plan_packet: dict,
                                    simulated_result: str = "") -> dict:
    """
    Build a pyper_execution_receipt packet describing the result of a
    simulated/dry-run execution.

    Receipts may ONLY describe:
      - Simulated execution
      - Deterministic dry-run results
      - Sandbox-safe observations

    Receipts may NOT claim commands actually ran unless execution authority
    explicitly exists (which for PypER, it never does in inference mode).
    """
    task_id = request.get("task_id", plan_packet.get("task_id", "task-0000"))
    plan_steps = plan_packet.get("execution_plan_data", {}).get("steps", [])

    # Build receipt for each step (simulated only)
    step_receipts = []
    for step in plan_steps:
        step_receipts.append({
            "step_index": step.get("step_index", 0),
            "description": step.get("description", ""),
            "simulated_result": "SIMULATED: No actual execution occurred",
            "actual_execution": False,  # NEVER true for PypER inference
            "side_effects": [],
            "exit_code": None,  # No real exit code — not executed
            "observations": "Dry-run observation only; no command was run",
        })

    if simulated_result:
        step_receipts[0]["simulated_result"] = f"SIMULATED: {simulated_result}"

    packet = {
        "packet_type": "pyper_execution_receipt",
        "version": "1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "pyper",
        "target": "overcr",
        "task_id": task_id,
        "summary": "[SIMULATED] PypER execution receipt: dry-run results",
        "receipt_data": {
            "execution_type": "simulated",  # Always simulated for PypER
            "steps_completed": len(step_receipts),
            "steps_failed": 0,
            "step_receipts": step_receipts,
            "overall_result": "SIMULATED: No commands were actually executed. All results are dry-run observations only.",
            "warnings": ["Execution was simulated; no actual system changes occurred"],
            "side_effects": [],
        },
        "audit_trail": {
            "worker_version": "0.7.0",
            "execution_timestamp": datetime.now(timezone.utc).isoformat(),
            "files_modified": [],  # Nothing actually modified
            "rollback_instructions": "No action taken; nothing to roll back",
            "inference_mode": plan_packet.get("audit_trail", {}).get("inference_mode", False),
            "inference_source": "deterministic",
            "fallback_used": False,
            "execution_authority": "none",
            "approval_required": True,
        },
        "approval_required": True,
        "execution_authority": "none",
        "next_steps_recommendation": "Execution was simulated only. Review plan and results. Approve individual steps for Hermes-mediated execution if needed.",
    }

    if plan_packet.get("upstream_task_id"):
        packet["upstream_task_id"] = plan_packet["upstream_task_id"]

    return packet


def read_request() -> dict:
    """Read and parse the request packet from stdin."""
    raw = sys.stdin.read()
    if not raw.strip():
        print(json.dumps({
            "error": "empty_input",
            "message": "Worker received empty input on stdin",
        }), file=sys.stderr)
        sys.exit(1)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        print(json.dumps({
            "error": "invalid_json",
            "message": f"Worker received invalid JSON on stdin: {e}",
        }), file=sys.stderr)
        sys.exit(1)


def main():
    """
    Main entry point: read request, attempt inference, fallback to deterministic.

    Flow:
      1. Read request from stdin
      2. Load inference config
      3. If execution_plan domain and inference enabled: try inference
      4. If inference fails or not enabled: fall back to deterministic
      5. If fallback also fails: exit nonzero (task does NOT advance)
      6. On success: write response packet to stdout and exit 0
    """
    request = read_request()
    domain = request.get("domain", "execution_plan")
    required_packet_type = request.get("required_packet_type", "")

    # Check for explicit refusal conditions before processing
    instruction = request.get("instruction", "").lower()

    # Refuse requests that ask for autonomous execution
    if any(phrase in instruction for phrase in [
        "execute automatically", "run without approval", "skip approval",
        "bypass approval", "autonomous execution", "no approval needed",
    ]):
        packet = build_execution_refusal_packet(
            request,
            "Autonomous execution is forbidden. All PypER execution plans require approval_required=true and operator review."
        )
        valid, errors, warnings = validate_packet(packet)
        if valid:
            print(json.dumps(packet, indent=2))
            sys.exit(0)
        else:
            print(json.dumps({
                "error": "validation_failed",
                "message": f"PypER refusal packet failed validation: {errors}",
            }), file=sys.stderr)
            sys.exit(1)

    # Refuse requests that target a subagent directly
    target = request.get("target", "overcr")
    if target != "overcr" and target in ("cryer", "coder", "knower"):
        packet = build_execution_refusal_packet(
            request,
            f"Direct subagent routing to '{target}' is forbidden. All handoffs must go through OverCR."
        )
        valid, errors, warnings = validate_packet(packet)
        if valid:
            print(json.dumps(packet, indent=2))
            sys.exit(0)
        else:
            print(json.dumps({
                "error": "validation_failed",
                "message": f"PypER refusal packet failed validation: {errors}",
            }), file=sys.stderr)
            sys.exit(1)

    # For execution_plan domain — try inference first
    if domain not in ("execution_plan",) and required_packet_type != "pyper_execution_plan":
        # Use deterministic fallback for domains not yet supported
        packet = build_deterministic_execution_plan_packet(request)
        print(json.dumps(packet, indent=2))
        sys.exit(0)

    # Execution plan domain — try inference first
    config = load_inference_config()
    domain_config = get_domain_config(config, domain)

    packet = None
    fallback_used = False

    if domain_config.get("enabled", False):
        # Try inference
        adapter_type = domain_config.get("adapter", "mock")
        try:
            adapter = get_adapter(adapter_type)
        except Exception:
            adapter = None

        if adapter and adapter.is_available():
            try:
                packet = build_inference_packet(request, adapter, domain_config)
            except Exception:
                packet = None

    # Fallback to deterministic if inference failed or not enabled
    if packet is None:
        fallback_used = True
        packet = build_deterministic_execution_plan_packet(request)
        # Mark fallback in audit trail
        if "audit_trail" in packet:
            packet["audit_trail"]["fallback_used"] = True
            packet["audit_trail"]["inference_source"] = "deterministic"

    if packet is None:
        # Both inference and fallback failed — this should not happen
        # with deterministic fallback, but defense in depth
        print(json.dumps({
            "error": "worker_failure",
            "message": "PypER inference worker: both inference and fallback failed",
        }), file=sys.stderr)
        sys.exit(1)

    # Final validation before output
    valid, errors, warnings = validate_packet(packet)
    if not valid:
        print(json.dumps({
            "error": "validation_failed",
            "message": f"PypER inference worker output failed validation: {errors}",
        }), file=sys.stderr)
        sys.exit(1)

    print(json.dumps(packet, indent=2))
    sys.exit(0)


if __name__ == "__main__":
    main()