#!/usr/bin/env python3
"""
OverCR v0.4.3 Output Sanitizer Tests
=====================================

Tests the deterministic output sanitizer that extracts the first valid
JSON object from raw model output. The sanitizer handles:
  - Markdown ```json ... ``` code fences
  - Markdown ``` ... ``` code fences (no language)
  - "Received: " prefix
  - "session_id:" preamble lines
  - Preamble text before JSON
  - Trailing text after JSON
  - Pure clean JSON (no wrapping)
"""

import sys
import os
import json
from pathlib import Path

# Resolve OVERCR_ROOT
OVERCR_ROOT = Path(os.environ.get("OVERCR_ROOT", str(Path(__file__).resolve().parent.parent)))
sys.path.insert(0, str(OVERCR_ROOT))

from runtime.output_sanitizer import sanitize_model_output, sanitize_and_parse


def test_clean_json():
    """Pure clean JSON passes through unchanged."""
    raw = '{"claim_review_data": {"topic": "test", "claims": []}}'
    result, info = sanitize_model_output(raw)
    parsed = json.loads(result)
    assert parsed["claim_review_data"]["topic"] == "test", f"Expected 'test', got {parsed['claim_review_data']['topic']}"
    assert info["parse_success"] is True
    assert info["method"] == "brace_extraction"
    print("  [PASS] Clean JSON passes through unchanged")


def test_json_code_fence():
    """JSON wrapped in ```json ... ``` is extracted."""
    raw = '```json\n{"claim_review_data": {"topic": "fenced", "claims": []}}\n```'
    result, info = sanitize_model_output(raw)
    parsed = json.loads(result)
    assert parsed["claim_review_data"]["topic"] == "fenced"
    assert info["parse_success"] is True
    assert info["stripped_code_fence"] is True
    assert info["method"] == "json_code_fence"
    print("  [PASS] JSON code fence stripped correctly")


def test_plain_code_fence():
    """JSON wrapped in ``` ... ``` (no language) is extracted."""
    raw = '```\n{"myth_fact_data": {"topic": "fenced", "items": []}}\n```'
    result, info = sanitize_model_output(raw)
    parsed = json.loads(result)
    assert parsed["myth_fact_data"]["topic"] == "fenced"
    assert info["parse_success"] is True
    assert info["stripped_code_fence"] is True
    print("  [PASS] Plain code fence stripped correctly")


def test_preamble_text():
    """Preamble text before JSON object is stripped."""
    raw = 'Here is the claim review JSON:\n\n{"claim_review_data": {"topic": "preamble", "claims": [{"text": "test", "classification": "fact", "confidence": 3, "source_quality": "secondary", "evidence": [], "unknowns": []}], "operator_brief": "test brief"}}'
    result, info = sanitize_model_output(raw)
    parsed = json.loads(result)
    assert parsed["claim_review_data"]["topic"] == "preamble"
    assert info["parse_success"] is True
    print("  [PASS] Preamble text stripped correctly")


def test_received_prefix():
    """'Received: ' prefix is stripped."""
    raw = 'Received: {"claim_review_data": {"topic": "received", "claims": []}}'
    result, info = sanitize_model_output(raw)
    parsed = json.loads(result)
    assert parsed["claim_review_data"]["topic"] == "received"
    assert info["parse_success"] is True
    print("  [PASS] 'Received:' prefix stripped correctly")


def test_session_id_prefix():
    """'session_id:' line is stripped."""
    raw = 'session_id: abc123\n{"claim_review_data": {"topic": "session", "claims": []}}'
    result, info = sanitize_model_output(raw)
    parsed = json.loads(result)
    assert parsed["claim_review_data"]["topic"] == "session"
    assert info["parse_success"] is True
    assert info["stripped_prefix_lines"] == 1
    print("  [PASS] session_id prefix stripped correctly")


def test_trailing_text():
    """Trailing text after JSON object is ignored."""
    raw = '{"claim_review_data": {"topic": "trail", "claims": []}}\n\nThat is the full analysis.'
    result, info = sanitize_model_output(raw)
    parsed = json.loads(result)
    assert parsed["claim_review_data"]["topic"] == "trail"
    assert info["parse_success"] is True
    print("  [PASS] Trailing text ignored correctly")


def test_no_json():
    """Non-JSON input returns empty string."""
    raw = 'This is just plain text with no JSON at all.'
    result, info = sanitize_model_output(raw)
    assert result == "", f"Expected empty string, got: {result[:80]}"
    assert info["parse_success"] is False
    print("  [PASS] Non-JSON input returns empty string")


