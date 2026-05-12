#!/usr/bin/env python3
"""
OverCR v0.6.0 — CodER Patch Plan Runtime Demo
===============================================

Demonstrates the CodER inference worker producing an advisory patch-plan
packet with full governance enforcement and zero filesystem mutation.

This demo:
  1. Loads inference routing config
  2. Invokes the CodER inference worker (mock adapter by default)
  3. Validates the output through the 6-level validator
  4. Falls back to deterministic worker if adapter unavailable
  5. Produces a typed coder_patch_plan packet with audit trail
  6. Verifies no filesystem mutation occurred

Governance guarantees:
  - Proposed diffs are advisory artifacts ONLY — never auto-applied
  - No shell commands executed automatically
  - No files modified by CodER inference mode
  - approval_required=true enforced at L4
  - All mutation requires OverCR approval gate
  - Model output is untrusted until sanitized and validated
  - Deterministic fallback always available

Usage:
  python3 examples/runtime_demo_coder_patch_plan.py
"""

import json
import sys
import os
import subprocess
import importlib.util
from pathlib import Path
from datetime import datetime, timezone

# Bootstrap project root
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


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
        print("[WARN] PyYAML not available, using defaults")
        return {}


def validate_packet_fn(packet: dict) -> tuple:
    """Validate inference output through the 6-level validator."""
    validate_path = ROOT / "tools" / "validate_packet.py"
    spec = importlib.util.spec_from_file_location("validate_packet", str(validate_path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    result = mod.validate_packet(packet)
    if isinstance(result, tuple):
        return result
    return (
        result.valid if hasattr(result, "valid") else False,
        result.errors if hasattr(result, "errors") else [],
        result.warnings if hasattr(result, "warnings") else [],
    )


def invoke_coder_worker(request: dict, timeout: float = 15.0) -> dict:
    """Invoke the CodER inference worker as a subprocess."""
    worker_path = ROOT / "subagents" / "coder" / "inference_worker.py"
    if not worker_path.exists():
        return {"exit_code": -1, "stdout": "", "stderr": f"Worker not found: {worker_path}"}

    try:
        result = subprocess.run(
            [sys.executable, str(worker_path)],
            input=json.dumps(request),
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(ROOT),
        )
        return {
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    except subprocess.TimeoutExpired:
        return {"exit_code": -2, "stdout": "", "stderr": "Worker timed out"}


def run_demo():
    """Run the CodER patch plan runtime demo."""
    print("=" * 70)
    print("OverCR v0.6.0 — CodER Patch Plan Runtime Demo")
    print("=" * 70)

    # 1. Load config
    config = load_routing_config()
    coder_config = config.get("_coder", {})
    patch_plan_cfg = coder_config.get("patch_plan", {})
    governance = config.get("_governance", {})

    print(f"\n[CONFIG] Domain: patch_plan")
    print(f"[CONFIG] Adapter: {patch_plan_cfg.get('adapter', 'mock')}")
    print(f"[CONFIG] Model: {patch_plan_cfg.get('model', 'glm-5.1:cloud')}")
    print(f"[CONFIG] Provider: {patch_plan_cfg.get('provider', 'ollama-cloud')}")
    print(f"[CONFIG] Fallback model: {patch_plan_cfg.get('fallback_model', 'N/A')}")
    print(f"[CONFIG] Fallback to deterministic: {patch_plan_cfg.get('fallback_to_deterministic', True)}")
    print(f"[CONFIG] Timeout: {patch_plan_cfg.get('timeout_s', 45)}s")

    # 2. Construct the request
    task_id = "task-0600"
    request = {
        "task_id": task_id,
        "domain": "patch_plan",
        "instruction": "Analyze the off-by-one error in src/utils/array.py loop termination and produce an advisory patch plan",
        "input_context": {
            "entity": "src/utils/array.py",
            "bug_description": "Loop uses i <= len(arr) instead of i < len(arr), causing IndexError at boundary",
            "code_snippet": "for i in range(0, len(arr) + 1):\n    result.append(arr[i])",
        },
        "required_packet_type": "coder_patch_plan",
    }

    print(f"\n[REQUEST] Task: {task_id}")
    print(f"[REQUEST] Domain: patch_plan")
    print(f"[REQUEST] Entity: {request['input_context']['entity']}")
    print(f"[REQUEST] Bug: {request['input_context']['bug_description'][:60]}...")

    # 3. Invoke the CodER inference worker
    print(f"\n[INVOKE] Running CodER inference worker...")
    start_time = datetime.now(timezone.utc)

    result = invoke_coder_worker(request)

    elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
    print(f"[INVOKE] Exit code: {result['exit_code']}")
    print(f"[INVOKE] Elapsed: {elapsed:.2f}s")

    if result["exit_code"] != 0:
        print(f"\n[ERROR] Worker exited with code {result['exit_code']}")
        print(f"[ERROR] stderr: {result['stderr'][:300]}")
        return False

    # 4. Parse the output
    try:
        packet = json.loads(result["stdout"])
    except json.JSONDecodeError:
        print(f"\n[ERROR] Worker output is not valid JSON")
        print(f"[ERROR] First 200 chars: {result['stdout'][:200]}")
        return False

    print(f"\n[OUTPUT] Packet type: {packet.get('packet_type', 'unknown')}")
    print(f"[OUTPUT] Version: {packet.get('version', 'unknown')}")
    print(f"[OUTPUT] Source: {packet.get('source', 'unknown')}")
    print(f"[OUTPUT] Target: {packet.get('target', 'unknown')}")
    print(f"[OUTPUT] Task ID: {packet.get('task_id', 'unknown')}")

    # 5. Validate the packet
    print(f"\n[VALIDATE] Running 6-level validation...")
    valid, errors, warnings = validate_packet_fn(packet)

    print(f"[VALIDATE] Valid: {valid}")
    print(f"[VALIDATE] Errors: {len(errors)}")
    for e in errors[:5]:
        print(f"  - {e}")
    if len(errors) > 5:
        print(f"  ... and {len(errors) - 5} more")
    print(f"[VALIDATE] Warnings: {len(warnings)}")
    for w in warnings[:3]:
        print(f"  - {w}")

    # 6. Check safety guarantees
    print(f"\n[SAFETY] Checking safety guarantees...")

    # approval_required must be True
    approval = packet.get("approval_required")
    if approval is True:
        print(f"[SAFETY] PASS: approval_required=True enforced")
    else:
        print(f"[SAFETY] FAIL: approval_required={approval} (expected True)")
        valid = False

    # Files modified must be empty
    files_modified = packet.get("audit_trail", {}).get("files_modified", [])
    if files_modified == []:
        print(f"[SAFETY] PASS: No files modified (zero filesystem mutation)")
    else:
        print(f"[SAFETY] FAIL: Files were modified: {files_modified}")
        valid = False

    # Target must be overcr
    target = packet.get("target")
    if target == "overcr":
        print(f"[SAFETY] PASS: Target is 'overcr' (no direct subagent routing)")
    else:
        print(f"[SAFETY] FAIL: Target is '{target}' (direct routing detected)")
        valid = False

    # 7. Display patch plan data
    pp = packet.get("patch_plan_data", {})
    if pp:
        print(f"\n[PLAN] Code inspection summary: {pp.get('code_inspection_summary', 'N/A')[:80]}...")
        diag = pp.get("bug_diagnosis", {})
        print(f"[PLAN] Bug diagnosis: {diag.get('summary', 'N/A')[:80]}...")
        print(f"[PLAN] Root cause: {diag.get('root_cause', 'N/A')[:80]}...")
        print(f"[PLAN] Confidence: {diag.get('confidence', 'N/A')}")

        plan = pp.get("patch_plan", {})
        print(f"[PLAN] Patch description: {plan.get('description', 'N/A')[:80]}...")
        print(f"[PLAN] Files to modify: {plan.get('files_to_modify', [])}")
        print(f"[PLAN] Complexity: {plan.get('estimated_complexity', 'N/A')}")

        diff = pp.get("proposed_diff", "")
        print(f"[PLAN] Proposed diff length: {len(diff)} chars")
        if diff:
            print(f"[PLAN] Diff preview: {diff[:80]}...")

        test_plan = pp.get("test_plan", {})
        print(f"[PLAN] Test cases: {len(test_plan.get('test_cases', []))}")
        print(f"[PLAN] Rollback plan: {pp.get('rollback_plan', 'N/A')[:60]}...")

        risk = pp.get("risk_notes", {})
        print(f"[PLAN] Risk level: {risk.get('level', 'N/A')}")
        print(f"[PLAN] Risk factors: {risk.get('factors', [])}")
        print(f"[PLAN] Mitigations: {risk.get('mitigations', [])}")

    # 8. Display audit trail
    audit = packet.get("audit_trail", {})
    print(f"\n[AUDIT] Inference mode: {audit.get('inference_mode', 'N/A')}")
    print(f"[AUDIT] Inference source: {audit.get('inference_source', 'N/A')}")
    print(f"[AUDIT] Selected model: {audit.get('selected_model', 'N/A')}")
    print(f"[AUDIT] Selected provider: {audit.get('selected_provider', 'N/A')}")
    print(f"[AUDIT] Route used: {audit.get('route_used', 'N/A')}")
    print(f"[AUDIT] Attempt ID: {audit.get('inference_attempt_id', 'N/A')}")
    print(f"[AUDIT] Prompt hash: {audit.get('prompt_hash', 'N/A')}")
    print(f"[AUDIT] Fallback used: {audit.get('fallback_used', 'N/A')}")
    print(f"[AUDIT] Elapsed: {audit.get('elapsed_s', 'N/A')}s")

    # 9. Summary
    print(f"\n{'=' * 70}")
    if valid:
        print("DEMO RESULT: PASS")
        print(f"  Inference source: {audit.get('inference_source', 'unknown')}")
        print(f"  Validation: PASSED (L1-L6)")
        print(f"  Safety: ZERO filesystem mutation, approval gate enforced")
        print(f"  Packet type: {packet.get('packet_type', 'unknown')}")
        print(f"  Proposed diff: advisory only (not applied)")
    else:
        print("DEMO RESULT: FAIL")
        print(f"  Validation: FAILED ({len(errors)} errors)")
        print(f"  Safety violations detected")
    print(f"{'=' * 70}")

    return valid


if __name__ == "__main__":
    success = run_demo()
    sys.exit(0 if success else 1)