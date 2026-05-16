"""
OverCR v2.7.0 — Sandbox Backend (Base Interface)

Abstract base for all sandbox isolation backends. Every backend
must implement this interface. The v2.6 policy layer (CommandPolicy,
NetworkGuard, FilesystemGuard) runs BEFORE any backend — the backend
only handles the execution mechanics, never the policy decisions.
"""

from abc import ABC, abstractmethod
from typing import Optional
from sandbox.isolation_profile import IsolationProfile
from sandbox.resource_limits import ResourceLimits


class SandboxBackend(ABC):
    """
    Abstract base for sandbox isolation backends.

    Policy checks (allowlist, metachar detection, network blocking,
    approval verification) are handled by CommandPolicy BEFORE the
    backend is invoked. The backend is ONLY responsible for execution
    mechanics — never policy decisions.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable backend name: 'local', 'bubblewrap', 'firejail'."""
        ...

    @abstractmethod
    def available(self) -> bool:
        """
        Is this backend available on the current system?

        Checks that required executables exist and are functional.
        Returns True only if the backend can actually execute commands.
        """
        ...

    @abstractmethod
    def build_command(
        self,
        argv: list[str],
        profile: IsolationProfile,
    ) -> list[str]:
        """
        Build the full command vector for this backend.

        Args:
            argv: The user's command argv (e.g., ['ls', '-la'])
            profile: Isolation profile with network/fs/resource config

        Returns:
            Full argv list ready for subprocess.run(shell=False).
            May prepend backend wrapper args (bwrap, firejail, etc.).

        Never uses shell=True or string-based command construction.
        """
        ...

    @abstractmethod
    def execute(
        self,
        argv: list[str],
        cwd: str,
        timeout_s: float,
        profile: IsolationProfile,
        limits: ResourceLimits,
    ) -> tuple[int, str, str, float]:
        """
        Execute a command through this backend.

        Args:
            argv: Full command argv (including any backend wrappers)
            cwd: Working directory
            timeout_s: Max execution time
            profile: Isolation profile (for audit, not enforcement here)
            limits: Resource limits to apply

        Returns:
            (exit_code, stdout, stderr, elapsed_s)
        """
        ...

    @abstractmethod
    def describe_isolation(self) -> str:
        """
        Human-readable description of the isolation this backend provides.
        Used in audit records and operator dashboards.
        """
        ...

    def supports_network_block(self) -> bool:
        """Does this backend provide kernel-level network isolation?"""
        return False

    def supports_readonly_mounts(self) -> bool:
        """Does this backend support readonly bind mounts?"""
        return False

    def supports_resource_limits(self) -> bool:
        """Does this backend support resource limits beyond timeout?"""
        return False
