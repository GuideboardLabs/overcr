"""
OverCR Runtime — Worker Registry (v0.2.1)

Centralized registry for live subagent workers. Each worker registers
its subagent name, version, supported packet types, capability flags,
and runtime compatibility version. The registry validates compatibility
before invocation and prevents duplicate or conflicting registrations.

Safety guarantees:
  - Duplicate registrations are rejected (same subagent + version)
  - Conflicting registrations are rejected (same subagent, different version,
    unless the existing entry is explicitly deregistered first)
  - Packet type conflicts are rejected (two workers claiming the same packet
    type with different subagent names)
  - Runtime compatibility is checked before invocation
  - Failed registrations never corrupt existing state
"""

from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Optional, Set


RUNTIME_COMPAT_VERSION = "0.2.1"


@dataclass
class WorkerRegistration:
    """A single worker registration entry."""

    subagent: str
    version: str
    supported_packet_types: FrozenSet[str]
    capability_flags: FrozenSet[str]
    runtime_compat_version: str
    worker_path: str  # relative to OverCR root

    def to_dict(self) -> dict:
        return {
            "subagent": self.subagent,
            "version": self.version,
            "supported_packet_types": sorted(self.supported_packet_types),
            "capability_flags": sorted(self.capability_flags),
            "runtime_compat_version": self.runtime_compat_version,
            "worker_path": self.worker_path,
        }


# Known capability flags
CAP_NO_NETWORK = "no_network"           # Worker makes no network calls
CAP_NO_SHELL = "no_shell"               # Worker executes no shell commands
CAP_NO_FILESYSTEM_WRITE = "no_fs_write" # Worker writes nothing outside temp
CAP_NO_OUTBOUND = "no_outbound"         # Worker has no outbound capability
CAP_READONLY_ANALYSIS = "readonly_analysis"  # Worker produces analysis only


# Standard capability sets per subagent
CODER_CAPABILITIES = frozenset({
    CAP_NO_NETWORK, CAP_NO_SHELL, CAP_READONLY_ANALYSIS,
})
KNOWER_CAPABILITIES = frozenset({
    CAP_NO_NETWORK, CAP_NO_SHELL, CAP_NO_FILESYSTEM_WRITE,
    CAP_NO_OUTBOUND, CAP_READONLY_ANALYSIS,
})


class WorkerRegistryError(Exception):
    """Raised when a registration or lookup fails."""
    pass


