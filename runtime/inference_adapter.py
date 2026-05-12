#!/usr/bin/env python3
"""
OverCR v0.4.1 Inference Adapter
=================================

Interface between the OverCR orchestration substrate and model providers.
Provides controlled inference-backed reasoning for subagent workers.

Architecture:
  - BaseInferenceAdapter: Abstract interface (contract)
  - MockInferenceAdapter: Simulated inference for testing (no real model calls)
  - HermesInferenceAdapter: Calls host runtime (Hermes) for live model inference

Governance rules (enforced regardless of adapter):
  - Model output CANNOT change doctrine
  - Model output CANNOT bypass approval gates
  - Model output CANNOT route directly to another subagent
  - Model output CANNOT claim live browsing occurred
  - Model output is UNTRUSTED until validated through 6-level validator
  - On inference failure, task MUST NOT advance state
  - Deterministic fallback MUST always be available

The adapter produces a raw model response. The inference_worker.py template
formats it into a typed packet. ALL packets — whether from inference or
deterministic — go through the same 6-level validator.
"""

import hashlib
import json
import os
import sys
import time
from abc import ABC, abstractmethod
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
    # Allow running from project root
    _ROOT = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(_ROOT))
    from runtime.inference_result import (
        InferenceMetadata,
        InferenceResult,
        InferenceStatus,
        make_inference_attempt_id,
    )


