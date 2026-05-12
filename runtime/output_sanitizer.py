#!/usr/bin/env python3
"""
OverCR v0.4.3 Output Sanitizer
================================

Deterministic, minimal sanitizer for model output produced by the Hermes CLI.

Purpose:
  Hermes `-z` oneshot mode returns clean model output, but models can still:
    - Wrap JSON in ```json ... ``` markdown code blocks
    - Add "Received: " prefixes
    - Emit session_id: lines (from chat mode, defensive only)
    - Include preamble text before the JSON object
    - Include trailing text after the JSON object

  This sanitizer does ONE thing: extract the first valid JSON object from
  raw model output, deterministically. It does NOT modify, weaken, or
  bypass any validation — it only strips non-JSON content that models
  routinely emit around structured output.

  The sanitizer is intentionally tiny and side-effect-free. It has no
  dependencies beyond the Python stdlib and does not touch the packet
  schema, governance rules, or validation logic.

Audit:
  Both raw_model_output (before sanitization) and sanitized_model_output
  (after sanitization) are recorded in the InferenceMetadata for full
  traceability. The validator always sees the sanitized output.
"""

import json
import re
from typing import Optional, Tuple


def sanitize_model_output(raw: str) -> Tuple[str, dict]:
    """
    Extract the first valid JSON object from raw model output.

    This is a deterministic, minimal transformation:
      1. Strip ```json ... ``` code fences
      2. Strip ``` ... ``` code fences (no language)
      3. Strip known prefixes ("Received: ", "session_id: ...\\n")
      4. Find the first '{' and match its closing '}' using brace counting
      5. Parse the extracted substring as JSON
      6. Return (json_string, info_dict) where info contains audit metadata

    Args:
        raw: The raw model output from the inference adapter.

    Returns:
        Tuple of (sanitized_json_string, info_dict):
          - sanitized_json_string: The extracted JSON as a string,
            or empty string if no valid JSON found.
          - info_dict: Audit metadata with keys:
            - input_length: Length of raw input in chars
            - output_length: Length of sanitized output in chars
            - method: Which extraction method was used
            - stripped_prefix_lines: Number of prefix lines stripped
            - stripped_code_fence: Whether markdown code fence was removed
            - parse_success: Whether JSON parsing succeeded
    """
    info = {
        "input_length": len(raw),
        "output_length": 0,
        "method": "none",
        "stripped_prefix_lines": 0,
        "stripped_code_fence": False,
        "parse_success": False,
    }

    if not raw or not raw.strip():
        return "", info

    text = raw.strip()
    prefix_lines_stripped = 0
    code_fence_removed = False

    # Step 1: Strip ```json ... ``` code fences
    # Match ```json followed by content, then ```
    json_fence_pattern = re.compile(
        r'```json\s*\n?(.*?)\n?\s*```', re.DOTALL
    )
    fence_match = json_fence_pattern.search(text)
    if fence_match:
        text = fence_match.group(1).strip()
        code_fence_removed = True
        info["method"] = "json_code_fence"
    else:
        # Step 1b: Strip ``` ... ``` code fences (no language specifier)
        plain_fence_pattern = re.compile(
            r'```\s*\n?(.*?)\n?\s*```', re.DOTALL
        )
        plain_match = plain_fence_pattern.search(text)
        if plain_match:
            text = plain_match.group(1).strip()
            code_fence_removed = True
            info["method"] = "plain_code_fence"

    # Step 2: Strip known prefixes
    # - "session_id: <hex>\\n" (Hermes chat mode, defensive)
    # - "Received: " (Hermes confirmation prefix)
    original_text = text
    if text.startswith("session_id:"):
        lines = text.split("\n", 1)
        if len(lines) > 1:
            text = lines[1].strip()
            prefix_lines_stripped += 1
        else:
            text = ""

    if text.startswith("Received: "):
        text = text[len("Received: "):].strip()

    if text != original_text and info["method"] == "none":
        info["method"] = "prefix_strip"

    info["stripped_prefix_lines"] = prefix_lines_stripped
    info["stripped_code_fence"] = code_fence_removed

    # Step 3: Find the first '{' and match its closing '}'
    # This handles preamble text like "Here is the JSON:" before the object.
    start_idx = text.find('{')
    if start_idx == -1:
        # No JSON object found at all
        info["output_length"] = 0
        return "", info

    # Brace-count to find the matching closing brace
    depth = 0
    end_idx = start_idx
    in_string = False
    escape_next = False

    for i in range(start_idx, len(text)):
        ch = text[i]

        if escape_next:
            escape_next = False
            continue

        if ch == '\\' and in_string:
            escape_next = True
            continue

        if ch == '"' and not escape_next:
            in_string = not in_string
            continue

        if in_string:
            continue

        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                end_idx = i + 1
                break

    if depth != 0:
        # Unbalanced braces — no valid JSON object
        info["output_length"] = 0
        return "", info

    candidate = text[start_idx:end_idx]

    # Step 4: Validate it's parseable JSON
    try:
        parsed = json.loads(candidate)
        if not isinstance(parsed, dict):
            # Found a valid JSON value but not an object
            info["output_length"] = 0
            return "", info
    except json.JSONDecodeError:
        # Not valid JSON even after extraction
        info["output_length"] = 0
        return "", info

    if info["method"] == "none":
        info["method"] = "brace_extraction"

    info["output_length"] = len(candidate)
    info["parse_success"] = True

    return candidate, info


def sanitize_and_parse(raw: str) -> Tuple[Optional[dict], dict]:
    """
    Sanitize model output and parse it as JSON.

    Convenience wrapper that combines sanitize_model_output with json.loads.

    Args:
        raw: The raw model output from the inference adapter.

    Returns:
        Tuple of (parsed_dict_or_None, info_dict):
          - parsed_dict: The parsed JSON object, or None if parsing failed
          - info_dict: Audit metadata from sanitization
    """
    json_str, info = sanitize_model_output(raw)

    if not json_str:
        return None, info

    try:
        parsed = json.loads(json_str)
        return parsed, info
    except json.JSONDecodeError:
        return None, info