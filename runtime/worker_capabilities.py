"""
OverCR Runtime — Worker Capabilities (v0.2.1)

Defines and validates worker capability declarations. Each worker must
declare its capabilities at registration time. The runtime uses these
declarations to:

  1. Verify that a worker's claimed capabilities match its actual behavior
     (via healthcheck)
  2. Enforce safety constraints based on capability flags
  3. Route tasks to workers that declare support for the required packet types

Capability flags are immutable once registered — they cannot be upgraded
or downgraded during a session without explicit deregistration and
re-registration.
"""

from dataclasses import dataclass
from typing import Dict, FrozenSet, List, Optional, Set, Tuple

# Re-export capability constants from worker_registry for convenience
from runtime.worker_registry import (
    CAP_NO_NETWORK,
    CAP_NO_SHELL,
    CAP_NO_FILESYSTEM_WRITE,
    CAP_NO_OUTBOUND,
    CAP_READONLY_ANALYSIS,
    WorkerRegistration,
)


# All known capability flags
ALL_CAPABILITY_FLAGS: FrozenSet[str] = frozenset({
    CAP_NO_NETWORK,
    CAP_NO_SHELL,
    CAP_NO_FILESYSTEM_WRITE,
    CAP_NO_OUTBOUND,
    CAP_READONLY_ANALYSIS,
})

# Required capabilities for safe worker operation
# Every worker MUST declare these at minimum
REQUIRED_CAPABILITIES: FrozenSet[str] = frozenset({
    CAP_NO_OUTBOUND,  # Workers must not initiate outbound contact
})

# Expected capabilities for each subagent type
EXPECTED_CAPABILITIES: Dict[str, FrozenSet[str]] = {
    "coder": frozenset({
        CAP_NO_NETWORK, CAP_NO_SHELL, CAP_READONLY_ANALYSIS,
    }),
    "knower": frozenset({
        CAP_NO_NETWORK, CAP_NO_SHELL, CAP_NO_FILESYSTEM_WRITE,
        CAP_NO_OUTBOUND, CAP_READONLY_ANALYSIS,
    }),
    # CryER and PypER will be added when their workers go live
}

CRYER_CAPABILITIES = frozenset({"no_network", "no_shell", "no_fs_write", "no_outbound", "readonly_analysis"})

EXPECTED_CAPABILITIES["cryer"] = CRYER_CAPABILITIES

# Expected packet types per subagent (mirrors task_store.SUBAGENT_PACKET_TYPES)
EXPECTED_PACKET_TYPES: Dict[str, FrozenSet[str]] = {
    "coder": frozenset({"coder_completion", "coder_blocked", "coder_diagnostic", "coder_patch_plan"}),
    "knower": frozenset({"knower_research", "knower_assessment", "knower_myth_separation", "knower_claim_review", "knower_myth_fact"}),
    "cryer": frozenset({"cryer_recon", "cryer_reputation_signal", "cryer_engagement_signal", "cryer_booking_friction", "cryer_directory_completeness", "cryer_hiring_growth"}),
    "pyper": frozenset({"pyper_approval", "pyper_revision", "pyper_objection_response"}),
}


class CapabilityCheckResult:
    """Result of a capability validation check."""

    def __init__(self, valid: bool, errors: List[str] = None, warnings: List[str] = None):
        self.valid = valid
        self.errors = errors or []
        self.warnings = warnings or []

    def to_dict(self) -> dict:
        return {
            "valid": self.valid,
            "errors": self.errors,
            "warnings": self.warnings,
        }


def validate_capabilities(registration: WorkerRegistration) -> CapabilityCheckResult:
    """
    Validate a worker's declared capabilities.

    Checks:
      1. All capability flags are known
      2. Required capabilities are present
      3. For known subagents, capabilities match expected set
    """
    errors: List[str] = []
    warnings: List[str] = []

    # Check for unknown capability flags
    unknown = registration.capability_flags - ALL_CAPABILITY_FLAGS
    if unknown:
        errors.append(f"Unknown capability flags: {sorted(unknown)}")

    # Check required capabilities
    missing_required = REQUIRED_CAPABILITIES - registration.capability_flags
    if missing_required:
        errors.append(
            f"Missing required capabilities: {sorted(missing_required)}. "
            f"All workers must declare at least: {sorted(REQUIRED_CAPABILITIES)}"
        )

    # Check against expected capabilities for known subagents
    expected = EXPECTED_CAPABILITIES.get(registration.subagent)
    if expected is not None:
        # Warnings for mismatches (not errors — workers can exceed expectations)
        missing_expected = expected - registration.capability_flags
        if missing_expected:
            warnings.append(
                f"Worker '{registration.subagent}' is missing expected capabilities: "
                f"{sorted(missing_expected)}. Expected: {sorted(expected)}"
            )

        extra = registration.capability_flags - expected - ALL_CAPABILITY_FLAGS
        # Extra known flags are fine (more restrictive), unknown flags are errors (caught above)

    return CapabilityCheckResult(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
    )


def validate_packet_types(registration: WorkerRegistration) -> CapabilityCheckResult:
    """
    Validate a worker's declared packet types.

    Checks:
      1. At least one packet type is declared
      2. For known subagents, packet types match expected set
    """
    errors: List[str] = []
    warnings: List[str] = []

    if not registration.supported_packet_types:
        errors.append("Worker must declare at least one supported packet type")
        return CapabilityCheckResult(valid=False, errors=errors)

    # Check against expected packet types for known subagents
    expected = EXPECTED_PACKET_TYPES.get(registration.subagent)
    if expected is not None:
        unexpected = registration.supported_packet_types - expected
        if unexpected:
            warnings.append(
                f"Worker '{registration.subagent}' declares unexpected packet types: "
                f"{sorted(unexpected)}. Expected: {sorted(expected)}"
            )

        missing = expected - registration.supported_packet_types
        if missing:
            warnings.append(
                f"Worker '{registration.subagent}' is missing expected packet types: "
                f"{sorted(missing)}"
            )

    return CapabilityCheckResult(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
    )


def get_capability_summary(registration: WorkerRegistration) -> dict:
    """
    Produce a human-readable summary of a worker's capability profile.

    Returns a dict with:
      - capabilities: sorted list of declared capabilities
      - packet_types: sorted list of supported packet types
      - meets_requirements: whether required capabilities are met
      - safety_profile: summary of safety-related capabilities
    """
    caps = sorted(registration.capability_flags)
    pkts = sorted(registration.supported_packet_types)
    meets_required = REQUIRED_CAPABILITIES.issubset(registration.capability_flags)

    safety_flags = []
    if CAP_NO_NETWORK in registration.capability_flags:
        safety_flags.append("no_network")
    if CAP_NO_SHELL in registration.capability_flags:
        safety_flags.append("no_shell")
    if CAP_NO_FILESYSTEM_WRITE in registration.capability_flags:
        safety_flags.append("no_filesystem_write")
    if CAP_NO_OUTBOUND in registration.capability_flags:
        safety_flags.append("no_outbound")
    if CAP_READONLY_ANALYSIS in registration.capability_flags:
        safety_flags.append("readonly_analysis")

    return {
        "subagent": registration.subagent,
        "version": registration.version,
        "capabilities": caps,
        "packet_types": pkts,
        "meets_requirements": meets_required,
        "safety_profile": safety_flags,
        "runtime_compat_version": registration.runtime_compat_version,
    }