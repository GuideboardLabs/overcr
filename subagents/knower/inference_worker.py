#!/usr/bin/env python3
"""
OverCR KnowER Inference Worker — v0.4.1
=========================================

Model-assisted reasoning mode for KnowER. This worker extends the
deterministic KnowER worker with optional live model inference for
claim_review and myth_fact domains.

Architecture:
  - Receives request on stdin (same contract as deterministic worker)
  - Reads inference_routing.yaml config to determine if inference is enabled
  - If inference enabled: calls inference adapter → model produces structured output
  - Model output is merged into typed packet envelope
  - ALL packets (inferenced or deterministic) go through 6-level validator
  - If inference fails: falls back to deterministic worker (same as v0.4.0)
  - If fallback fails: task does NOT advance state (safe failure)

Governance (enforced regardless of model output):
  - Model output CANNOT change doctrine
  - Model output CANNOT bypass approval gates
  - Model output CANNOT route directly to another subagent
  - Model output CANNOT claim live browsing occurred
  - Model output must distinguish: fact, inference, assumption, rumor, unknown
  - On inference failure, task MUST NOT advance state
  - Deterministic worker MUST remain available as fallback

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
from datetime import datetime, timezone
from pathlib import Path
from string import Template
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
sys.path.insert(0, str(_PROJECT_ROOT / "subagents" / "knower"))
from worker import (
    build_claim_review_packet,
    build_myth_fact_packet,
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
        # Fallback: simple YAML parsing for our flat structure
        # This handles the key sections we need without requiring PyYAML
        return _parse_yaml_simple(config_path)


def _parse_yaml_simple(path: Path) -> dict:
    """Minimal YAML parser for inference_routing.yaml without PyYAML."""
    config = {}
    current_section = None
    current_subsection = None

    with open(path, "r") as f:
        for line in f:
            line = line.rstrip()
            # Skip comments and empty lines
            if not line or line.lstrip().startswith("#"):
                continue
            stripped = line.lstrip()
            indent = len(line) - len(stripped)

            # Key-value pairs
            if ":" in stripped and not stripped.startswith("-"):
                key, _, value = stripped.partition(":")
                key = key.strip()
                value = value.strip()

                # Remove inline comments
                if "#" in value:
                    value = value[:value.index("#")].strip()

                # Skip section headers that are just names
                if value and value not in ("null", "~", ""):
                    # Convert value types
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
                        # Top-level key
                        if key.startswith("_"):
                            config[key] = {} if not parsed else parsed
                            current_section = key
                        else:
                            config[key] = parsed
                    elif indent >= 2:
                        # Nested key
                        if current_section and current_section in config:
                            if isinstance(config[current_section], dict):
                                config[current_section][key] = parsed

                elif not value:
                    # Section/subsection header
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
    """
    Get the inference config for a specific knower domain.

    Merges defaults with domain-specific overrides.
    """
    defaults = config.get("_inference_defaults", {})
    knower = config.get("_knower", {})
    domain_cfg = knower.get(domain, {})

    # Merge: domain overrides defaults
    merged = dict(defaults)
    merged.update(domain_cfg)
    return merged


# ---------------------------------------------------------------------------
# Prompt rendering
# ---------------------------------------------------------------------------

def render_prompt(template_path: Path, task_id: str, domain: str,
                  instruction: str, input_context: dict) -> str:
    """
    Render the inference prompt template with task context.

    Uses simple string substitution ({{variable}}) rather than Jinja2
    to minimize dependencies.
    """
    if not template_path.exists():
        # Fallback: inline prompt
        return (
            f"Task ID: {task_id}\n"
            f"Domain: {domain}\n"
            f"Instruction: {instruction}\n\n"
            f"Input context:\n{json.dumps(input_context, indent=2)}\n\n"
            f"Produce structured JSON output for the {domain} domain."
        )

    template_text = template_path.read_text()

    # Prepare substitution context
    context = {
        "task_id": task_id,
        "domain": domain,
        "instruction": instruction,
        "input_context": json.dumps(input_context, indent=2) if isinstance(input_context, dict) else str(input_context),
    }

    # Simple {{variable}} substitution
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
    domain = request.get("domain", "claim_review")
    # Map domain to packet type
    domain_to_packet_type = {
        "claim_review": "knower_claim_review",
        "myth_fact": "knower_myth_fact",
    }
    packet_type = request.get("required_packet_type", "") or domain_to_packet_type.get(domain, "")
    task_id = request.get("task_id", "task-0000")
    instruction = request.get("instruction", "")
    input_context = request.get("input_context", {})

    if packet_type not in ("knower_claim_review", "knower_myth_fact"):
        # Inference not supported for this domain
        return None

    # Render prompt from template
    template_path = _PROJECT_ROOT / "subagents" / "knower" / "inference_prompt.md"
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

    # Invoke inference adapter
    result = adapter.invoke(prompt, adapter_config)

    if result.metadata.status != InferenceStatus.SUCCESS:
        # Inference failed — return None to trigger fallback
        return None

    if result.packet is None:
        # No packet produced — return None to trigger fallback
        return None

    # Extract inference output and merge into packet envelope
    inference_data = result.packet
    inference_source = inference_data.pop("_inference_source", "unknown")

    # Build packet envelope (same structure as deterministic worker)
    if packet_type == "knower_claim_review":
        packet = _build_claim_review_envelope(
            request, inference_data, result.metadata, inference_source
        )
    elif packet_type == "knower_myth_fact":
        packet = _build_myth_fact_envelope(
            request, inference_data, result.metadata, inference_source
        )
    else:
        return None

    return packet


def _build_claim_review_envelope(request: dict, inference_data: dict,
                                  metadata: InferenceMetadata,
                                  inference_source: str) -> dict:
    """
    Build a knower_claim_review packet envelope from inference output.

    Merges model-produced data into the standard packet structure.
    Adds inference-specific audit metadata.
    """
    task_id = request.get("task_id", "task-0000")
    instruction = request.get("instruction", "")
    input_context = request.get("input_context", {})
    upstream_id = input_context.get("upstream_task_id", "")

    # Use inference-produced claim_review_data if available, else construct minimal
    claim_review_data = inference_data.get("claim_review_data", {})

    # Ensure required fields exist (governance: model output cannot bypass schema)
    if "topic" not in claim_review_data or not claim_review_data["topic"]:
        claim_review_data["topic"] = input_context.get("topic", instruction[:120] if instruction else "unknown topic")

    if "claims" not in claim_review_data or not claim_review_data["claims"]:
        # Model produced no claims — this is a malformed inference output
        # Governance: we cannot fabricate claims
        claim_review_data["claims"] = [{
            "text": "Inference produced no claims — verification needed",
            "classification": "unknown",
            "confidence": 1,
            "source_quality": "unverified",
            "evidence": [],
            "unknowns": ["Model output did not produce structured claims"],
        }]

    # Enforce classification constraints (governance override check)
    valid_classifications = {"fact", "inference", "assumption", "rumor"}
    for claim in claim_review_data["claims"]:
        if claim.get("classification") not in valid_classifications:
            claim["classification"] = "unknown"
        if not isinstance(claim.get("confidence"), int) or claim.get("confidence", 0) not in {1, 2, 3, 4}:
            claim["confidence"] = 1
        if claim.get("source_quality") not in {"primary", "secondary", "tertiary", "unverified"}:
            claim["source_quality"] = "unverified"
        if "unknowns" not in claim:
            claim["unknowns"] = []

    if "operator_brief" not in claim_review_data or not claim_review_data["operator_brief"]:
        claim_review_data["operator_brief"] = (
            f"[Inference-assisted analysis] Review of {len(claim_review_data['claims'])} claim(s). "
            f"Classification assisted by model reasoning. Verify before operational decisions."
        )

    packet = {
        "packet_type": "knower_claim_review",
        "version": "1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "knower",
        "target": "overcr",
        "task_id": task_id,
        "summary": f"KnowER inference claim review for: {instruction[:100]}",
        "claim_review_data": claim_review_data,
        "audit_trail": {
            "worker_version": "0.4.1",
            "inference_mode": True,
            "inference_source": inference_source,
            "inference_attempt_id": metadata.inference_attempt_id,
            "inference_model": metadata.selected_model,
            "inference_provider": metadata.selected_provider,
            "inference_elapsed_s": metadata.elapsed_s,
            "execution_timestamp": datetime.now(timezone.utc).isoformat(),
            "sources_consulted": [
                {"reference": f"Model-assisted reasoning ({inference_source})", "reliability": "secondary"},
                {"reference": f"Provided input (claim review, {len(claim_review_data['claims'])} claims)", "reliability": "medium"},
            ],
            "methodology_notes": (
                f"Claim classification assisted by {inference_source} inference. "
                f"Model output treated as untrusted until validated through 6-level validator. "
                f"No external action needed."
            ),
        },
        "approval_required": False,
        "next_steps_recommendation": (
            "Route claim review to operator for judgment via OverCR. "
            "Inference-assisted — verify classifications before operational decisions."
        ),
    }

    if upstream_id:
        packet["upstream_task_id"] = upstream_id

    return packet


def _build_myth_fact_envelope(request: dict, inference_data: dict,
                               metadata: InferenceMetadata,
                               inference_source: str) -> dict:
    """
    Build a knower_myth_fact packet envelope from inference output.

    Merges model-produced data into the standard packet structure.
    Adds inference-specific audit metadata.
    """
    task_id = request.get("task_id", "task-0000")
    instruction = request.get("instruction", "")
    input_context = request.get("input_context", {})
    upstream_id = input_context.get("upstream_task_id", "")

    # Use inference-produced myth_fact_data if available
    myth_fact_data = inference_data.get("myth_fact_data", {})

    # Ensure required fields exist
    if "topic" not in myth_fact_data or not myth_fact_data["topic"]:
        myth_fact_data["topic"] = input_context.get("topic", instruction[:120] if instruction else "unknown topic")

    if "items" not in myth_fact_data or not myth_fact_data["items"]:
        myth_fact_data["items"] = [{
            "statement": "Inference produced no statements — verification needed",
            "classification": "unverified",
            "confidence": 1,
            "source_quality": "unverified",
            "explanation": "Model output did not produce structured items",
            "unknowns": ["Model output did not produce structured statements"],
        }]

    # Enforce classification constraints
    valid_classifications = {"myth", "fact", "partial_truth", "unverified"}
    for item in myth_fact_data["items"]:
        if item.get("classification") not in valid_classifications:
            item["classification"] = "unverified"
        if not isinstance(item.get("confidence"), int) or item.get("confidence", 0) not in {1, 2, 3, 4}:
            item["confidence"] = 1
        if item.get("source_quality") not in {"primary", "secondary", "tertiary", "unverified"}:
            item["source_quality"] = "unverified"
        if "unknowns" not in item:
            item["unknowns"] = []

    if "operator_brief" not in myth_fact_data or not myth_fact_data["operator_brief"]:
        myth_fact_data["operator_brief"] = (
            f"[Inference-assisted analysis] Analyzed {len(myth_fact_data['items'])} statement(s). "
            f"Classification assisted by model reasoning. Verify before operational decisions."
        )

    packet = {
        "packet_type": "knower_myth_fact",
        "version": "1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "knower",
        "target": "overcr",
        "task_id": task_id,
        "summary": f"KnowER inference myth/fact classification for: {instruction[:100]}",
        "myth_fact_data": myth_fact_data,
        "audit_trail": {
            "worker_version": "0.4.1",
            "inference_mode": True,
            "inference_source": inference_source,
            "inference_attempt_id": metadata.inference_attempt_id,
            "inference_model": metadata.selected_model,
            "inference_provider": metadata.selected_provider,
            "inference_elapsed_s": metadata.elapsed_s,
            "execution_timestamp": datetime.now(timezone.utc).isoformat(),
            "sources_consulted": [
                {"reference": f"Model-assisted reasoning ({inference_source})", "reliability": "secondary"},
                {"reference": f"Provided input (myth/fact, {len(myth_fact_data['items'])} statements)", "reliability": "medium"},
            ],
            "methodology_notes": (
                f"Myth/fact classification assisted by {inference_source} inference. "
                f"Model output treated as untrusted until validated through 6-level validator. "
                f"No external action needed."
            ),
        },
        "approval_required": False,
        "next_steps_recommendation": (
            "Route myth/fact results to operator for review via OverCR. "
            "Inference-assisted — verify classifications before operational decisions."
        ),
    }

    if upstream_id:
        packet["upstream_task_id"] = upstream_id

    return packet


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main():
    """
    Main entry point for KnowER inference worker.

    Flow:
      1. Read request from stdin
      2. Load inference config for the domain
      3. If inference enabled: attempt inference, validate, return
      4. If inference fails or is disabled: fall back to deterministic worker
      5. If fallback also fails: exit nonzero (task does NOT advance)
    """
    request = read_request()

    domain = request.get("domain", "claim_review")
    # Map domain to required packet type for validation check
    domain_to_packet_type = {
        "claim_review": "knower_claim_review",
        "myth_fact": "knower_myth_fact",
        "research": "knower_research",
        "analysis": "knower_assessment",
        "myth_separation": "knower_myth_separation",
    }
    packet_type = request.get("required_packet_type", "") or domain_to_packet_type.get(domain, "")

    # Only claim_review and myth_fact support inference in v0.4.1
    inference_domains = {"claim_review", "myth_fact"}

    if domain in inference_domains and packet_type in ("knower_claim_review", "knower_myth_fact"):
        # Load config and attempt inference
        try:
            config = load_inference_config()
            domain_config = get_domain_config(config, domain)
        except Exception:
            # Config load failure — fall back to deterministic
            domain_config = {"enabled": False}

        if domain_config.get("enabled", False):
            # Inference is enabled — attempt model-assisted reasoning
            adapter_type = domain_config.get("adapter", "mock")
            try:
                adapter = get_adapter(adapter_type)
            except ValueError:
                # Unknown adapter type — fall back to mock
                adapter = MockInferenceAdapter()

            # Attempt inference
            inference_packet = build_inference_packet(request, adapter, domain_config)

            if inference_packet is not None:
                # Inference succeeded — validate the packet
                # validate_packet returns (valid, errors, warnings) tuple
                valid, errors, warnings = validate_packet(inference_packet)

                if valid:
                    # Valid inference output — emit it
                    # Add inference metadata to audit trail
                    if "audit_trail" not in inference_packet:
                        inference_packet["audit_trail"] = {}
                    inference_packet["audit_trail"]["inference_used"] = True
                    inference_packet["audit_trail"]["fallback_used"] = False
                    print(json.dumps(inference_packet, indent=2))
                    return  # Exit 0 (implicit)
                else:
                    # Validation failed — governance constraint violated
                    # Log validation errors to stderr for audit
                    print(json.dumps({
                        "inference_validation_failed": True,
                        "errors": errors[:10],  # Cap error output
                        "fallback": "deterministic",
                    }), file=sys.stderr)

            # Inference failed or validation failed — fall back to deterministic
            fallback_packet = _deterministic_fallback(request, packet_type)

            if fallback_packet is not None:
                # Add fallback metadata to audit trail
                if "audit_trail" not in fallback_packet:
                    fallback_packet["audit_trail"] = {}
                fallback_packet["audit_trail"]["inference_used"] = False
                fallback_packet["audit_trail"]["fallback_used"] = True
                print(json.dumps(fallback_packet, indent=2))
                return  # Exit 0

            # Both inference and fallback failed — task does NOT advance
            print(json.dumps({
                "error": "inference_and_fallback_failed",
                "message": "Both inference and deterministic fallback failed. Task must not advance.",
            }), file=sys.stderr)
            sys.exit(1)

    # Domain not inference-enabled, or inference disabled — deterministic path
    fallback_packet = _deterministic_fallback(request, packet_type)

    if fallback_packet is not None:
        print(json.dumps(fallback_packet, indent=2))
        return  # Exit 0

    # Should never reach here, but safety exit
    print(json.dumps({
        "error": "no_packet_produced",
        "message": f"KnowER inference worker produced no packet for domain: {domain}",
    }), file=sys.stderr)
    sys.exit(1)


def _deterministic_fallback(request: dict, packet_type: str) -> Optional[dict]:
    """
    Fall back to the deterministic KnowER worker functions.

    This ensures that if inference fails, the task can still be processed
    by the template-based worker (v0.4.0 behavior).
    """
    try:
        if packet_type == "knower_claim_review":
            return build_claim_review_packet(request)
        elif packet_type == "knower_myth_fact":
            return build_myth_fact_packet(request)
        else:
            return None
    except Exception as e:
        print(json.dumps({
            "error": "deterministic_fallback_failed",
            "message": f"KnowER deterministic fallback error: {type(e).__name__}: {str(e)[:200]}",
        }), file=sys.stderr)
        return None


if __name__ == "__main__":
    main()