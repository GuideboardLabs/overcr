#!/usr/bin/env python3
"""
OverCR CodER Inference Worker — v0.6.0
========================================

Model-assisted reasoning mode for CodER. This worker extends the
deterministic CodER worker with optional live model inference for
patch_plan domain — code analysis, bug diagnosis, patch planning,
proposed diffs, test plans, rollback plans, and risk notes.

Architecture:
  - Receives request on stdin (same contract as deterministic worker)
  - Reads inference_routing.yaml config to determine if inference is enabled
  - If inference enabled: calls inference adapter -> model produces structured output
  - Model output is merged into typed packet envelope
  - ALL packets (inferenced or deterministic) go through 6-level validator
  - If inference fails: falls back to deterministic worker (same as v0.2.0)
  - If fallback fails: task does NOT advance state (safe failure)

Governance (enforced regardless of model output):
  - Model output CANNOT change doctrine
  - Model output CANNOT bypass approval gates
  - Model output CANNOT route directly to another subagent
  - Model output CANNOT claim live browsing occurred
  - No patch is applied automatically
  - No shell command is executed automatically
  - No files are modified by CodER inference mode
  - Proposed diffs are advisory artifacts only
  - All mutation requires OverCR approval gate
  - Output target must be overcr only
  - Reject direct subagent routing
  - Reject governance override claims
  - deterministic CodER worker remains fallback

Worker contract (same as deterministic):
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

# Import deterministic worker functions (fallback)
sys.path.insert(0, str(_PROJECT_ROOT / "subagents" / "coder"))
from worker import (
    build_completion_packet,
    build_diagnostic_packet,
    read_request,
)

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
    """Get the inference config for a specific coder domain."""
    defaults = config.get("_inference_defaults", {})
    coder = config.get("_coder", {})
    domain_cfg = coder.get(domain, {})

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
    domain = request.get("domain", "patch_plan")
    # Map domain to packet type
    domain_to_packet_type = {
        "patch_plan": "coder_patch_plan",
    }
    packet_type = request.get("required_packet_type", "") or domain_to_packet_type.get(domain, "")
    task_id = request.get("task_id", "task-0000")
    instruction = request.get("instruction", "")
    input_context = request.get("input_context", {})

    if packet_type != "coder_patch_plan":
        # Inference not supported for this domain
        return None

    # Render prompt from template
    template_path = _PROJECT_ROOT / "subagents" / "coder" / "inference_prompt.md"
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

    # Wrap in the full packet envelope
    packet = {
        "packet_type": "coder_patch_plan",
        "version": "1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "coder",
        "target": "overcr",
        "task_id": task_id,
        "summary": f"CodER inference patch plan: {instruction[:100]}",
        "patch_plan_data": model_data.get("patch_plan_data", {}),
        "audit_trail": {
            "worker_version": "0.6.0",
            "execution_timestamp": datetime.now(timezone.utc).isoformat(),
            "files_modified": [],  # Advisory-only: no files actually modified
            "rollback_instructions": model_data.get("patch_plan_data", {}).get("rollback_plan", "No filesystem changes made by inference worker."),
            "inference_mode": True,
            "inference_source": adapter.adapter_type,
            "inference_attempt_id": result.metadata.inference_attempt_id,
            "inference_model": config.get("model", "unknown"),
            "prompt_hash": prompt_hash,
            "selected_model": config.get("model", "unknown"),
            "selected_provider": config.get("provider", "unknown"),
            "route_used": f"coder/{domain}/inference",
            "raw_model_output_summary": result.metadata.raw_output_summary[:500],
            "sanitized_model_output_summary": result.metadata.sanitized_output_summary[:500],
            "validation_result": None,  # filled after validation
            "fallback_used": False,
            "elapsed_s": round(elapsed, 3),
            "inference_elapsed_s": round(elapsed, 3),
        },
        "approval_required": True,  # ALL file mutation requires approval
        "next_steps_recommendation": "Review advisory patch plan. Apply changes only after operator approval.",
    }

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


def build_deterministic_patch_plan_packet(request: dict) -> dict:
    """
    Build a deterministic coder_patch_plan response packet (fallback).

    This uses the same template-based approach as the deterministic worker.
    No model calls, no filesystem changes.
    """
    task_id = request.get("task_id", "task-0000")
    instruction = request.get("instruction", "")
    input_context = request.get("input_context", {})
    entity = input_context.get("entity", "unspecified target")
    upstream_id = input_context.get("upstream_task_id", "")

    instruction_lower = instruction.lower()

    # Code inspection summary
    inspection_summary = f"Code inspection for: {entity}"
    if "inspect" in instruction_lower or "review" in instruction_lower:
        inspection_summary = f"Detailed code inspection for: {entity}"
    elif "bug" in instruction_lower or "fix" in instruction_lower or "error" in instruction_lower:
        inspection_summary = f"Bug diagnosis for: {entity}"
    elif "patch" in instruction_lower or "modify" in instruction_lower or "change" in instruction_lower:
        inspection_summary = f"Patch planning for: {entity}"

    # Build the patch plan packet
    packet = {
        "packet_type": "coder_patch_plan",
        "version": "1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "coder",
        "target": "overcr",
        "task_id": task_id,
        "summary": f"CodER patch plan: {instruction[:100]}",
        "patch_plan_data": {
            "code_inspection_summary": inspection_summary,
            "bug_diagnosis": {
                "summary": f"Analysis of issue in {entity} based on instruction",
                "root_cause": "Requires further investigation; deterministic worker cannot perform deep analysis",
                "confidence": 0.3,
            },
            "patch_plan": {
                "description": f"Proposed patch for: {entity}",
                "files_to_modify": [entity],
                "approach": "Operator review required — advisory plan only",
                "estimated_complexity": "medium",
            },
            "proposed_diff": f"--- a/{entity}\n+++ b/{entity}\n@@ advisory diff @@\n- no changes made\n+ pending operator approval\n",
            "test_plan": {
                "strategy": f"Verify fix for {entity} does not introduce regressions",
                "test_cases": [f"Test that {entity} behaves correctly after patch"],
                "verification_steps": ["Run existing test suite", "Apply patch in isolated environment first"],
            },
            "rollback_plan": f"Revert changes to {entity} via version control; no filesystem changes made by worker",
            "risk_notes": {
                "level": "medium",
                "factors": ["Automated patch requires human review", "Impact scope not fully determined by deterministic analysis"],
                "mitigations": ["Operator approval required before any file mutation", "Patch is advisory artifact only"],
            },
        },
        "audit_trail": {
            "worker_version": "0.6.0",
            "execution_timestamp": datetime.now(timezone.utc).isoformat(),
            "files_modified": [],  # Advisory-only: nothing actually modified
            "rollback_instructions": "No filesystem changes made by worker. Deliverables are advisory plans only.",
            "inference_mode": False,
            "inference_source": "deterministic",
            "fallback_used": False,
        },
        "approval_required": True,  # ALL file mutation requires approval
        "next_steps_recommendation": "Review advisory patch plan. Apply changes only after operator approval.",
    }

    if upstream_id:
        packet["upstream_task_id"] = upstream_id

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
      3. If patch_plan domain and inference enabled: try inference
      4. If inference fails or not enabled: fall back to deterministic
      5. If fallback also fails: exit nonzero (task does NOT advance)
      6. On success: write response packet to stdout and exit 0
    """
    request = read_request()
    domain = request.get("domain", "patch_plan")
    required_packet_type = request.get("required_packet_type", "")

    # For non-patch-plan domains, delegate to deterministic worker
    if domain not in ("patch_plan",) and required_packet_type != "coder_patch_plan":
        # Use deterministic worker for code/diagnostics domains
        if domain == "diagnostics" or required_packet_type == "coder_diagnostic":
            packet = build_diagnostic_packet(request)
        elif domain == "code" or required_packet_type == "coder_completion":
            packet = build_completion_packet(request)
        else:
            packet = build_completion_packet(request)

        print(json.dumps(packet, indent=2))
        sys.exit(0)

    # Patch plan domain — try inference first
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
        packet = build_deterministic_patch_plan_packet(request)
        # Mark fallback in audit trail
        if "audit_trail" in packet:
            packet["audit_trail"]["fallback_used"] = True
            packet["audit_trail"]["inference_source"] = "deterministic"

    if packet is None:
        # Both inference and fallback failed — this should not happen
        # with deterministic fallback, but defense in depth
        print(json.dumps({
            "error": "worker_failure",
            "message": "CodER inference worker: both inference and fallback failed",
        }), file=sys.stderr)
        sys.exit(1)

    # Final validation before output
    valid, errors, warnings = validate_packet(packet)
    if not valid:
        print(json.dumps({
            "error": "validation_failed",
            "message": f"CodER inference worker output failed validation: {errors}",
        }), file=sys.stderr)
        sys.exit(1)

    print(json.dumps(packet, indent=2))
    sys.exit(0)


if __name__ == "__main__":
    main()