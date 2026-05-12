#!/usr/bin/env python3
"""
OverCR v0.4.2 Demo: HermesCLIAdapter Live Inference
====================================================

This demo shows the HermesCLIAdapter making a real inference call through
the Hermes CLI runtime, using live provider routing (no hardcoded API keys).

Usage:
    python3 demo_hermes_cli_adapter.py [claim_review|myth_fact] <topic>
"""

import sys
import os
from pathlib import Path

# Resolve OVERCR_ROOT
OVERCR_ROOT = Path(os.environ.get("OVERCR_ROOT", str(Path(__file__).resolve().parent.parent)))
sys.path.insert(0, str(OVERCR_ROOT))

from runtime.inference_adapter import get_adapter


def demo_claim_review(topic: str):
    """Demo claim_review domain using HermesCLIAdapter."""
    print("=" * 72)
    print("OverCR v0.4.2 — Claim Review Demo (HermesCLIAdapter)")
    print("=" * 72)
    print()
    print(f"Domain: claim_review")
    print(f"Topic: {topic}")
    print()
    
    # Get adapter (will use Hermes CLI as configured in environment)
    adapter = get_adapter("hermes_cli")
    
    if not adapter.is_available():
        print("ERROR: Hermes CLI not available.")
        print("Please ensure 'hermes' is in PATH or set HERMES_CLI_PATH.")
        return 1
    
    # Build the inference prompt (simplified for demo)
    prompt = f"""Claim review task.

Topic: {topic}

Please analyze statements about this topic and classify each as fact, inference, assumption, or rumor.
Return a JSON object with:
  claim_review_data: {{
    topic: "<topic>",
    claims: [{{ text: "<statement>", classification: "<type>", confidence: <1-4>, source_quality: "<primary|secondary|tertiary|unverified>" }}],
    operator_brief: "<brief summary>"
  }}

Confidence scale: 1=speculative, 2=moderate, 3=strong, 4=definitive
Source quality: primary (direct evidence), secondary (reported), tertiary (secondary-sourced), unverified (unsourceable)
"""
    
    print("Prompt (first 200 chars):")
    print("  " + prompt[:200].replace("\n", " ") + "...")
    print()
    
    config = {
        "domain": "claim_review",
        "model": "glm-5.1:cloud",
        "provider": "ollama-cloud",
        "timeout_s": 30,
        "task_id": "task-demo-claim-001",
        "input_context": {
            "entity": topic,
            "topic": topic,
            "claims_to_review": [f"Statement about {topic}"],
        },
    }
    
    import time
    start = time.time()
    
    print("Calling Hermes CLI for inference...")
    print(f"  Model: {config['model']}")
    print(f"  Provider: {config['provider']}")
    print()
    
    result = adapter.invoke(prompt, config)
    elapsed = time.time() - start
    
    print(f"Returned in {elapsed:.2f}s")
    print(f"Success: {result.success}")
    print(f"Used fallback: {result.used_fallback}")
    print()
    
    if result.success and result.packet:
        print("Inference Result:")
        print("-" * 40)
        packet = result.packet
        
        # Draw inference source marker
        source = packet.get("_inference_source", "unknown")
        print(f"  _inference_source: {source}")
        
        # Show claim_review_data if present
        if "claim_review_data" in packet:
            cr_data = packet["claim_review_data"]
            print()
            print("  claim_review_data:")
            print(f"    topic: {cr_data.get('topic', 'N/A')}")
            print(f"    operator_brief: {cr_data.get('operator_brief', 'N/A')[:100]}...")
            
            claims = cr_data.get("claims", [])
            print(f"    claims: {len(claims)} item(s)")
            for i, claim in enumerate(claims[:3], 1):  # Show first 3
                print(f"      {i}. {claim.get('text', 'N/A')[:60]}")
                print(f"         classification: {claim.get('classification', 'N/A')}")
                print(f"         confidence: {claim.get('confidence', 'N/A')}")
                print(f"         source_quality: {claim.get('source_quality', 'N/A')}")
            if len(claims) > 3:
                print(f"      ... and {len(claims) - 3} more")
        
        # Show audit trail metadata
        print()
        print("Audit Trail Metadata:")
        print("-" * 40)
        meta = result.metadata
        print(f"  adapter_type: {meta.adapter_type}")
        print(f"  inference_attempt_id: {meta.inference_attempt_id}")
        print(f"  selected_model: {meta.selected_model}")
        print(f"  selected_provider: {meta.selected_provider}")
        print(f"  elapsed_s: {round(meta.elapsed_s, 3)}")
    else:
        print("ERROR: No packet produced.")
        if result.metadata:
            print(f"  Error: {result.metadata.error_message[:200]}")
    
    print()
    print("=" * 72)
    print("Demo Complete")
    print("=" * 72)
    
    return 0