class BaseInferenceAdapter(ABC):
    """
    Abstract base class for inference adapters.

    All inference adapters must implement:
      - invoke(prompt, config) -> InferenceResult
      - is_available() -> bool
      - adapter_type -> str
    """

    @property
    @abstractmethod
    def adapter_type(self) -> str:
        """Return adapter type identifier (e.g., 'mock', 'hermes')."""
        ...

    @abstractmethod
    def invoke(self, prompt: str, config: dict) -> InferenceResult:
        """
        Invoke the inference backend with a formatted prompt.

        Args:
            prompt: Fully rendered prompt text (from inference_prompt.md template)
            config: Domain-specific config from inference_routing.yaml,
                    including model, provider, timeout_s, domain, etc.

        Returns:
            InferenceResult with metadata and raw model output (or error).
            The result.packet may be None on failure — caller must handle.
        """
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the adapter can make inference calls right now."""
        ...


class MockInferenceAdapter(BaseInferenceAdapter):
    """
    Simulated inference adapter for testing.

    Produces deterministic mock responses that parse into valid packet
    structures for claim_review and myth_fact domains. Does NOT make
    real model calls. This is explicitly NOT live provider execution.

    Use cases:
      - CI/CD testing without model dependency
      - Development and debugging
      - Validating inference pipeline without cost/latency
      - Regression testing governance constraints
    """

    @property
    def adapter_type(self) -> str:
        return "mock"

    def is_available(self) -> bool:
        return True

    def invoke(self, prompt: str, config: dict) -> InferenceResult:
        """
        Produce a mock inference response.

        The mock response is structured JSON that parses into a packet
        matching the requested domain's schema. It is labeled with
        source="mock" in the metadata so auditors can distinguish it
        from real model output.
        """
        start_time = time.time()
        domain = config.get("domain", "unknown")
        model = config.get("model", "mock-model")
        provider = config.get("provider", "mock")
        timeout_s = config.get("timeout_s", 30.0)
        task_id = config.get("task_id", "task-0000")
        attempt_id = make_inference_attempt_id(domain, task_id)

        # Compute prompt hash for audit trail
        prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]

        # Simulate inference latency (very short for mock)
        time.sleep(0.001)

        elapsed = time.time() - start_time

        # Generate mock response based on domain
        raw_output = self._generate_mock_response(domain, prompt, config)

        metadata = InferenceMetadata(
            inference_attempt_id=attempt_id,
            domain=domain,
            subagent="knower",
            adapter_type="mock",
            selected_model=model,
            selected_provider=provider,
            route_used=f"mock/{domain}",
            prompt_hash=prompt_hash,
            timeout_s=timeout_s,
            elapsed_s=elapsed,
            status=InferenceStatus.SUCCESS,
            fallback_used=False,
            raw_output_summary=f"[MOCK] {domain} inference — simulated, not live",
        )

        return InferenceResult(
            metadata=metadata,
            packet=raw_output,
            fallback_packet=None,
        )

    def _generate_mock_response(self, domain: str, prompt: str, config: dict) -> dict:
        """
        Generate a mock inference response that fits the domain packet schema.

        The response is a structured dict that the inference_worker will
        merge into the final typed packet. It contains the domain-specific
        data fields but NOT the envelope (packet_type, source, target, etc.)
        — those are added by the inference_worker.
        """
        input_context = config.get("input_context", {})
        entity = input_context.get("entity", "Test Entity")
        topic = input_context.get("topic", f"Test {domain} analysis")

        now = datetime.now(timezone.utc).isoformat()

        if domain == "claim_review":
            claims_text = input_context.get("claims_to_review", [
                f"Claim about {entity}",
            ])
            claims = []
            for i, ct in enumerate(claims_text[:4]):
                claims.append({
                    "text": ct,
                    "classification": ["fact", "inference", "assumption", "rumor"][i % 4],
                    "confidence": (i % 4) + 1,
                    "source_quality": ["primary", "secondary", "tertiary", "unverified"][i % 4],
                    "evidence": [f"Mock evidence for claim {i+1}"],
                    "unknowns": [f"Verification needed for claim {i+1}"],
                })

            return {
                "_inference_source": "mock",
                "claim_review_data": {
                    "topic": topic,
                    "claims": claims,
                    "operator_brief": f"[Mock inference] Reviewed {len(claims)} claim(s) about {topic}. Classification uses mock heuristic, not live model reasoning.",
                },
            }

        elif domain == "myth_fact":
            statements = input_context.get("statements", [
                f"Statement about {entity}",
            ])
            items = []
            classifications = ["myth", "fact", "partial_truth", "unverified"]
            for i, stmt in enumerate(statements[:4]):
                items.append({
                    "statement": stmt,
                    "classification": classifications[i % 4],
                    "confidence": (i % 4) + 1,
                    "source_quality": ["primary", "secondary", "tertiary", "unverified"][i % 4],
                    "explanation": f"[Mock inference] Simulated analysis of: {stmt[:60]}",
                    "unknowns": [f"Verification needed for statement {i+1}"],
                })

            return {
                "_inference_source": "mock",
                "myth_fact_data": {
                    "topic": topic,
                    "items": items,
                    "operator_brief": f"[Mock inference] Analyzed {len(items)} statement(s) about {topic}. Classification uses mock heuristic, not live model reasoning.",
                },
            }

        elif domain == "patch_plan":
            instruction = input_context.get("instruction", config.get("instruction", f"Analyze {entity}"))
            return {
                "_inference_source": "mock",
                "patch_plan_data": {
                    "code_inspection_summary": f"[Mock inference] Code inspection for: {entity}",
                    "bug_diagnosis": {
                        "summary": f"[Mock inference] Mock analysis of issue in {entity}",
                        "root_cause": f"[Mock inference] Deterministic mock cannot perform deep analysis of {entity}",
                        "confidence": 0.3,
                    },
                    "patch_plan": {
                        "description": f"[Mock inference] Proposed patch for: {entity}",
                        "files_to_modify": [entity],
                        "approach": "Operator review required — advisory plan only (mock inference)",
                        "estimated_complexity": "medium",
                    },
                    "proposed_diff": f"--- a/{entity}\n+++ b/{entity}\n@@ mock advisory diff @@\n- no changes made\n+ pending operator approval\n",
                    "test_plan": {
                        "strategy": f"Verify fix for {entity} does not introduce regressions",
                        "test_cases": [f"Test that {entity} behaves correctly after patch"],
                        "verification_steps": ["Run existing test suite", "Apply patch in isolated environment first"],
                    },
                    "rollback_plan": f"Revert changes to {entity} via version control; no filesystem changes made by worker",
                    "risk_notes": {
                        "level": "medium",
                        "factors": ["Mock inference — requires human review", "Impact scope not fully determined"],
                        "mitigations": ["Operator approval required before any file mutation", "Patch is advisory artifact only"],
                    },
                },
            }

        elif domain == "execution_plan":
            instruction = input_context.get("instruction", config.get("instruction", f"Plan execution for {entity}"))
            return {
                "_inference_source": "mock",
                "execution_plan_data": {
                    "plan_description": f"[Mock inference] Execution plan for: {entity}",
                    "entity": entity,
                    "steps": [
                        {
                            "step_index": 0,
                            "description": f"Verify prerequisites for {entity}",
                            "command_preview": f"check_prerequisites --entity {entity}",
                            "safety_classification": "safe",
                            "risk_notes": "Read-only verification; no system mutation",
                        },
                    ],
                    "risk_level": "low",
                    "dependency_analysis": {
                        "dependencies": [],
                        "missing": [],
                        "conflicts": [],
                    },
                    "dry_run_summary": f"[SIMULATED] Dry-run for {entity}: 1 step planned, 0 mutations, 0 package installs. No commands executed.",
                    "rollback_plan": f"No mutations planned — rollback is trivial (no state change to revert)",
                    "sandbox_recommendation": "Not applicable — no commands executed in inference mode",
                    "audit_summary": {
                        "execution_authority": "none",
                        "approval_required": True,
                        "commands_executed": 0,
                        "commands_planned": 1,
                        "risk_level": "low",
                    },
                },
            }

        else:
            # Generic mock for unsupported domains
            return {
                "_inference_source": "mock",
                "_mock_domain": domain,
                "topic": topic,
                "operator_brief": f"[Mock inference] Generic mock response for domain '{domain}'. Not a live model call.",
            }


class HermesInferenceAdapter(BaseInferenceAdapter):
    """
    Live inference adapter that calls the host runtime (Hermes) for
    real model-assisted reasoning.

    Currently implements the Ollama-compatible API directly. This is the
    production adapter — it makes real model calls and incurs real cost/latency.

    Implementation notes:
      - Uses OLLAMA_API_KEY env var or config for authentication
      - Falls back to MockInferenceAdapter on auth/connection failure
        if config.fallback_to_deterministic is True
      - All model output is treated as UNTRUSTED until validated
      - Timeout is enforced — no zombie inference calls
    """

    def __init__(self, base_url: str = "https://api.ohmyllama.com", api_key: str = ""):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key or os.environ.get("OLLAMA_API_KEY", "")
        self._available = None  # Lazy check

    @property
    def adapter_type(self) -> str:
        return "hermes"

    def is_available(self) -> bool:
        """Check if Ollama API key is configured."""
        if self._available is not None:
            return self._available
        self._available = bool(self._api_key and self._api_key != "ollama-local")
        return self._available

    def invoke(self, prompt: str, config: dict) -> InferenceResult:
        """
        Invoke a live model through the Ollama-compatible API.

        On failure (auth, network, timeout), returns InferenceResult with
        status=ERROR and no packet. Caller should check fallback_to_deterministic
        config to decide whether to use the deterministic worker.
        """
        if not self.is_available():
            return self._error_result(
                config=config,
                prompt=prompt,
                error_message="Hermes adapter unavailable: no valid OLLAMA_API_KEY configured",
            )

        import subprocess

        domain = config.get("domain", "unknown")
        model = config.get("model", "glm-5.1:cloud")
        provider = config.get("provider", "ollama-cloud")
        timeout_s = config.get("timeout_s", 30.0)
        task_id = config.get("task_id", "task-0000")
        attempt_id = make_inference_attempt_id(domain, task_id)
        prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]

        start_time = time.time()

        try:
            # Use hermes CLI for inference (Hermes is the reference runtime)
            # This keeps OverCR runtime-agnostic: any provider can be swapped
            # by changing the config, without touching doctrine or governance
            result = subprocess.run(
                [
                    sys.executable, "-m", "hermes_tools",
                    "infer",
                    "--model", model,
                    "--prompt", prompt,
                    "--timeout", str(int(timeout_s)),
                    "--format", "json",
                ],
                capture_output=True,
                text=True,
                timeout=timeout_s + 5,  # Grace margin beyond model timeout
            )

            elapsed = time.time() - start_time

            if result.returncode != 0:
                return self._error_result(
                    config=config,
                    prompt=prompt,
                    attempt_id=attempt_id,
                    prompt_hash=prompt_hash,
                    error_message=f"Hermes inference failed (exit={result.returncode}): {result.stderr[:300]}",
                    elapsed=elapsed,
                    timeout_s=timeout_s,
                    model=model,
                    provider=provider,
                )

            # Parse model output
            raw_output = result.stdout.strip()
            if not raw_output:
                return self._error_result(
                    config=config,
                    prompt=prompt,
                    attempt_id=attempt_id,
                    prompt_hash=prompt_hash,
                    error_message="Hermes inference returned empty output",
                    elapsed=elapsed,
                    timeout_s=timeout_s,
                    model=model,
                    provider=provider,
                )

            # Try to parse as JSON (model should return structured output)
            try:
                parsed = json.loads(raw_output)
                if isinstance(parsed, dict):
                    packet = parsed
                else:
                    # Model returned text, not JSON — wrap for manual parsing
                    packet = {"_raw_model_output": raw_output}
            except json.JSONDecodeError:
                # Model returned raw text — inference_worker will handle
                packet = {"_raw_model_output": raw_output}

            # Mark as live inference
            packet["_inference_source"] = "hermes"

            raw_summary = raw_output[:500] if len(raw_output) > 500 else raw_output

            metadata = InferenceMetadata(
                inference_attempt_id=attempt_id,
                domain=domain,
                subagent="knower",
                adapter_type="hermes",
                selected_model=model,
                selected_provider=provider,
                route_used=f"hermes/{domain}",
                prompt_hash=prompt_hash,
                timeout_s=timeout_s,
                elapsed_s=elapsed,
                status=InferenceStatus.SUCCESS,
                fallback_used=False,
                raw_output_summary=raw_summary,
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

    def _error_result(
        self,
        config: dict,
        prompt: str,
        error_message: str,
        attempt_id: str = "",
        prompt_hash: str = "",
        elapsed: float = 0.0,
        timeout_s: float = 30.0,
        model: str = "",
        provider: str = "",
        status: InferenceStatus = InferenceStatus.ERROR,
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
            adapter_type="hermes",
            selected_model=model,
            selected_provider=provider,
            route_used=f"hermes/{domain}",
            prompt_hash=prompt_hash,
            timeout_s=timeout_s,
            elapsed_s=elapsed,
            status=status,
            fallback_used=False,
            error_message=error_message,
        )

        return InferenceResult(
            metadata=metadata,
            packet=None,
            fallback_packet=None,
        )


def get_adapter(adapter_type: str = "mock", **kwargs) -> BaseInferenceAdapter:
    """
    Factory function to get an inference adapter by type.

    Args:
        adapter_type: Adapter type identifier:
            - "mock": MockInferenceAdapter — simulated testing, no real calls
            - "hermes": HermesInferenceAdapter — legacy subprocess adapter (v0.4.1)
            - "hermes_cli": HermesCLIAdapter — real provider calls via Hermes CLI (v0.4.2)
        **kwargs: Additional arguments passed to the adapter constructor

    Returns:
        BaseInferenceAdapter instance

    Raises:
        ValueError: If adapter_type is unknown
    """
    if adapter_type == "mock":
        return MockInferenceAdapter()
    elif adapter_type == "hermes":
        return HermesInferenceAdapter(**kwargs)
    elif adapter_type == "hermes_cli":
        try:
            from runtime.hermes_inference_adapter import HermesCLIAdapter
            return HermesCLIAdapter(**kwargs)
        except ImportError as e:
            raise ValueError(f"Cannot import HermesCLIAdapter: {e}")
    else:
        raise ValueError(f"Unknown inference adapter type: {adapter_type}. "
                         f"Supported: 'mock', 'hermes', 'hermes_cli'")