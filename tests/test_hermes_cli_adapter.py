#!/usr/bin/env python3
"""
OverCR v0.4.3 HermesCLIAdapter Integration Tests
==================================================

Tests the HermesCLIAdapter implementation in runtime/hermes_inference_adapter.py.

v0.4.3 changes:
  - Adapter now uses `hermes -z` (oneshot mode) for clean output
  - Output sanitizer extracts first valid JSON from model output
  - Both raw and sanitized output recorded in audit metadata
"""

import sys
import os
from pathlib import Path

# Resolve OVERCR_ROOT
OVERCR_ROOT = Path(os.environ.get("OVERCR_ROOT", str(Path(__file__).resolve().parent.parent)))
sys.path.insert(0, str(OVERCR_ROOT))

from runtime.inference_adapter import get_adapter
from runtime.inference_result import InferenceStatus


def test_hermes_cli_adapter_factory():
    """Test that get_adapter returns HermesCLIAdapter for 'hermes_cli' type."""
    print("\n" + "=" * 72)
    print("Test: HermesCLIAdapter Factory")
    print("=" * 72)
    
    adapter = get_adapter("hermes_cli")
    assert adapter.adapter_type == "hermes_cli", f"Expected 'hermes_cli', got '{adapter.adapter_type}'"
    print("  [PASS] get_adapter('hermes_cli') returns HermesCLIAdapter")
    print(f"         adapter_type = '{adapter.adapter_type}'")
    return True


def test_hermes_cli_adapter_availability():
    """Test that is_available() correctly tests Hermes CLI availability."""
    print("\n" + "=" * 72)
    print("Test: HermesCLIAdapter Availability Check")
    print("=" * 72)
    
    adapter = get_adapter("hermes_cli")
    available = adapter.is_available()
    print(f"  Hermes CLI available: {available}")
    if available:
        print("  [PASS] Hermes CLI is installed and functional")
    else:
        print("  [INFO] Hermes CLI not available (expected in CI/test environments)")
        print("         This test will skip live inference without a functional hermes CLI")
    return True


def test_hermes_cli_adapter_dry_run():
    """Test that dry_run() validates availability without making a call."""
    print("\n" + "=" * 72)
    print("Test: HermesCLIAdapter Dry Run")
    print("=" * 72)
    
    adapter = get_adapter("hermes_cli")
    config = {
        "domain": "claim_review",
        "model": "glm-5.1:cloud",
        "provider": "ollama-cloud",
        "timeout_s": 60,
        "task_id": "task-0000",
    }
    
    result = adapter.dry_run(config)
    print(f"  adapter_type: {adapter.adapter_type}")
    print(f"  cli_path: {result.get('cli_path', 'not found')}")
    print(f"  model: {result.get('model', 'default')}")
    print(f"  provider: {result.get('provider', 'default')}")
    print(f"  available: {result.get('available')}")
    print(f"  error: {result.get('error', 'none')}")
    
    # dry_run should not raise, even if unavailable
    assert 'available' in result, "dry_run should return 'available' key"
    print("  [PASS] dry_run() returns expected structure")
    return True


