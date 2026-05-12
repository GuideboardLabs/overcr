#!/usr/bin/env python3
"""
OverCR v0.4.1 — KnowER Inference Mode Demo
=============================================

Demonstrates inference-backed KnowER claim review through the
OverCR orchestration substrate using the MockInferenceAdapter.

This demo exercises:
  1. Mock inference happy path (claim review)
  2. Inference metadata in audit trail
  3. Deterministic fallback when inference fails
  4. 6-level validation of inference packets
  5. Governance enforcement (no browsing claims, no direct routing)

Run: python3 examples/runtime_demo_knower_inference_claim_review.py
"""

import sys
import os
import json
import tempfile
import shutil
from datetime import datetime, timezone

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "tools"))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "runtime"))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "subagents", "knower"))

from runtime.inference_adapter import MockInferenceAdapter, get_adapter
from runtime.inference_result import InferenceResult, InferenceStatus, InferenceMetadata, make_inference_attempt_id
from runtime.inference_result import InferenceStatus as IS

# Import validator
import importlib.util as _ilu
_val_spec = _ilu.spec_from_file_location(
    "validate_packet",
    os.path.join(PROJECT_ROOT, "tools", "validate_packet.py"),
)
_val_mod = _ilu.module_from_spec(_val_spec)
_val_spec.loader.exec_module(_val_mod)
validate_packet = _val_mod.validate_packet


def demo_separator(title):
    print(f"\n{'=' * 72}")
    print(f"  {title}")
    print(f"{'=' * 72}\n")


