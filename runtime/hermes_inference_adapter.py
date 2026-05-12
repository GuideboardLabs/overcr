#!/usr/bin/env python3
"""
OverCR v0.4.3 Hermes Inference Adapter
=========================================

Real provider-backed inference adapter that calls the host runtime
(Hermes) for live model-assisted reasoning.

v0.4.3 changes from v0.4.2:
  - Switched from `hermes chat -q` to `hermes -z` (oneshot mode).
    Oneshot mode prints ONLY the final response text to stdout —
    no banner, no spinner, no session_id line, no tool previews.
    This is the cleanest possible CLI interface for programmatic use.
  - Added deterministic output sanitizer (runtime/output_sanitizer.py)
    that extracts the first valid JSON object from model output.
    Handles markdown code fences, preamble text, and known prefixes.
  - Both raw_model_output and sanitized_model_output are recorded
    in audit metadata for full traceability.
  - The sanitizer does NOT weaken or bypass validation — it only
    strips non-JSON content that models routinely emit around
    structured output.

Architecture:
  - HermesCLIAdapter calls `hermes -z <prompt>` via subprocess —
    the oneshot mode that produces clean, banner-free output.
  - OverCR holds NO API keys. All auth, provider routing, and model
    selection goes through Hermes config.
  - The adapter is a thin subprocess boundary: prompt in, response out,
    governance enforced by the 6-level validator on the other end.
  - MockInferenceAdapter remains available as a fallback for testing.

Governance (enforced regardless of model output):
  - Model output CANNOT change doctrine
  - Model output CANNOT bypass approval gates
  - Model output CANNOT route directly to another subagent
  - Model output CANNOT claim live browsing occurred
  - Model output is UNTRUSTED until validated through 6-level validator
  - On inference failure, task MUST NOT advance state
  - Deterministic fallback MUST always be available

Safety:
  - If HERMES_CLI is not available, is_available() returns False
  - If the subprocess times out, returns InferenceStatus.TIMEOUT
  - If the subprocess exits nonzero, returns InferenceStatus.ERROR
  - If the model output is unparseable after sanitization,
    returns InferenceStatus.MALFORMED_OUTPUT
  - Raw AND sanitized model output captured in audit (truncated to 500 chars)
  - No API keys held by OverCR — all auth through Hermes
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# Import inference result types
try:
    from runtime.inference_result import (
        InferenceMetadata,
        InferenceResult,
        InferenceStatus,
        make_inference_attempt_id,
    )
except ImportError:
    _ROOT = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(_ROOT))
    from runtime.inference_result import (
        InferenceMetadata,
        InferenceResult,
        InferenceStatus,
        make_inference_attempt_id,
    )

# Import output sanitizer
try:
    from runtime.output_sanitizer import sanitize_model_output, sanitize_and_parse
except ImportError:
    _ROOT = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(_ROOT))
    from runtime.output_sanitizer import sanitize_model_output, sanitize_and_parse

# Import the base class from the parent module
try:
    from runtime.inference_adapter import BaseInferenceAdapter
except ImportError:
    _ROOT = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(_ROOT))
    from runtime.inference_adapter import BaseInferenceAdapter


class HermesCLIAdapter(BaseInferenceAdapter):
    """
    Live inference adapter that calls the Hermes CLI for real model inference.

    Uses `hermes -z <prompt>` (oneshot mode) which prints ONLY the final
    response text to stdout — no banner, no session metadata, no spinner.

    The output sanitizer extracts the first valid JSON object from the
    model's response, handling markdown code fences and preamble text.
    Both raw and sanitized output are recorded for audit traceability.
    """

    def __init__(self, hermes_cli_path: str = "", model: str = "",
                 provider: str = "", timeout_s: float = 60.0):
        """
        Initialize the Hermes CLI adapter.

        Args:
            hermes_cli_path: Path to the hermes binary. Defaults to
                HERMES_CLI_PATH env var or 'hermes' in PATH.
            model: Override model for this adapter. Defaults to config.
            provider: Override provider for this adapter. Defaults to config.
            timeout_s: Default timeout for inference calls.
        """
        self._hermes_cli_path = hermes_cli_path or os.environ.get(
            "HERMES_CLI_PATH", ""
        )
        self._model = model
        self._provider = provider
        self._timeout_s = timeout_s
        self._available = None  # Lazy check, cached

    @property
    def adapter_type(self) -> str:
        return "hermes_cli"

    def is_available(self) -> bool:
        """
        Check whether the Hermes CLI is available and functional.

        Returns True if:
          1. hermes binary found (HERMES_CLI_PATH or in PATH)
          2. `hermes --version` exits 0

        Result is cached after first check.
        """
        if self._available is not None:
            return self._available

        cli_path = self._resolve_cli_path()
        if not cli_path:
            self._available = False
            return False

        try:
            result = subprocess.run(
                [cli_path, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            self._available = result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            self._available = False

        return self._available

    def invoke(self, prompt: str, config: dict) -> InferenceResult:
        """
        Invoke a live model through the Hermes CLI.

        Calls `hermes -z <prompt>` (oneshot mode) via subprocess.
        Oneshot mode prints ONLY the final response text to stdout —
        no banner, no session_id line, no tool previews.

        The raw model output is then run through the deterministic
        output sanitizer (output_sanitizer.py) which extracts the
        first valid JSON object.

        Both raw_model_output and sanitized_model_output are recorded
        in the InferenceMetadata for audit traceability.

        Args:
            prompt: Fully rendered prompt text (from inference_prompt.md)
            config: Domain-specific config dict with keys:
                - domain: e.g. "claim_review", "myth_fact"
                - model: Model name (e.g. "glm-5.1:cloud")
                - provider: Provider name (e.g. "ollama-cloud")
                - timeout_s: Timeout in seconds
                - task_id: Task ID for audit trail
                - input_context: Original input for routing context

        Returns:
            InferenceResult with status SUCCESS/ERROR/TIMEOUT/MALFORMED_OUTPUT
        """
        if not self.is_available():
            return self._error_result(
                config=config,
                prompt=prompt,
                error_message="HermesCLIAdapter unavailable: hermes CLI not found or not functional",
            )

        domain = config.get("domain", "unknown")
        model = self._model or config.get("model", "glm-5.1:cloud")
        provider = self._provider or config.get("provider", "ollama-cloud")
        timeout_s = config.get("timeout_s", self._timeout_s)
        task_id = config.get("task_id", "task-0000")
        attempt_id = make_inference_attempt_id(domain, task_id)
        prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]

        cli_path = self._resolve_cli_path()
        start_time = time.time()

        # Build the hermes oneshot command
        # `-z` is the oneshot flag: prints ONLY the final response text.
        # No banner, no spinner, no session_id, no tool previews.
        # `--ignore-rules` prevents AGENTS.md/memory injection which could
        #   pollute the output with session context.
        cmd = [
            cli_path,
            "-z", prompt,
            "--model", model,
            "--provider", provider,
            "--ignore-rules",
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_s + 15,  # Grace margin beyond model timeout
            )

            elapsed = time.time() - start_time

            if result.returncode != 0:
                stderr_summary = (result.stderr or "")[:500]
                return self._error_result(
                    config=config,
                    prompt=prompt,
                    attempt_id=attempt_id,
                    prompt_hash=prompt_hash,
                    error_message=f"Hermes CLI failed (exit={result.returncode}): {stderr_summary}",
                    elapsed=elapsed,
                    timeout_s=timeout_s,
                    model=model,
                    provider=provider,
                )

            # Step 1: Capture raw model output
            raw_output = (result.stdout or "").strip()

            if not raw_output:
                return self._error_result(
                    config=config,
                    prompt=prompt,
                    attempt_id=attempt_id,
                    prompt_hash=prompt_hash,
                    error_message="Hermes CLI returned empty output",
                    elapsed=elapsed,
                    timeout_s=timeout_s,
                    model=model,
                    provider=provider,
                    extra_audit={
                        "raw_model_output": "<empty>",
                        "sanitized_model_output": "<empty>",
                        "sanitizer_info": {"method": "none", "input_length": 0, "output_length": 0},
                    },
                )

            # Step 2: Sanitize model output — extract first valid JSON object
            sanitized_json_str, sanitizer_info = sanitize_model_output(raw_output)

            # Step 3: Record BOTH raw and sanitized output in audit
            raw_summary = raw_output[:500] if len(raw_output) > 500 else raw_output
            sanitized_summary = sanitized_json_str[:500] if len(sanitized_json_str) > 500 else sanitized_json_str

            # Step 4: Parse the sanitized JSON
            if not sanitized_json_str:
                # No valid JSON found in model output
                return self._error_result(
                    config=config,
                    prompt=prompt,
                    attempt_id=attempt_id,
                    prompt_hash=prompt_hash,
                    error_message=(
                        f"Model output contained no valid JSON object. "
                        f"Sanitizer method={sanitizer_info.get('method', 'none')}. "
                        f"Raw output (first 200 chars): {raw_output[:200]}"
                    ),
                    elapsed=elapsed,
                    timeout_s=timeout_s,
                    model=model,
                    provider=provider,
                    status=InferenceStatus.MALFORMED_OUTPUT,
                    extra_audit={
                        "raw_model_output": raw_summary,
                        "sanitized_model_output": "<no valid JSON>",
                        "sanitizer_info": sanitizer_info,
                    },
                )

            try:
                parsed = json.loads(sanitized_json_str)
            except json.JSONDecodeError as e:
                return self._error_result(
                    config=config,
                    prompt=prompt,
                    attempt_id=attempt_id,
                    prompt_hash=prompt_hash,
                    error_message=(
                        f"Sanitized model output failed JSON parse: {e}. "
                        f"Sanitizer method={sanitizer_info.get('method', 'none')}. "
                        f"Sanitized output (first 200 chars): {sanitized_json_str[:200]}"
                    ),
                    elapsed=elapsed,
                    timeout_s=timeout_s,
                    model=model,
                    provider=provider,
                    status=InferenceStatus.MALFORMED_OUTPUT,
                    extra_audit={
                        "raw_model_output": raw_summary,
                        "sanitized_model_output": sanitized_summary,
                        "sanitizer_info": sanitizer_info,
                    },
                )

            if not isinstance(parsed, dict):
                return self._error_result(
                    config=config,
                    prompt=prompt,
                    attempt_id=attempt_id,
                    prompt_hash=prompt_hash,
                    error_message=(
                        f"Model output parsed as {type(parsed).__name__}, expected dict/object. "
                        f"Sanitized output (first 200 chars): {sanitized_json_str[:200]}"
                    ),
                    elapsed=elapsed,
                    timeout_s=timeout_s,
                    model=model,
                    provider=provider,
                    status=InferenceStatus.MALFORMED_OUTPUT,
                    extra_audit={
                        "raw_model_output": raw_summary,
                        "sanitized_model_output": sanitized_summary,
                        "sanitizer_info": sanitizer_info,
                    },
                )

            # Step 5: Mark as live inference
            packet = parsed
            packet["_inference_source"] = "hermes_cli"

            metadata = InferenceMetadata(
                inference_attempt_id=attempt_id,
                domain=domain,
                subagent="knower",
                adapter_type="hermes_cli",
                selected_model=model,
                selected_provider=provider,
                route_used=f"hermes_cli/{domain}",
                prompt_hash=prompt_hash,
                timeout_s=timeout_s,
                elapsed_s=elapsed,
                status=InferenceStatus.SUCCESS,
                fallback_used=False,
                raw_output_summary=raw_summary,
                sanitized_output_summary=sanitized_summary,
                sanitizer_info=sanitizer_info,
            )

            return InferenceResult(
                metadata=metadata,
                packet=packet,
                fallback_packet=None,
            )

        except subprocess.TimeoutExpired:
            elapsed = time.time() - start_time
            return self._error_result(
                config=config,
                prompt=prompt,
                attempt_id=attempt_id,
                prompt_hash=prompt_hash,
                error_message=f"Inference timed out after {timeout_s}s",
                elapsed=elapsed,
                timeout_s=timeout_s,
                model=model,
                provider=provider,
                status=InferenceStatus.TIMEOUT,
            )

        except Exception as e:
            elapsed = time.time() - start_time
            return self._error_result(
                config=config,
                prompt=prompt,
                attempt_id=attempt_id,
                prompt_hash=prompt_hash,
                error_message=f"Inference error: {type(e).__name__}: {str(e)[:300]}",
                elapsed=elapsed,
                timeout_s=timeout_s,
                model=model,
                provider=provider,
            )

    def dry_run(self, config: dict) -> dict:
        """
        Validate adapter availability without making a real model call.

        Returns a dict with:
          - available: bool — whether the adapter can make calls
          - cli_path: str — resolved CLI path
          - model: str — model that would be used
          - provider: str — provider that would be used
          - error: str or None — reason for unavailability
        """
        cli_path = self._resolve_cli_path()
        available = self.is_available()
        model = self._model or config.get("model", "glm-5.1:cloud")
        provider = self._provider or config.get("provider", "ollama-cloud")

        result = {
            "available": available,
            "cli_path": cli_path or "not found",
            "model": model,
            "provider": provider,
            "error": None,
        }

        if not cli_path:
            result["error"] = "Hermes CLI not found (set HERMES_CLI_PATH or add hermes to PATH)"
        elif not available:
            result["error"] = f"Hermes CLI at {cli_path} not functional (exit code non-zero)"

        return result

    def _resolve_cli_path(self) -> str:
        """
        Resolve the Hermes CLI binary path.

        Priority:
          1. HERMES_CLI_PATH env var
          2. Constructor-provided path
          3. `hermes` in PATH (via shutil.which)
        """
        env_path = os.environ.get("HERMES_CLI_PATH", "")
        if env_path and os.path.isfile(env_path) and os.access(env_path, os.X_OK):
            return env_path

        if self._hermes_cli_path:
            if os.path.isfile(self._hermes_cli_path) and os.access(
                self._hermes_cli_path, os.X_OK
            ):
                return self._hermes_cli_path

        found = shutil.which("hermes")
        if found:
            return found

        return ""

    def _error_result(
        self,
        config: dict,
        prompt: str,
        error_message: str,
        attempt_id: str = "",
        prompt_hash: str = "",
        elapsed: float = 0.0,
        timeout_s: float = 60.0,
        model: str = "",
        provider: str = "",
        status: InferenceStatus = InferenceStatus.ERROR,
        extra_audit: dict = None,
    ) -> InferenceResult:
        """Create an error InferenceResult."""
        domain = config.get("domain", "unknown")
        task_id = config.get("task_id", "task-0000")
        if not attempt_id:
            attempt_id = make_inference_attempt_id(domain, task_id)
        if not prompt_hash:
            prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]

        metadata = InferenceMetadata(
            inference_attempt_id=attempt_id,
            domain=domain,
            subagent="knower",
            adapter_type="hermes_cli",
            selected_model=model,
            selected_provider=provider,
            route_used=f"hermes_cli/{domain}",
            prompt_hash=prompt_hash,
            timeout_s=timeout_s,
            elapsed_s=elapsed,
            status=status,
            fallback_used=False,
            error_message=error_message,
        )

        # Attach extra audit data if provided (raw/sanitized output on error)
        if extra_audit:
            metadata.raw_output_summary = extra_audit.get("raw_model_output", metadata.raw_output_summary)
            metadata.sanitized_output_summary = extra_audit.get("sanitized_model_output", "")
            metadata.sanitizer_info = extra_audit.get("sanitizer_info", {})

        return InferenceResult(
            metadata=metadata,
            packet=None,
            fallback_packet=None,
        )


def get_cli_adapter(model: str = "", provider: str = "",
                    timeout_s: float = 60.0) -> HermesCLIAdapter:
    """
    Factory function to get a HermesCLIAdapter with sensible defaults.

    This is the v0.4.3 entry point for real provider-backed inference.
    """
    return HermesCLIAdapter(model=model, provider=provider, timeout_s=timeout_s)