def demo_myth_fact(topic: str):
    """Demo myth_fact domain using HermesCLIAdapter."""
    print("=" * 72)
    print("OverCR v0.4.2 — Myth/Fact Demo (HermesCLIAdapter)")
    print("=" * 72)
    print()
    print(f"Domain: myth_fact")
    print(f"Topic: {topic}")
    print()
    
    adapter = get_adapter("hermes_cli")
    
    if not adapter.is_available():
        print("ERROR: Hermes CLI not available.")
        return 1
    
    prompt = f"""Myth/fact analysis task.

Topic: {topic}

Please analyze statements and classify each as myth, fact, partial_truth, or unverified.
Return a JSON object with:
  myth_fact_data: {{
    topic: "<topic>",
    items: [{{ statement: "<statement>", classification: "<type>", confidence: <1-4>, source_quality: "<primary|secondary|tertiary|unverified>", explanation: "<reasoning>" }}],
    operator_brief: "<brief summary>"
  }}

Confidence scale: 1=speculative, 2=moderate, 3=strong, 4=definitive
Source quality: primary (direct evidence), secondary (reported), tertiary (secondary-sourced), unverified (unsourceable)
"""
    
    print("Prompt (first 200 chars):")
    print("  " + prompt[:200].replace("\n", " ") + "...")
    print()
    
    config = {
        "domain": "myth_fact",
        "model": "glm-5.1:cloud",
        "provider": "ollama-cloud",
        "timeout_s": 30,
        "task_id": "task-demo-myth-001",
        "input_context": {
            "entity": topic,
            "topic": topic,
            "statements": [f"Statement about {topic}"],
        },
    }
    
    import time
    start = time.time()
    
    print("Calling Hermes CLI for inference...")
    print(f"  Model: {config['model']}")
    print(f"  Provider: {config['provider']}")
    print()
    
    result = adapter.invoke(prompt, config)
    elapsed = time.time() - start
    
    print(f"Returned in {elapsed:.2f}s")
    print(f"Success: {result.success}")
    print()
    
    if result.success and result.packet:
        print("Inference Result:")
        print("-" * 40)
        packet = result.packet
        source = packet.get("_inference_source", "unknown")
        print(f"  _inference_source: {source}")
        
        if "myth_fact_data" in packet:
            mf_data = packet["myth_fact_data"]
            print()
            print("  myth_fact_data:")
            print(f"    topic: {mf_data.get('topic', 'N/A')}")
            print(f"    operator_brief: {mf_data.get('operator_brief', 'N/A')[:100]}...")
            
            items = mf_data.get("items", [])
            print(f"    items: {len(items)} item(s)")
            for i, item in enumerate(items[:3], 1):
                print(f"      {i}. {item.get('statement', 'N/A')[:60]}")
                print(f"         classification: {item.get('classification', 'N/A')}")
                print(f"         confidence: {item.get('confidence', 'N/A')}")
                print(f"         source_quality: {item.get('source_quality', 'N/A')}")
            if len(items) > 3:
                print(f"      ... and {len(items) - 3} more")
        
        print()
        print("Audit Trail Metadata:")
        print("-" * 40)
        meta = result.metadata
        print(f"  adapter_type: {meta.adapter_type}")
        print(f"  inference_attempt_id: {meta.inference_attempt_id}")
    else:
        print("ERROR: No packet produced.")
        if result.metadata:
            print(f"  Error: {result.metadata.error_message[:200]}")
    
    print()
    print("=" * 72)
    print("Demo Complete")
    print("=" * 72)
    
    return 0


def main():
    """Run the appropriate demo based on command line args."""
    if len(sys.argv) < 3:
        print("Usage:")
        print("  python3 demo_hermes_cli_adapter.py claim_review <topic>")
        print("  python3 demo_hermes_cli_adapter.py myth_fact <topic>")
        print()
        print("Examples:")
        print("  python3 demo_hermes_cli_adapter.py claim_review \"public budget 2026\"")
        print("  python3 demo_hermes_cli_adapter.py myth_fact \"artificial intelligence myths\"")
        return 1
    
    domain = sys.argv[1]
    topic = sys.argv[2]
    
    if domain == "claim_review":
        return demo_claim_review(topic)
    elif domain == "myth_fact":
        return demo_myth_fact(topic)
    else:
        print(f"ERROR: Unknown domain '{domain}'")
        print("Supported: claim_review, myth_fact")
        return 1


if __name__ == "__main__":
    sys.exit(main())
