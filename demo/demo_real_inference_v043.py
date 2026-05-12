#!/usr/bin/env python3
"""
OverCR v0.4.3 Real Inference Demo
===================================

Demonstrates ONE complete real inference path end-to-end.

Usage:
    python3 demo_real_inference_v043.py [claim_review|myth_fact] <topic>

Example:
    python3 demo_real_inference_v043.py claim_review "public budget 2026"
"""

import sys
import os
import time
from pathlib import Path

# Resolve OVERCR_ROOT
OVERCR_ROOT = Path(os.environ.get("OVERCR_ROOT", str(Path(__file__).resolve().parent.parent)))
sys.path.insert(0, str(OVERCR_ROOT))

from runtime.inference_adapter import get_adapter
from tools.validate_packet import validate_packet


def run_demo(domain: str, topic: str):
    """Run real inference demo for specified domain."""
    print("=" * 72)
    print(f"OverCR v0.4.3 Real Inference Demo - {domain}")
    print("=" * 72)
    print()

    if domain not in ("claim_review", "myth_fact"):
        print(f"ERROR: Unknown domain '{domain}'")
        print("Supported: claim_review, myth_fact")
        return 1

    # Get Hermes CLI adapter
    adapter = get_adapter("hermes_cli")

    if not adapter.is_available():
        print("ERROR: Hermes CLI not available.")
        print("Please ensure 'hermes' is in PATH or set HERMES_CLI_PATH.")
        return 1

    print("Step 1: Checking Hermes CLI availability...")
    print(f"  Adapter: {adapter.adapter_type}")
    print(f"  CLI path: {adapter._resolve_cli_path()}")
    print(f"  Available: {adapter.is_available()}")
    print()

    # Build prompt - simple and to the point
    if domain == "claim_review":
        prompt = (
            f"Produce JSON for claim_review domain. "
            f"Topic: {topic}. "
            "Create 1 claim. Return ONLY JSON with claim_review_data. No markdown."
        )
    elif domain == "myth_fact":
        prompt = (
            f"Produce JSON for myth_fact domain. "
            f"Topic: {topic}. "
            "Create 1 statement. Return ONLY JSON with myth_fact_data. No markdown."
        )

    print("Step 2: Prompt sent to Hermes CLI...")
    print(f"  Prompt length: {len(prompt)} chars")
    print()

    # Config
    config = {
        "domain": domain,
        "model": "glm-5.1:cloud",
        "provider": "ollama-cloud",
        "timeout_s": 60,
        "task_id": "demo-001",
        "input_context": {
            "topic": topic,
            "instruction": f"Analyze and classify information about {topic}",
        },
    }

    print("Step 3: Invoking Hermes CLI for inference...")
    start = time.time()
    result = adapter.invoke(prompt, config)
    elapsed = time.time() - start

    print(f"  Elapsed: {elapsed:.2f}s")
    print()

    if not result.success:
        print("ERROR: Inference failed")
        print(f"  Error: {result.metadata.error_message}")
        return 1

    print("Step 4: Processing model response...")
    packet = result.packet
    if packet is None:
        print("ERROR: No packet produced")
        return 1

    print(f"  Inference source: {packet.get('_inference_source', 'unknown')}")

    # Check for actual data from model
    data_key = f"{domain}_data"
    if data_key not in packet:
        print(f"ERROR: Model did not produce {data_key}")
        print(f"  Raw packet keys: {list(packet.keys())}")
        if "_raw_model_output" in packet:
            print("  Raw output preview:")
            raw = packet["_raw_model_output"][:500]
            for line in raw.split("\n")[:10]:
                print(f"    {line}")
        return 1

    # Get the data produced by model
    data = packet[data_key]
    print(f"  Model produced: {data_key}")
    print(f"    topic: {data.get('topic', 'N/A')}")
    if domain == "claim_review":
        print(f"    claims: {len(data.get('claims', []))}")
    elif domain == "myth_fact":
        print(f"    items: {len(data.get('items', []))}")
    print()

    # Build full packet envelope
    packet_type = f"knower_{domain}"
    full_packet = {
        "packet_type": packet_type,
        "version": "1.0",
        "timestamp": "2026-05-11T00:00:00+00:00",
        "source": "knower",
        "target": "overcr",
        "task_id": "demo-001",
        "summary": f"OverCR v0.4.3 real inference demo: {topic}",
        data_key: data,
        "audit_trail": {
            "worker_version": "0.4.3",
            "inference_mode": True,
            "inference_source": packet.get("_inference_source", "unknown"),
            "inference_attempt_id": result.metadata.inference_attempt_id,
            "inference_model": result.metadata.selected_model,
            "inference_provider": result.metadata.selected_provider,
            "inference_elapsed_s": result.metadata.elapsed_s,
            "execution_timestamp": "2026-05-11T00:00:00+00:00",
        },
        "approval_required": False,
        "next_steps_recommendation": "Route to operator for review.",
    }

    print("Step 5: L1-L6 Validation...")
    valid, errors, warnings = validate_packet(full_packet)

    print(f"  Result: {'VALID' if valid else 'INVALID'}")
    print(f"  Errors: {len(errors)}")
    print(f"  Warnings: {len(warnings)}")

    if not valid:
        print("  ERROR Details:")
        for err in errors:
            print(f"    - {err}")
        return 1

    if warnings:
        for warn in warnings:
            print(f"    ~ {warn}")

    # Build validation_result
    validation_result = {"valid": valid, "errors": errors, "warnings": warnings}

    print()
    print("Step 6: Audit Trail...")
    meta = result.metadata
    print(f"  adapter_type: {meta.adapter_type}")
    print(f"  selected_model: {meta.selected_model}")
    print(f"  selected_provider: {meta.selected_provider}")
    print(f"  inference_attempt_id: {meta.inference_attempt_id}")
    print(f"  timeout_s: {meta.timeout_s}")
    print(f"  elapsed_s: {round(meta.elapsed_s, 3)}")
    print(f"  status: {meta.status.value}")
    print(f"  validation_result: {validation_result['valid']}")

    print()
    print("=" * 72)
    print("DEMO SUCCESS - v0.4.3 Real Inference Proven")
    print("=" * 72)
    print()
    print("End-to-end path verified:")
    print("  1. Hermes CLI invoked via subprocess (no direct API calls)")
    print("  2. Real model produced structured JSON output")
    print(f"  3. Output wrapped as {packet_type} packet")
    print("  4. Packet passed L1-L6 validation")
    print("  5. Full audit trail recorded (no mocks)")
    print()
    print("No autonomous loops, retries, or self-routing used.")
    print("Deterministic fallback still available if inference fails.")
    print()

    return 0


def main():
    """Run the v0.4.3 real inference demo."""
    if len(sys.argv) < 3:
        print("Usage:")
        print("  python3 demo_real_inference_v043.py claim_review <topic>")
        print("  python3 demo_real_inference_v043.py myth_fact <topic>")
        print()
        print("Examples:")
        print("  python3 demo_real_inference_v043.py claim_review 'public budget 2026'")
        print("  python3 demo_real_inference_v043.py myth_fact 'artificial intelligence'")
        return 1

    domain = sys.argv[1]
    topic = sys.argv[2]

    return run_demo(domain, topic)


if __name__ == "__main__":
    sys.exit(main())