class WorkerRegistry:
    """
    Centralized registry for subagent workers.

    The registry:
      1. Accepts worker registrations (subagent, version, capabilities, etc.)
      2. Validates that registrations don't conflict
      3. Resolves subagent names to worker registration entries
      4. Checks runtime compatibility before invocation
      5. Rejects packet types claimed by multiple subagents
    """

    def __init__(self, runtime_version: str = RUNTIME_COMPAT_VERSION):
        self._registry: Dict[str, WorkerRegistration] = {}
        self._packet_type_owners: Dict[str, str] = {}
        self._runtime_version = runtime_version

    @property
    def runtime_version(self) -> str:
        return self._runtime_version

    def register(self, registration: WorkerRegistration) -> dict:
        """
        Register a worker. Returns a result dict with success/error info.

        Raises WorkerRegistryError on conflict.
        """
        subagent = registration.subagent

        # Check for exact duplicate
        if subagent in self._registry:
            existing = self._registry[subagent]
            if existing.version == registration.version:
                raise WorkerRegistryError(
                    f"Duplicate registration: subagent '{subagent}' version "
                    f"'{registration.version}' is already registered"
                )
            else:
                raise WorkerRegistryError(
                    f"Conflicting registration: subagent '{subagent}' already "
                    f"registered as version '{existing.version}' — deregister "
                    f"first before registering version '{registration.version}'"
                )

        # Check for packet type conflicts
        for pkt_type in registration.supported_packet_types:
            if pkt_type in self._packet_type_owners:
                owner = self._packet_type_owners[pkt_type]
                raise WorkerRegistryError(
                    f"Packet type conflict: '{pkt_type}' is already owned by "
                    f"subagent '{owner}' — cannot register for '{subagent}'"
                )

        # Check runtime compatibility
        compat_result = self.check_compatibility(registration)
        if not compat_result["compatible"]:
            raise WorkerRegistryError(
                f"Runtime compatibility check failed for '{subagent}': "
                f"{compat_result['reason']}"
            )

        # Register
        self._registry[subagent] = registration
        for pkt_type in registration.supported_packet_types:
            self._packet_type_owners[pkt_type] = subagent

        return {
            "registered": True,
            "subagent": subagent,
            "version": registration.version,
            "packet_types": sorted(registration.supported_packet_types),
            "capability_flags": sorted(registration.capability_flags),
        }

    def deregister(self, subagent: str) -> dict:
        """
        Remove a worker registration. Returns info about what was removed.

        Raises WorkerRegistryError if subagent is not registered.
        """
        if subagent not in self._registry:
            raise WorkerRegistryError(
                f"Cannot deregister: subagent '{subagent}' is not registered"
            )

        removed = self._registry.pop(subagent)
        # Remove packet type ownership
        for pkt_type in removed.supported_packet_types:
            self._packet_type_owners.pop(pkt_type, None)

        return {
            "deregistered": True,
            "subagent": subagent,
            "version": removed.version,
        }

    def lookup(self, subagent: str) -> Optional[WorkerRegistration]:
        """Look up a worker registration by subagent name."""
        return self._registry.get(subagent)

    def is_registered(self, subagent: str) -> bool:
        """Check whether a subagent has a registered worker."""
        return subagent in self._registry

    def list_registrations(self) -> List[WorkerRegistration]:
        """Return all registered workers."""
        return list(self._registry.values())

    def packet_type_owner(self, packet_type: str) -> Optional[str]:
        """Return which subagent owns a given packet type, or None."""
        return self._packet_type_owners.get(packet_type)

    def supports_packet_type(self, subagent: str, packet_type: str) -> bool:
        """Check if a registered subagent supports a specific packet type."""
        reg = self._registry.get(subagent)
        if reg is None:
            return False
        return packet_type in reg.supported_packet_types

    def check_compatibility(self, registration: WorkerRegistration) -> dict:
        """
        Check whether a worker registration is compatible with this runtime.

        Compatibility rules:
          - The worker's runtime_compat_version must match the major.minor
            of the runtime version (patch differences are allowed)
          - The worker must declare at least one supported packet type
          - The worker must declare at least one capability flag
        """
        worker_version = registration.runtime_compat_version
        runtime_version = self._runtime_version

        # Parse major.minor for comparison
        try:
            w_parts = worker_version.split(".")
            r_parts = runtime_version.split(".")
            w_major, w_minor = int(w_parts[0]), int(w_parts[1])
            r_major, r_minor = int(r_parts[0]), int(r_parts[1])
        except (ValueError, IndexError):
            return {
                "compatible": False,
                "reason": f"Cannot parse version numbers: worker={worker_version}, runtime={runtime_version}",
            }

        if w_major != r_major or w_minor != r_minor:
            return {
                "compatible": False,
                "reason": (
                    f"Version mismatch: worker runtime_compat_version "
                    f"'{worker_version}' is not compatible with runtime "
                    f"'{runtime_version}' (major.minor must match)"
                ),
            }

        if not registration.supported_packet_types:
            return {
                "compatible": False,
                "reason": "Worker must declare at least one supported packet type",
            }

        if not registration.capability_flags:
            return {
                "compatible": False,
                "reason": "Worker must declare at least one capability flag",
            }

        return {
            "compatible": True,
            "reason": "Compatible",
            "runtime_version": runtime_version,
            "worker_compat_version": worker_version,
        }

    def get_registration_dict(self, subagent: str) -> Optional[dict]:
        """Return registration as a dict, or None if not found."""
        reg = self.lookup(subagent)
        if reg is None:
            return None
        return reg.to_dict()