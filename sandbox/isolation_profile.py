"""
OverCR v2.7.0 — Isolation Profile

Defines the isolation configuration for a sandbox execution.
Serializable, auditable, and immutable once created. Every field
is recorded in the execution receipt.

The profile defines what is allowed, not what the command attempts.
The backend enforces it; the profile declares the intent.
"""

from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class IsolationProfile:
    """
    Declarative isolation configuration for a sandbox execution.

    Serialized into every receipt. The profile is the operator's
    stated intent; the backend enforcement in the receipt proves
    whether it was honored.
    """
    # Network
    network_allowed: bool = False

    # Filesystem
    readonly_paths: list[str] = field(default_factory=list)
    writable_paths: list[str] = field(default_factory=list)
    temp_root: str = ""

    # Resource limits
    max_runtime_s: float = 30.0
    max_output_bytes: int = 1048576

    # Process visibility
    allow_proc: bool = False
    allow_dev: bool = False

    # Backend preference
    backend_preference: str = "auto"  # auto | local | bubblewrap | firejail
    fallback_allowed: bool = True
    fallback_reason: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "IsolationProfile":
        return cls(
            network_allowed=data.get("network_allowed", False),
            readonly_paths=data.get("readonly_paths", []),
            writable_paths=data.get("writable_paths", []),
            temp_root=data.get("temp_root", ""),
            max_runtime_s=data.get("max_runtime_s", 30.0),
            max_output_bytes=data.get("max_output_bytes", 1048576),
            allow_proc=data.get("allow_proc", False),
            allow_dev=data.get("allow_dev", False),
            backend_preference=data.get("backend_preference", "auto"),
            fallback_allowed=data.get("fallback_allowed", True),
            fallback_reason=data.get("fallback_reason", ""),
        )

    @classmethod
    def default(cls, sandbox_root: str = "") -> "IsolationProfile":
        """Create a strict default profile (network=off, proc=off, dev=off)."""
        return cls(
            network_allowed=False,
            writable_paths=[sandbox_root] if sandbox_root else [],
            temp_root=sandbox_root,
            max_runtime_s=30.0,
            max_output_bytes=1048576,
            allow_proc=False,
            allow_dev=False,
            backend_preference="auto",
            fallback_allowed=True,
        )
