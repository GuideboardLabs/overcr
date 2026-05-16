"""
OverCR v2.7.0 — Controlled Execution Sandbox with Kernel Isolation

Same v2.6 governance. Optional stronger isolation backends.
Policy layer runs first — backends only handle execution mechanics.

Exports:
  v2.6: AllowedCommands, CommandPolicy, FilesystemGuard, NetworkGuard,
        RollbackSnapshot, ExecutionReceipt, SandboxRunner
  v2.7: IsolationProfile, ResourceLimits, BackendSelector,
        SandboxBackend, LocalBackend, BubblewrapBackend, FirejailBackend
"""

from sandbox.allowed_commands import (
    ALLOWED_COMMANDS, BLOCKED_COMMANDS,
    is_command_allowed, is_command_blocked,
    token_is_blocked, path_is_protected,
)
from sandbox.command_policy import CommandPolicy, PolicyDecision
from sandbox.filesystem_guard import FilesystemGuard
from sandbox.network_guard import NetworkGuard, NetworkCheck
from sandbox.rollback_snapshot import RollbackSnapshot
from sandbox.execution_receipt import ExecutionReceipt
from sandbox.sandbox_runner import SandboxRunner
from sandbox.isolation_profile import IsolationProfile
from sandbox.resource_limits import ResourceLimits
from sandbox.backend_selector import BackendSelector
from sandbox.backends import (
    SandboxBackend, LocalBackend, BubblewrapBackend, FirejailBackend,
)

__all__ = [
    "ALLOWED_COMMANDS", "BLOCKED_COMMANDS",
    "is_command_allowed", "is_command_blocked",
    "token_is_blocked", "path_is_protected",
    "CommandPolicy", "PolicyDecision",
    "FilesystemGuard", "NetworkGuard", "NetworkCheck",
    "RollbackSnapshot", "ExecutionReceipt", "SandboxRunner",
    "IsolationProfile", "ResourceLimits", "BackendSelector",
    "SandboxBackend", "LocalBackend", "BubblewrapBackend", "FirejailBackend",
]

__version__ = "2.7.0"