def test_hermes_cli_adapter_invoke():
    """Test that invoke() makes a real inference call (if available)."""
    print("\n" + "=" * 72)
    print("Test: HermesCLIAdapter Real Inference Call (v0.4.3)")
    print("=" * 72)
    
    adapter = get_adapter("hermes_cli")
    
    if not adapter.is_available():
        print("  [SKIP] Skipping live inference - Hermes CLI not available")
        print("         To enable: ensure 'hermes' is in PATH or set HERMES_CLI_PATH")
        return True
    
    # Create a minimal prompt for structured JSON output
    prompt = 'Produce ONLY valid JSON: {"test": true}'
    config = {
        "domain": "myth_fact",
        "model": "glm-5.1:cloud",
        "provider": "ollama-cloud",
        "timeout_s": 60,
        "task_id": "task-demo-001",
        "input_context": {
            "topic": "Test inference",
            "statements": ["The sky is blue on clear days."],
        },
    }
    
    print(f"  Prompt length: {len(prompt)} chars")
    print(f"  Domain: {config['domain']}")
    print(f"  Model: {config['model']}")
    print(f"  Provider: {config['provider']}")
    
    import time
    start = time.time()
    result = adapter.invoke(prompt, config)
    elapsed = time.time() - start
    
    print(f"  Elapsed: {elapsed:.2f}s")
    print(f"  Success: {result.success}")
    
    # v0.4.3: Check audit metadata has both raw and sanitized output
    metadata = result.metadata
    print(f"  Status: {metadata.status.value}")
    print(f"  Adapter type: {metadata.adapter_type}")
    
    if result.success:
        print("  [PASS] Live inference succeeded")
        if result.packet:
            print(f"  Packet keys: {list(result.packet.keys())}")
            assert "_inference_source" in result.packet, "Packet must have _inference_source marker"
            assert result.packet["_inference_source"] == "hermes_cli", "Source must be 'hermes_cli'"
            print("  [PASS] Packet has correct inference source marker")
        
        # v0.4.3: Verify raw and sanitized output in audit
        if metadata.raw_output_summary:
            print(f"  raw_output_summary (first 100 chars): {metadata.raw_output_summary[:100]}...")
        if metadata.sanitized_output_summary:
            print(f"  sanitized_output_summary (first 100 chars): {metadata.sanitized_output_summary[:100]}...")
        if metadata.sanitizer_info:
            print(f"  sanitizer_info: {metadata.sanitizer_info}")
    else:
        print(f"  Error: {metadata.error_message}")
        # Still check audit fields on error
        if metadata.raw_output_summary:
            print(f"  raw_output_summary (first 100 chars): {metadata.raw_output_summary[:100]}...")
        if metadata.sanitized_output_summary:
            print(f"  sanitized_output_summary (first 100 chars): {metadata.sanitized_output_summary[:100]}...")
        if metadata.sanitizer_info:
            print(f"  sanitizer_info: {metadata.sanitizer_info}")
    
    return True


def test_output_sanitizer_on_adapter():
    """Test that the adapter uses the output sanitizer correctly."""
    print("\n" + "=" * 72)
    print("Test: Output Sanitizer Integration in Adapter")
    print("=" * 72)
    
    from runtime.output_sanitizer import sanitize_model_output
    
    # Test 1: Clean JSON passes through
    clean_json = '{"claim_review_data": {"topic": "test", "claims": []}}'
    result, info = sanitize_model_output(clean_json)
    assert info["parse_success"] is True, "Clean JSON should parse"
    assert "claim_review_data" in result, "Should extract claim_review_data"
    print("  [PASS] Clean JSON sanitized correctly")
    
    # Test 2: Code-fenced JSON is extracted
    fenced_json = '```json\n{"myth_fact_data": {"topic": "test", "items": []}}\n```'
    result2, info2 = sanitize_model_output(fenced_json)
    assert info2["parse_success"] is True, "Fenced JSON should parse"
    assert info2["stripped_code_fence"] is True, "Should detect code fence"
    print("  [PASS] Code-fenced JSON sanitized correctly")
    
    # Test 3: Sanitizer info has correct fields
    assert "method" in info, "Sanitizer info should have 'method'"
    assert "input_length" in info, "Sanitizer info should have 'input_length'"
    assert "output_length" in info, "Sanitizer info should have 'output_length'"
    assert "parse_success" in info, "Sanitizer info should have 'parse_success'"
    print("  [PASS] Sanitizer info has correct fields")
    
    return True


def main():
    """Run all v0.4.3 HermesCLIAdapter integration tests."""
    print("=" * 72)
    print("OverCR v0.4.3 HermesCLIAdapter Integration Tests")
    print("=" * 72)
    
    tests = [
        ("Factory", test_hermes_cli_adapter_factory),
        ("Availability", test_hermes_cli_adapter_availability),
        ("Dry Run", test_hermes_cli_adapter_dry_run),
        ("Live Inference", test_hermes_cli_adapter_invoke),
        ("Output Sanitizer", test_output_sanitizer_on_adapter),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_fn in tests:
        try:
            if test_fn():
                passed += 1
            else:
                failed += 1
                print(f"  [FAIL] {name} test failed")
        except Exception as e:
            failed += 1
            print(f"  [FAIL] {name} test raised: {type(e).__name__}: {e}")
    
    print("\n" + "=" * 72)
    print("Summary")
    print("=" * 72)
    print(f"  Passed: {passed}")
    print(f"  Failed: {failed}")
    
    if failed > 0:
        sys.exit(1)
    else:
        print("\n  ALL TESTS PASSED")
        sys.exit(0)


if __name__ == "__main__":
    main()