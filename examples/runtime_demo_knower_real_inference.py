#!/usr/bin/env python3
"""
OverCR v0.4.2 — KnowER Real Inference Demo
=============================================

Demonstrates the HermesCLIAdapter making a real provider-backed model call
for KnowER claim review, with full governance enforcement.

This demo:
  1. Loads inference routing config
  2. Creates a HermesCLIAdapter
  3. Checks adapter availability (dry_run)
  4. If available: makes a real model call for a claim review prompt
  5. Validates the output through 6-level validator
  6. Falls back to deterministic worker if adapter unavailable
  7. Produces a typed KnowER packet with audit trail

Governance guarantees:
  - No direct subagent routing allowed
  - No browsing claims allowed
  - No governance overrides allowed
  - On failure, task does not advance
  - All inference metadata recorded in audit trail

Usage:
  python3 examples/runtime_demo_knower_real_inference.py
  HERMES_CLI_PATH=/path/to/hermes python3 examples/runtime_demo_knower_real_inference.py
"""

import json
import sys
import os
from pathlib import Path

# Bootstrap project root
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from runtime.inference_result import (
    InferenceResult,
    InferenceStatus,
    make_inference_attempt_id,
)
from runtime.hermes_inference_adapter import HermesCLIAdapter, get_cli_adapter
from runtime.inference_adapter import get_adapter, MockInferenceAdapter


def load_routing_config() -> dict:
    """Load inference routing configuration."""
    config_path = ROOT / "config" / "inference_routing.yaml"
    if not config_path.exists():
        print(f"[WARN] Config not found: {config_path}")
        return {}

    try:
        import yaml
        with open(config_path, "r") as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        # Fallback: parse manually or skip
        print("[WARN] PyYAML not available, using defaults")
        return {}


def render_prompt(template_path: str, variables: dict) -> str:
    """Render a prompt template with variable substitution."""
    full_path = ROOT / template_path
    if not full_path.exists():
        print(f"[WARN] Template not found: {full_path}")
        return ""

    with open(full_path, "r") as f:
        content = f.read()

    for key, value in variables.items():
        placeholder = "{{" + key + "}}"
        content = content.replace(placeholder, str(value))

    return content