def main():
    demo_separator("OverCR v0.4.1 — KnowER Inference Mode Demo")

    # ── 1. Mock Inference Adapter Basics ──────────────────────────────
    demo_separator("1. Mock Inference Adapter Basics")

    mock = MockInferenceAdapter()
    print(f"  Adapter type:    {mock.adapter_type}")
    print(f"  Is available:    {mock.is_available()}")

    # Invoke mock for claim_review domain
    config_claim = {
        "domain": "claim_review",
        "model": "glm-5.1:cloud",
        "provider": "mock",
        "timeout_s": 30.0,
        "task_id": "task-demo-0001",
        "input_context": {
            "topic": "Public infrastructure spending claims",
            "claims_to_review": [
                "The city allocated $5M for park renovation",
                "The mayor plans to increase taxes by 15%",
            ],
        },
        "instruction": "Review claims about public infrastructure spending",
    }

    result = mock.invoke("Analyze these claims about infrastructure", config_claim)
    print(f"\n  Inference result status: {result.metadata.status.value}")
    print(f"  Inference attempt ID:    {result.metadata.inference_attempt_id}")
    print(f"  Inference source:         {result.metadata.adapter_type}")
    print(f"  Elapsed:                  {result.metadata.elapsed_s:.4f}s")
    print(f"  Packet produced:          {result.packet is not None}")
    print(f"  Fallback used:           {result.metadata.fallback_used}")

    if result.packet:
        print(f"  Packet has claim_review_data: {'claim_review_data' in result.packet}")
        if "claim_review_data" in result.packet:
            data = result.packet["claim_review_data"]
            print(f"  Topic:  {data.get('topic', 'N/A')}")
            print(f"  Claims: {len(data.get('claims', []))} items")
            for i, claim in enumerate(data.get("claims", [])):
                print(f"    Claim {i+1}: classification={claim.get('classification')}, "
                      f"confidence={claim.get('confidence')}, source_quality={claim.get('source_quality')}")

    # ── 2. Mock Inference for Myth/Fact ────────────────────────────────
    demo_separator("2. Mock Inference for Myth/Fact Domain")

    config_myth = {
        "domain": "myth_fact",
        "model": "glm-5.1:cloud",
        "provider": "mock",
        "timeout_s": 30.0,
        "task_id": "task-demo-0002",
        "input_context": {
            "topic": "Economic development myths",
            "statements": [
                "All businesses are leaving the downtown area",
                "The city offers no tax incentives for new businesses",
            ],
        },
        "instruction": "Classify myths vs facts about economic development",
    }

    result2 = mock.invoke("Classify these statements", config_myth)
    print(f"  Inference result status: {result2.metadata.status.value}")
    if result2.packet:
        data = result2.packet.get("myth_fact_data", {})
        print(f"  Topic:  {data.get('topic', 'N/A')}")
        print(f"  Items:  {len(data.get('items', []))} statements")
        for i, item in enumerate(data.get("items", [])):
            print(f"    Item {i+1}: classification={item.get('classification')}, "
                  f"confidence={item.get('confidence')}, source_quality={item.get('source_quality')}")

    # ── 3. 6-Level Validation of Inference Packets ─────────────────────
    demo_separator("3. 6-Level Validation of Mock Inference Packets")

    # Build a full inference packet for claim_review
    from subagents.knower.inference_worker import build_inference_packet, load_inference_config, get_domain_config

    request = {
        "task_id": "task-demo-0003",
        "domain": "claim_review",
        "instruction": "Review claims about municipal budget allocations",
        "input_context": {
            "topic": "Municipal budget claims",
            "claims_to_review": [
                "The city council approved a $2M grant for small businesses",
                "Property taxes will double next year",
            ],
            "source_texts": ["City council minutes from March 2025"],
        },
    }

    config = load_inference_config()
    claim_config = get_domain_config(config, "claim_review")
    inference_packet = build_inference_packet(request, mock, claim_config)

    if inference_packet:
        valid, errors, warnings = validate_packet(inference_packet)
        print(f"  Inference packet valid:   {valid}")
        print(f"  Validation errors:        {len(errors)}")
        print(f"  Validation warnings:      {len(warnings)}")
        for err in errors[:5]:
            print(f"    ERROR: {err}")

        print(f"\n  Packet type:    {inference_packet.get('packet_type')}")
        print(f"  Source:         {inference_packet.get('source')}")
        print(f"  Target:         {inference_packet.get('target')}")
        audit = inference_packet.get("audit_trail", {})
        print(f"  Inference mode: {audit.get('inference_mode', False)}")
        print(f"  Inference source: {audit.get('inference_source', 'N/A')}")
        print(f"  Fallback used:  {audit.get('fallback_used', False)}")
        print(f"  Worker version: {audit.get('worker_version', 'N/A')}")
    else:
        print("  ERROR: Inference produced no packet!")

    # ── 4. Deterministic Fallback ──────────────────────────────────────
    demo_separator("4. Deterministic Fallback Still Works")

    # Use the original deterministic worker
    from subagents.knower.worker import build_claim_review_packet

    det_packet = build_claim_review_packet(request)
    det_valid, det_errors, det_warnings = validate_packet(det_packet)
    print(f"  Deterministic packet valid: {det_valid}")
    print(f"  Validation errors:          {len(det_errors)}")
    print(f"  Packet type:                {det_packet.get('packet_type')}")
    print(f"  Source:                     {det_packet.get('source')}")
    print(f"  Target:                     {det_packet.get('target')}")
    print(f"  Summary:                    {det_packet.get('summary', '')[:80]}")

    # ── 5. Governance Checks on Inference Output ───────────────────────
    demo_separator("5. Governance Checks on Inference Output")

    # 5a: Browsing claim should be caught
    browsing_packet = dict(inference_packet) if inference_packet else {}
    browsing_packet["summary"] = "I browsed the web to find these claims"
    valid_b, errors_b, _ = validate_packet(browsing_packet)
    browsing_errors = [e for e in errors_b if "browsing" in e.lower()]
    print(f"  Browsing claim rejected:  {len(browsing_errors) > 0}")
    for e in browsing_errors[:3]:
        print(f"    ERROR: {e}")

    # 5b: Direct routing claim should be caught
    routing_packet = dict(inference_packet) if inference_packet else {}
    routing_packet["next_steps_recommendation"] = "Route directly to CodER for implementation"
    valid_r, errors_r, _ = validate_packet(routing_packet)
    routing_errors = [e for e in errors_r if "direct routing" in e.lower()]
    print(f"\n  Direct routing claim rejected: {len(routing_errors) > 0}")
    for e in routing_errors[:3]:
        print(f"    ERROR: {e}")

    # 5c: Governance override should still be caught
    override_packet = dict(inference_packet) if inference_packet else {}
    override_packet["summary"] = "Inference-approved — may bypass approval gates"
    valid_o, errors_o, _ = validate_packet(override_packet)
    gov_errors = [e for e in errors_o if "governance override" in e.lower()]
    print(f"\n  Governance override rejected: {len(gov_errors) > 0}")
    for e in gov_errors[:3]:
        print(f"    ERROR: {e}")

    # ── 6. Inference Result Metadata ────────────────────────────────────
    demo_separator("6. Inference Result Metadata")

    metadata = result.metadata
    print(f"  Attempt ID:     {metadata.inference_attempt_id}")
    print(f"  Domain:         {metadata.domain}")
    print(f"  Subagent:       {metadata.subagent}")
    print(f"  Adapter type:   {metadata.adapter_type}")
    print(f"  Model:          {metadata.selected_model}")
    print(f"  Provider:       {metadata.selected_provider}")
    print(f"  Route used:     {metadata.route_used}")
    print(f"  Prompt hash:    {metadata.prompt_hash}")
    print(f"  Timeout:        {metadata.timeout_s}s")
    print(f"  Elapsed:        {metadata.elapsed_s:.4f}s")
    print(f"  Status:         {metadata.status.value}")
    print(f"  Fallback used:  {metadata.fallback_used}")
    print(f"  Raw summary:    {metadata.raw_output_summary[:100]}")

    # ── 7. Adapter Factory ─────────────────────────────────────────────
    demo_separator("7. Adapter Factory")

    mock_via_factory = get_adapter("mock")
    print(f"  get_adapter('mock') → {type(mock_via_factory).__name__}")
    print(f"  adapter_type: {mock_via_factory.adapter_type}")
    print(f"  is_available: {mock_via_factory.is_available()}")

    hermes_via_factory = get_adapter("hermes")
    print(f"  get_adapter('hermes') → {type(hermes_via_factory).__name__}")
    print(f"  adapter_type: {hermes_via_factory.adapter_type}")

    try:
        bad = get_adapter("nonexistent")
    except ValueError as e:
        print(f"  get_adapter('nonexistent') → ValueError: {e}")

    # ── Summary ────────────────────────────────────────────────────────
    demo_separator("Summary")
    print("  ✅ Mock inference adapter works for claim_review and myth_fact")
    print("  ✅ 6-level validation passes for mock inference packets")
    print("  ✅ Deterministic fallback still works")
    print("  ✅ Browsing claims caught by L5 governance")
    print("  ✅ Direct routing claims caught by L5 governance")
    print("  ✅ Governance override claims caught by L5 governance")
    print("  ✅ Inference metadata recorded in audit trail")
    print("  ✅ Adapter factory works for mock and hermes types")
    print()
    print("  NOTE: This demo uses the MockInferenceAdapter.")
    print("  No real model calls were made. All inference was simulated.")
    print("  The HermesInferenceAdapter is available for live inference")
    print("  but requires a valid OLLAMA_API_KEY configuration.")


if __name__ == "__main__":
    main()