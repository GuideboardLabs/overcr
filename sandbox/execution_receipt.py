"""
OverCR v2.6.0 — Execution Receipt

The canonical audit record of every sandbox execution. Each execution
produces exactly one receipt. Receipts are append-only and never
deleted. They track what ran, when, by whose authority, and every
governance flag that was checked.

Receipts are JSON-serializable and stored in filesystem records.
Every field is auditable.
"""

import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Optional


class ExecutionReceipt:
    """
    Immutable record of a single sandbox execution.

    Contains every field needed for audit: operator identity,
    approval chain, command details, output hashes, timing,
    filesystem modifications, and rollback state.
    """

    def __init__(
        self,
        execution_id: str,
        operator_identity: str,
        approved_by: str,
        executed_command: str,
        argv: list[str],
        cwd: str,
        exit_code: int,
        elapsed_s: float,
        stdout: str = "",
        stderr: str = "",
        timeout_occurred: bool = False,
        blocked_by_policy: bool = False,
        blocked_reason: str = "",
    ):
        self.execution_id = execution_id
        self.operator_identity = operator_identity
        self.approved_by = approved_by
        self.executed_command = executed_command
        self.argv = list(argv)
        self.cwd = cwd
        self.timestamp = datetime.now(timezone.utc).isoformat()
        self.exit_code = exit_code
        self.elapsed_s = round(elapsed_s, 3)

        # Output hashing (never stores full output inline by default)
        self.stdout_hash = hashlib.sha256(
            stdout.encode("utf-8", errors="replace")
        ).hexdigest() if stdout else ""
        self.stderr_hash = hashlib.sha256(
            stderr.encode("utf-8", errors="replace")
        ).hexdigest() if stderr else ""

        self.stdout_truncated = len(stdout) > 10000
        self.stderr_truncated = len(stderr) > 10000

        # Execution artifacts (stored externally)
        self.stdout_path: str = ""
        self.stderr_path: str = ""

        # Timing and status
        self.timeout_occurred = timeout_occurred
        self.blocked_by_policy = blocked_by_policy
        self.blocked_reason = blocked_reason

        # Filesystem impact
        self.modified_paths: list[str] = []
        self.snapshot_refs: list[str] = []

        # Rollback
        self.rollback_available: bool = False
        self.rollback_executed: bool = False

        # Governance flags
        self.governance_flags: dict[str, bool] = {
            "command_allowed": True,
            "shell_metacharacters_blocked": True,
            "path_traversal_blocked": True,
            "network_access_blocked": True,
            "sandbox_boundary_intact": True,
            "filesystem_mutation_tracked": True,
        }

        # v2.7.0 — Isolation backend metadata
        self.sandbox_backend: str = "local"
        self.isolation_profile: dict = {}
        self.backend_available: bool = True
        self.backend_fallback_used: bool = False
        self.backend_fallback_reason: str = ""
        self.network_allowed: bool = False
        self.readonly_paths: list[str] = []
        self.writable_paths: list[str] = []
        self.resource_limits: dict = {}

        # Audit
        self.audit_entries: list[dict] = []

    def add_audit(self, entry_type: str, details: dict):
        """Append an audit entry (never removed)."""
        self.audit_entries.append({
            "type": entry_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "details": details,
        })

    def attach_output(self, stdout: str, stderr: str, output_dir: str):
        """Write stdout/stderr to files and record paths."""
        os.makedirs(output_dir, exist_ok=True)

        if stdout:
            sp = os.path.join(output_dir, f"{self.execution_id}_stdout.txt")
            with open(sp, "w") as f:
                f.write(stdout)
            self.stdout_path = sp

        if stderr:
            ep = os.path.join(output_dir, f"{self.execution_id}_stderr.txt")
            with open(ep, "w") as f:
                f.write(stderr)
            self.stderr_path = ep

    def to_dict(self) -> dict:
        """Full serializable receipt dict."""
        return {
            "execution_id": self.execution_id,
            "operator_identity": self.operator_identity,
            "approved_by": self.approved_by,
            "executed_command": self.executed_command,
            "argv": self.argv,
            "timestamp": self.timestamp,
            "cwd": self.cwd,
            "exit_code": self.exit_code,
            "elapsed_s": self.elapsed_s,
            "stdout_hash": self.stdout_hash,
            "stderr_hash": self.stderr_hash,
            "stdout_truncated": self.stdout_truncated,
            "stderr_truncated": self.stderr_truncated,
            "modified_paths": self.modified_paths,
            "snapshot_refs": self.snapshot_refs,
            "rollback_available": self.rollback_available,
            "rollback_executed": self.rollback_executed,
            "timeout_occurred": self.timeout_occurred,
            "blocked_by_policy": self.blocked_by_policy,
            "blocked_reason": self.blocked_reason,
            "governance_flags": self.governance_flags,
            "audit_entries": self.audit_entries,
            # v2.7.0 backend fields
            "sandbox_backend": self.sandbox_backend,
            "isolation_profile": self.isolation_profile,
            "backend_available": self.backend_available,
            "backend_fallback_used": self.backend_fallback_used,
            "backend_fallback_reason": self.backend_fallback_reason,
            "network_allowed": self.network_allowed,
            "readonly_paths": self.readonly_paths,
            "writable_paths": self.writable_paths,
            "resource_limits": self.resource_limits,
        }

    def to_json(self, path: Optional[str] = None) -> str:
        """Serialize receipt to JSON string or file."""
        data = self.to_dict()
        jstr = json.dumps(data, indent=2)
        if path:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f:
                f.write(jstr)
        return jstr

    @classmethod
    def from_dict(cls, data: dict) -> "ExecutionReceipt":
        """Deserialize from dict."""
        r = cls(
            execution_id=data["execution_id"],
            operator_identity=data["operator_identity"],
            approved_by=data["approved_by"],
            executed_command=data["executed_command"],
            argv=data["argv"],
            cwd=data["cwd"],
            exit_code=data["exit_code"],
            elapsed_s=data.get("elapsed_s", 0),
        )
        r.timestamp = data.get("timestamp", r.timestamp)
        r.stdout_hash = data.get("stdout_hash", "")
        r.stderr_hash = data.get("stderr_hash", "")
        r.stdout_truncated = data.get("stdout_truncated", False)
        r.stderr_truncated = data.get("stderr_truncated", False)
        r.modified_paths = data.get("modified_paths", [])
        r.snapshot_refs = data.get("snapshot_refs", [])
        r.rollback_available = data.get("rollback_available", False)
        r.rollback_executed = data.get("rollback_executed", False)
        r.timeout_occurred = data.get("timeout_occurred", False)
        r.blocked_by_policy = data.get("blocked_by_policy", False)
        r.blocked_reason = data.get("blocked_reason", "")
        r.governance_flags = data.get("governance_flags", r.governance_flags)
        r.audit_entries = data.get("audit_entries", [])
        # v2.7.0 backend fields
        r.sandbox_backend = data.get("sandbox_backend", "local")
        r.isolation_profile = data.get("isolation_profile", {})
        r.backend_available = data.get("backend_available", True)
        r.backend_fallback_used = data.get("backend_fallback_used", False)
        r.backend_fallback_reason = data.get("backend_fallback_reason", "")
        r.network_allowed = data.get("network_allowed", False)
        r.readonly_paths = data.get("readonly_paths", [])
        r.writable_paths = data.get("writable_paths", [])
        r.resource_limits = data.get("resource_limits", {})
        return r