def validate_with_l5_l6(packet: dict) -> tuple:
    """
    Validate inference output through L5 and L6 checks.
    Returns (valid, errors, warnings) tuple.
    """
    import importlib.util

    validate_path = ROOT / "tools" / "validate_packet.py"
    spec = importlib.util.spec_from_file_location("validate_packet", str(validate_path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    result = mod.validate_packet(packet)
    if isinstance(result, tuple):
        return result
    # Backward compat: result could be a dict-like
    return (result.valid if hasattr(result, "valid") else False,
            result.errors if hasattr(result, "errors") else [],
            result.warnings if hasattr(result, "warnings") else [])


def run_demo():
    """Run the KnowER real inference demo."""
    print("=" * 70)
    print("OverCR v0.4.2 — KnowER Real Inference Demo")
    print("=" * 70)

    # 1. Load config
    config = load_routing_config()
    knower_config = config.get("_knower", {})
    claim_review_cfg = knower_config.get("claim_review", {})
    defaults = config.get("_inference_defaults", {})
    production_cfg = defaults.get("production", {})

    print(f"\n[CONFIG] Domain: claim_review")
    print(f"[CONFIG] Adapter (default): {claim_review_cfg.get('adapter', 'mock')}")
    print(f"[CONFIG] Model: {claim_review_cfg.get('model', 'glm-5.1:cloud')}")
    print(f"[CONFIG] Provider: {claim_review_cfg.get('provider', 'ollama-cloud')}")
    print(f"[CONFIG] Production adapter: {production_cfg.get('adapter', 'hermes_cli')}")

    # 2. Create adapters
    mock_adapter = MockInferenceAdapter()
    cli_adapter = get_cli_adapter(
        model=claim_review_cfg.get("model", "glm-5.1:cloud"),
        provider=claim_review_cfg.get("provider", "ollama-cloud"),
        timeout_s=claim_review_cfg.get("timeout_s", 45),
    )

    # 3. Check real adapter availability
    print(f"\n[AVAIL] MockInferenceAdapter: available={mock_adapter.is_available()}")
    dry_run = cli_adapter.dry_run(config=claim_review_cfg)
    print(f"[AVAIL] HermesCLIAdapter: available={dry_run['available']}")
    print(f"[AVAIL] HermesCLIAdapter: cli_path={dry_run['cli_path']}")
    print(f"[AVAIL] HermesCLIAdapter: model={dry_run['model']}")
    print(f"[AVAIL] HermesCLIAdapter: provider={dry_run['provider']}")
    if dry_run.get("error"):
        print(f"[AVAIL] HermesCLIAdapter: error={dry_run['error']}")

    # 4. Render prompt
    task_id = "task-0042"
    domain = "claim_review"
    prompt_vars = {
        "task_id": task_id,
        "domain": domain,
        "instruction": "Review the following claim and classify it as fact, inference, assumption, or rumor. Provide a confidence level (1-4) and assess source quality.",
        "input_context": "Claim: 'Endicott, NY has a population of approximately 13,000 residents as of the 2020 census.' This appears to be a factual demographic claim from census data.",
    }

    prompt = render_prompt(
        claim_review_cfg.get("prompt_template", "subagents/knower/inference_prompt.md"),
        prompt_vars,
    )

    if not prompt:
        print("[ERROR] Failed to render prompt")
        return False

    print(f"\n[PROMPT] Length: {len(prompt)} chars")
    print(f"[PROMPT] First 100 chars: {prompt[:100]}...")

    # 5. Attempt real inference if available
    real_result = None
    real_packet = None
    used_real = False

    if cli_adapter.is_available():
        print(f"\n[REAL] Attempting real provider-backed inference via Hermes CLI...")

        invoke_config = {
            "domain": domain,
            "task_id": task_id,
            "model": claim_review_cfg.get("model", "glm-5.1:cloud"),
            "provider": claim_review_cfg.get("provider", "ollama-cloud"),
            "timeout_s": claim_review_cfg.get("timeout_s", 45),
            "input_context": prompt_vars["input_context"],
        }

        real_result = cli_adapter.invoke(prompt, invoke_config)

        print(f"[REAL] Status: {real_result.metadata.status.value}")
        print(f"[REAL] Adapter: {real_result.metadata.adapter_type}")
        print(f"[REAL] Model: {real_result.metadata.selected_model}")
        print(f"[REAL] Provider: {real_result.metadata.selected_provider}")
        print(f"[REAL] Attempt ID: {real_result.metadata.inference_attempt_id}")
        print(f"[REAL] Elapsed: {real_result.metadata.elapsed_s:.2f}s")
        print(f"[REAL] Prompt hash: {real_result.metadata.prompt_hash}")

        if real_result.metadata.status == InferenceStatus.SUCCESS:
            real_packet = real_result.packet
            used_real = True
            print(f"[REAL] Packet keys: {list(real_packet.keys()) if real_packet else 'None'}")
            if real_packet and "_raw_model_output" in real_packet:
                print(f"[REAL] Raw output (first 200 chars): {real_packet['_raw_model_output'][:200]}...")
            elif real_packet:
                print(f"[REAL] Structured output received")
        else:
            print(f"[REAL] Inference failed: {real_result.metadata.error_message}")
            print(f"[REAL] Will fall back to deterministic worker")

    # 6. Fall back to mock if real unavailable or failed
    if not used_real:
        print(f"\n[FALLBACK] Using MockInferenceAdapter (simulated)...")
        invoke_config = {
            "domain": domain,
            "task_id": task_id,
            "model": claim_review_cfg.get("model", "glm-5.1:cloud"),
            "provider": claim_review_cfg.get("provider", "ollama-cloud"),
            "timeout_s": claim_review_cfg.get("timeout_s", 45),
            "input_context": prompt_vars["input_context"],
        }

        mock_result = mock_adapter.invoke(prompt, invoke_config)

        if mock_result.metadata.status == InferenceStatus.SUCCESS:
            # For mock, create a proper KnowER packet
            real_packet = {
                "packet_type": "knower_claim_review",
                "version": "0.4.2",
                "task_id": task_id,
                "domain": domain,
                "subagent": "knower",
                "timestamp": "2025-01-15T12:00:00Z",
                "claim": prompt_vars["input_context"],
                "classification": "fact",
                "confidence": 3,
                "source_quality": "primary",
                "reasoning": "Census data is a primary source for demographic claims. The classification as fact is supported by the availability of official US Census Bureau records.",
                "submit_to": "OverCR for routing",
                "governance": {
                    "doctrine_compliant": True,
                    "approval_gate_passed": True,
                    "browsing_claim": False,
                    "direct_routing": False,
                },
                "_inference_source": "mock",
                "_inference_metadata": {
                    "attempt_id": mock_result.metadata.inference_attempt_id,
                    "adapter_type": mock_result.metadata.adapter_type,
                    "model": "mock",
                    "elapsed_s": mock_result.metadata.elapsed_s,
                    "fallback_used": not used_real,
                },
            }
            real_result = mock_result
        else:
            print(f"[FALLBACK] Mock adapter also failed: {mock_result.metadata.error_message}")
            return False

    # 7. Validate the packet
    print(f"\n[VALIDATE] Running 6-level validation on output packet...")
    valid, errors, warnings = validate_with_l5_l6(real_packet)

    print(f"[VALIDATE] Valid: {valid}")
    print(f"[VALIDATE] Errors: {len(errors)}")
    for e in errors[:5]:
        print(f"  - {e}")
    if len(errors) > 5:
        print(f"  ... and {len(errors) - 5} more")
    print(f"[VALIDATE] Warnings: {len(warnings)}")
    for w in warnings[:3]:
        print(f"  - {w}")

    # 8. Build final response with audit trail
    audit_trail = {
        "inference_used": used_real,
        "adapter_type": real_result.metadata.adapter_type,
        "selected_model": real_result.metadata.selected_model,
        "selected_provider": real_result.metadata.selected_provider,
        "attempt_id": real_result.metadata.inference_attempt_id,
        "prompt_hash": real_result.metadata.prompt_hash,
        "elapsed_s": real_result.metadata.elapsed_s,
        "fallback_used": real_result.metadata.fallback_used or not used_real,
        "validation_passed": valid,
        "validation_errors": errors,
        "validation_warnings": warnings,
    }

    if real_result.metadata.error_message:
        audit_trail["error_message"] = real_result.metadata.error_message

    response = {
        "packet": real_packet,
        "audit_trail": audit_trail,
    }

    print(f"\n[AUDIT] Full audit trail:")
    for k, v in audit_trail.items():
        if isinstance(v, list):
            print(f"  {k}: [{len(v)} items]")
        else:
            print(f"  {k}: {v}")

    # 9. Summary
    print(f"\n{'=' * 70}")
    print(f"DEMO RESULT: {'PASS' if valid else 'FAIL'}")
    print(f"  Inference source: {'REAL (hermes_cli)' if used_real else 'MOCK (simulated)'}")
    print(f"  Validation: {'PASSED' if valid else 'FAILED'}")
    print(f"  Errors: {len(errors)}")
    print(f"  Warnings: {len(warnings)}")
    print(f"  Packet type: {real_packet.get('packet_type', 'unknown') if real_packet else 'N/A'}")
    print(f"{'=' * 70}")

    return valid


if __name__ == "__main__":
    success = run_demo()
    sys.exit(0 if success else 1)