def test_nested_braces():
    """Nested JSON objects are extracted fully (brace-counting works)."""
    raw = '{"claim_review_data": {"topic": "nested", "claims": [{"text": "claim 1", "classification": "fact", "confidence": 3, "source_quality": "secondary", "evidence": ["ev1", "ev2"], "unknowns": []}]}, "operator_brief": "nested test"}'
    result, info = sanitize_model_output(raw)
    parsed = json.loads(result)
    assert parsed["claim_review_data"]["claims"][0]["text"] == "claim 1"
    assert info["parse_success"] is True
    print("  [PASS] Nested braces extracted correctly")


def test_code_fence_with_preamble():
    """Code fence with preamble text and trailing text."""
    raw = 'Here is the result:\n\n```json\n{"myth_fact_data": {"topic": "combo", "items": []}}\n```\n\nDone.'
    result, info = sanitize_model_output(raw)
    parsed = json.loads(result)
    assert parsed["myth_fact_data"]["topic"] == "combo"
    assert info["parse_success"] is True
    assert info["stripped_code_fence"] is True
    print("  [PASS] Code fence + preamble + trailing text handled correctly")


def test_empty_input():
    """Empty input returns empty string."""
    result, info = sanitize_model_output("")
    assert result == ""
    assert info["parse_success"] is False
    print("  [PASS] Empty input returns empty string")


def test_whitespace_only():
    """Whitespace-only input returns empty string."""
    result, info = sanitize_model_output("   \n\n  \t  ")
    assert result == ""
    assert info["parse_success"] is False
    print("  [PASS] Whitespace-only input returns empty string")


def test_sanitize_and_parse():
    """sanitize_and_parse convenience function works."""
    raw = '{"topic": "convenience"}'
    parsed, info = sanitize_and_parse(raw)
    assert parsed is not None
    assert parsed["topic"] == "convenience"
    assert info["parse_success"] is True
    print("  [PASS] sanitize_and_parse convenience function works")


def test_sanitize_and_parse_failure():
    """sanitize_and_parse returns None for non-JSON."""
    parsed, info = sanitize_and_parse("no json here")
    assert parsed is None
    assert info["parse_success"] is False
    print("  [PASS] sanitize_and_parse returns None for non-JSON")


def test_json_array_not_object():
    """JSON array (not object) is rejected — we require a JSON object."""
    raw = '[1, 2, 3]'
    result, info = sanitize_model_output(raw)
    assert result == "", "JSON array should be rejected"
    assert info["parse_success"] is False
    print("  [PASS] JSON array (not object) correctly rejected")


def test_escaped_braces_in_strings():
    """Braces inside JSON strings don't confuse brace extraction."""
    raw = '{"claim_review_data": {"topic": "test with {braces} inside", "claims": []}}'
    result, info = sanitize_model_output(raw)
    parsed = json.loads(result)
    assert "braces" in parsed["claim_review_data"]["topic"]
    assert info["parse_success"] is True
    print("  [PASS] Escaped braces in strings handled correctly")


def main():
    """Run all output sanitizer tests."""
    print("=" * 72)
    print("OverCR v0.4.3 Output Sanitizer Tests")
    print("=" * 72)

    tests = [
        ("Clean JSON", test_clean_json),
        ("JSON Code Fence", test_json_code_fence),
        ("Plain Code Fence", test_plain_code_fence),
        ("Preamble Text", test_preamble_text),
        ("Received Prefix", test_received_prefix),
        ("Session ID Prefix", test_session_id_prefix),
        ("Trailing Text", test_trailing_text),
        ("No JSON", test_no_json),
        ("Nested Braces", test_nested_braces),
        ("Code Fence + Preamble", test_code_fence_with_preamble),
        ("Empty Input", test_empty_input),
        ("Whitespace Only", test_whitespace_only),
        ("sanitize_and_parse", test_sanitize_and_parse),
        ("sanitize_and_parse Failure", test_sanitize_and_parse_failure),
        ("JSON Array Rejection", test_json_array_not_object),
        ("Escaped Braces in Strings", test_escaped_braces_in_strings),
    ]

    passed = 0
    failed = 0

    for name, test_fn in tests:
        try:
            test_fn()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"  [FAIL] {name}: {e}")

    print("\n" + "=" * 72)
    print("Summary")
    print("=" * 72)
    print(f"  Passed: {passed}/{len(tests)}")

    if failed > 0:
        print(f"  Failed: {failed}")
        sys.exit(1)
    else:
        print("\n  ALL TESTS PASSED — output sanitizer verified")
        sys.exit(0)


if __name__ == "__main__":
    main()