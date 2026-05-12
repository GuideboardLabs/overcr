#!/usr/bin/env python3
"""
OverCR v0.4.1 Inference Result
================================

Data structures for capturing inference (model-assisted reasoning) results
within the OverCR orchestration substrate.

Inference results are UNTRUSTED until validated through the 6-level packet
validator. They carry metadata for audit trails, governance enforcement,
and fallback routing.

Key invariant: inference failure MUST NOT advance task state.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class InferenceStatus(Enum):
    """Status of an inference attempt."""
    SUCCESS = "success"               # Model returned a usable response
    FALLBACK_USED = "fallback_used"     # Deterministic worker used (inference failed)
    TIMEOUT = "timeout"                 # Model call timed out
    ERROR = "error"                     # Model call errored (auth, network, etc.)
    MALFORMED_OUTPUT = "malformed"      # Model returned unparseable output
    VALIDATION_FAILED = "validation_failed"  # Model output parsed but failed L1-L6


@dataclass
class InferenceMetadata:
    """
    Audit-trail metadata for a single inference attempt.

    Recorded in the task audit log alongside packet validation results.
    This metadata is governance-transparent: the operator can see exactly
    which model was used, whether fallback occurred, and why.
    """
    inference_attempt_id: str = ""
    domain: str = ""
    subagent: str = ""
    adapter_type: str = ""           # "mock" | "hermes"
    selected_model: str = ""
    selected_provider: str = ""
    route_used: str = ""
    prompt_hash: str = ""            # SHA-256 hash of the rendered prompt
    timeout_s: float = 30.0
    elapsed_s: float = 0.0
    status: InferenceStatus = InferenceStatus.ERROR
    fallback_used: bool = False
    raw_output_summary: str = ""     # Truncated, audit-safe summary of raw model output
    sanitized_output_summary: str = ""  # Truncated, audit-safe summary of sanitized JSON output (v0.4.3)
    sanitizer_info: dict = field(default_factory=dict)  # Sanitizer audit: method, input/output lengths (v0.4.3)
    validation_result: Optional[dict] = None  # {valid: bool, errors: [...], warnings: [...]}
    error_message: str = ""

    def to_dict(self) -> dict:
        """Serialize to dict for audit trail storage."""
        return {
            "inference_attempt_id": self.inference_attempt_id,
            "domain": self.domain,
            "subagent": self.subagent,
            "adapter_type": self.adapter_type,
            "selected_model": self.selected_model,
            "selected_provider": self.selected_provider,
            "route_used": self.route_used,
            "prompt_hash": self.prompt_hash,
            "timeout_s": self.timeout_s,
            "elapsed_s": round(self.elapsed_s, 3),
            "status": self.status.value,
            "fallback_used": self.fallback_used,
            "raw_output_summary": self.raw_output_summary[:500],  # Hard audit cap
            "sanitized_output_summary": self.sanitized_output_summary[:500],  # v0.4.3
            "sanitizer_info": self.sanitizer_info,  # v0.4.3
            "validation_result": self.validation_result,
            "error_message": self.error_message[:500],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "InferenceMetadata":
        """Deserialize from dict."""
        d = dict(d)  # Copy to avoid mutation
        d["status"] = InferenceStatus(d.get("status", "error"))
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class InferenceResult:
    """
    Complete result of an inference attempt, including the produced packet
    (if any) and all metadata.

    This is the interface between the inference adapter and the runtime.
    The runtime uses InferenceResult to decide:
      - If result.packet is not None → proceed to validation
      - If result.fallback_packet is not None → use deterministic fallback
      - If both are None → task stays in safe state (in_progress)
    """
    metadata: InferenceMetadata = field(default_factory=InferenceMetadata)
    packet: Optional[dict] = None           # Model-produced packet (untrusted until validated)
    fallback_packet: Optional[dict] = None   # Deterministic fallback packet (also validated)

    @property
    def success(self) -> bool:
        """Whether the inference produced a packet (may still fail validation)."""
        return self.metadata.status in (
            InferenceStatus.SUCCESS,
            InferenceStatus.FALLBACK_USED,
        )

    @property
    def used_fallback(self) -> bool:
        """Whether the deterministic fallback was used instead of inference."""
        return self.metadata.fallback_used

    def primary_packet(self) -> Optional[dict]:
        """
        Return the best available packet:
          1. If inference succeeded → model-produced packet
          2. If inference failed but fallback available → deterministic packet
          3. Otherwise → None (task must not advance)
        """
        if self.metadata.status == InferenceStatus.SUCCESS and self.packet is not None:
            return self.packet
        if self.fallback_packet is not None:
            return self.fallback_packet
        return None

    def to_dict(self) -> dict:
        """Serialize to dict for audit/logging."""
        return {
            "metadata": self.metadata.to_dict(),
            "packet": self.packet,
            "fallback_packet": self.fallback_packet,
        }


def make_inference_attempt_id(domain: str, task_id: str) -> str:
    """
    Generate a deterministic inference attempt ID.

    Format: inf-{domain}-{task_id}-{timestamp_ms}
    """
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")[:18]
    return f"inf-{domain}-{task_id}-{ts}"