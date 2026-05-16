"""
OverCR v2.7.0 — Sandbox Runner (updated)

Adds backend-aware execution to the v2.6 sandbox runner. Accepts
an optional isolation profile and backend selector. The policy
layer runs first (unchanged from v2.6), then the backend is
selected and used for subprocess isolation.

All existing v2.6 behavior is preserved when no backend is
specified (defaults to local backend).
"""

import hashlib
import json
import os
import subprocess
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

from sandbox.command_policy import CommandPolicy, PolicyDecision
from sandbox.filesystem_guard import FilesystemGuard
from sandbox.network_guard import NetworkGuard
from sandbox.rollback_snapshot import RollbackSnapshot
from sandbox.execution_receipt import ExecutionReceipt
from sandbox.allowed_commands import (
    ALLOWED_COMMANDS, is_command_allowed,
)
from sandbox.isolation_profile import IsolationProfile
from sandbox.resource_limits import ResourceLimits
from sandbox.backend_selector import BackendSelector
from sandbox.backends.base_backend import SandboxBackend


class SandboxRunner:
    """
    Governed sandbox execution engine with optional kernel isolation.

    Every execution goes through:
      1. Policy validation (command, args, approval, boundaries)
      2. Network check (default-deny)
      3. Filesystem pre-checks (snapshot creation for mutators)
      4. Backend selection (auto, firejail, bubblewrap, or local)
      5. Subprocess execution through selected backend
      6. Post-execution modification tracking
      7. Receipt generation with backend metadata
    """

    # Commands that mutate the filesystem (trigger snapshot)
    MUTATING_COMMANDS = {"cp", "mv", "mkdir", "rm", "touch", "echo"}

    def __init__(
        self,
        sandbox_root: str,
        selector: Optional[BackendSelector] = None,
    ):
        """
        Args:
            sandbox_root: Absolute path to the sandbox root directory.
            selector: Optional BackendSelector. If None, uses default (local only).
        """
        self.sandbox_root = os.path.abspath(sandbox_root)
        os.makedirs(self.sandbox_root, exist_ok=True)

        self.policy = CommandPolicy(self.sandbox_root)
        self.fs_guard = FilesystemGuard(self.sandbox_root)
        self.net_guard = NetworkGuard(allow_localhost=False)
        self.snapshot = RollbackSnapshot(self.sandbox_root)
        self.selector = selector or BackendSelector()

        self.receipts_dir = os.path.join(self.sandbox_root, ".overcr_receipts")
        self.outputs_dir = os.path.join(self.sandbox_root, ".overcr_outputs")
        os.makedirs(self.receipts_dir, exist_ok=True)
        os.makedirs(self.outputs_dir, exist_ok=True)

    # ── Execution entry point ──────────────────────────────

    def execute_request(
        self,
        command: str,
        argv: list[str],
        operator_identity: str,
        approved_by: str,
        cwd: str = "",
        timeout_s: float = 30.0,
        approval_artifact: Optional[dict] = None,
        purpose: str = "",
        dry_run: bool = False,
        profile: Optional[IsolationProfile] = None,
        limits: Optional[ResourceLimits] = None,
    ) -> dict:
        """
        Execute a governed command in the sandbox.

        Args:
            command: Executable name (must be on allowlist)
            argv: Full argument vector (must start with command)
            operator_identity: Who requested execution
            approved_by: Who approved it
            cwd: Working directory
            timeout_s: Max execution time
            approval_artifact: Operator approval record
            purpose: Stated purpose
            dry_run: If True, validates but does NOT execute
            profile: v2.7 isolation profile (defaults to strict if None)
            limits: v2.7 resource limits (defaults to standard)

        Returns:
            dict with success, receipt, stdout, stderr, error
        """
        execution_id = f"exec-{uuid.uuid4().hex[:8]}"
        start_time = time.time()
        cwd_abs = os.path.abspath(cwd) if cwd else self.sandbox_root

        profile = profile or IsolationProfile.default(self.sandbox_root)
        limits = limits or ResourceLimits(timeout_s=timeout_s)

        # ── 0. Generate initial receipt ──
        receipt = ExecutionReceipt(
            execution_id=execution_id,
            operator_identity=operator_identity,
            approved_by=approved_by,
            executed_command=command,
            argv=argv,
            cwd=cwd_abs,
            exit_code=-1,
            elapsed_s=0,
        )
        receipt.add_audit("execution_requested", {
            "command": command, "argv": argv, "purpose": purpose,
        })

        # ── 1. Policy validation (unchanged from v2.6) ──
        policy_result = self.policy.validate_request(
            command=command, argv=argv, cwd=cwd_abs,
            approval_artifact=approval_artifact, timeout_s=timeout_s,
        )
        receipt.add_audit("policy_validation", {
            "allowed": policy_result.allowed,
            "checks_passed": policy_result.checks_passed,
            "checks_failed": policy_result.checks_failed,
        })

        if not policy_result.allowed:
            receipt.blocked_by_policy = True
            receipt.blocked_reason = policy_result.reason
            receipt.elapsed_s = round(time.time() - start_time, 3)
            receipt.governance_flags["command_allowed"] = False
            self._set_backend_metadata(receipt, "local", profile, limits)
            self._persist_receipt(receipt)
            return self._fail(receipt, f"Policy violation: {policy_result.reason}")

        # ── 2. Network check (unchanged from v2.6) ──
        has_net, net_violations = self.net_guard.is_network_attempt(command, argv)
        if has_net:
            receipt.blocked_by_policy = True
            receipt.blocked_reason = "Network access attempt blocked"
            receipt.elapsed_s = round(time.time() - start_time, 3)
            receipt.governance_flags["network_access_blocked"] = True
            receipt.add_audit("network_blocked", {
                "violations": [v.blocked_target for v in net_violations],
            })
            self._set_backend_metadata(receipt, "local", profile, limits)
            self._persist_receipt(receipt)
            return self._fail(receipt, f"Network access blocked: {[v.reason for v in net_violations]}")

        # ── 3. Filesystem pre-checks ──
        self._do_fs_checks(receipt, argv, cwd_abs, start_time)
        if receipt.blocked_by_policy:
            return self._fail(receipt, receipt.blocked_reason)

        # ── 4. Dry run ──
        if dry_run:
            receipt.elapsed_s = round(time.time() - start_time, 3)
            receipt.add_audit("dry_run_complete", {"elapsed_s": receipt.elapsed_s})
            self._set_backend_metadata(receipt, "local", profile, limits)
            self._persist_receipt(receipt)
            return self._success(receipt)

        # ── 5. Backend selection (v2.7) ──
        backend, sel_meta = self.selector.select(profile)
        receipt.add_audit("backend_selected", sel_meta)

        # Apply backend metadata to receipt
        self._set_backend_metadata(receipt, backend.name, profile, limits,
                                   sel_meta.get("fallback_used", False),
                                   sel_meta.get("fallback_reason", ""))

        # ── 6. Execute through backend ──
        full_argv = backend.build_command(argv, profile)
        exit_code, stdout, stderr, exec_elapsed = backend.execute(
            full_argv, cwd_abs, timeout_s, profile, limits,
        )

        # ── 7. Post-execution tracking ──
        if self.is_mutating(command) and exit_code == 0:
            for arg in argv[1:]:
                if not arg.startswith("-"):
                    target = arg if os.path.isabs(arg) else os.path.join(cwd_abs, arg)
                    if os.path.exists(target):
                        self.fs_guard.record_modification(target)

        # ── 8. Finalize receipt ──
        receipt.exit_code = exit_code
        receipt.elapsed_s = round(exec_elapsed, 3)
        receipt.stdout_hash = hashlib.sha256(
            stdout.encode("utf-8", errors="replace")
        ).hexdigest() if stdout else ""
        receipt.stderr_hash = hashlib.sha256(
            stderr.encode("utf-8", errors="replace")
        ).hexdigest() if stderr else ""
        receipt.modified_paths = self.fs_guard.get_modifications()
        receipt.snapshot_refs = list(set(receipt.snapshot_refs))
        receipt.rollback_available = bool(receipt.snapshot_refs)
        receipt.add_audit("execution_complete", {
            "exit_code": exit_code, "elapsed_s": exec_elapsed,
            "stdout_len": len(stdout), "stderr_len": len(stderr),
            "backend": backend.name,
        })
        receipt.attach_output(stdout, stderr, self.outputs_dir)
        self._persist_receipt(receipt)

        return {
            "success": exit_code == 0,
            "receipt": receipt.to_dict(),
            "stdout": stdout[:2000],
            "stderr": stderr[:2000],
            "error": None if exit_code == 0 else f"exit code {exit_code}",
        }

    # ── Helpers ────────────────────────────────────────────

    def _do_fs_checks(self, receipt, argv, cwd_abs, start_time):
        """Filesystem pre-checks (extracted for clarity)."""
        command = argv[0]
        is_mutator = command in self.MUTATING_COMMANDS or (
            command == "echo" and any(">" in arg for arg in argv)
        )
        if not is_mutator:
            return

        for arg in argv[1:]:
            if arg.startswith("-"):
                continue
            target = arg if os.path.isabs(arg) else os.path.join(cwd_abs, arg)
            allowed, reason = self.fs_guard.validate_write_path(target)
            if not allowed:
                receipt.blocked_by_policy = True
                receipt.blocked_reason = reason
                receipt.elapsed_s = round(time.time() - start_time, 3)
                receipt.governance_flags["sandbox_boundary_intact"] = False
                receipt.add_audit("fs_boundary_violation", {"path": target, "reason": reason})
                return

            snap_id = self.snapshot.create_file_snapshot(target)
            if snap_id:
                receipt.snapshot_refs.append(snap_id)
                receipt.rollback_available = True
                receipt.add_audit("snapshot_created", {"snapshot_id": snap_id, "path": target})

    def _set_backend_metadata(self, receipt, backend_name, profile, limits,
                              fallback_used=False, fallback_reason=""):
        """Set v2.7 backend fields on a receipt."""
        receipt.sandbox_backend = backend_name
        receipt.isolation_profile = profile.to_dict()
        receipt.backend_available = True
        receipt.backend_fallback_used = fallback_used
        receipt.backend_fallback_reason = fallback_reason
        receipt.network_allowed = profile.network_allowed
        receipt.readonly_paths = list(profile.readonly_paths)
        receipt.writable_paths = list(profile.writable_paths)
        receipt.resource_limits = limits.to_dict()

    def _fail(self, receipt, error):
        return {"success": False, "receipt": receipt.to_dict(), "stdout": "", "stderr": "", "error": error}

    def _success(self, receipt):
        return {"success": True, "receipt": receipt.to_dict(), "stdout": "", "stderr": "", "error": None}

    # ── Remaining methods (rollback, receipts, utility) ──
    # Identical to v2.6 — omitted for brevity but present in the full file

    def rollback_changes(self, execution_id: str) -> dict:
        receipt_data = self._load_receipt_data(execution_id)
        if not receipt_data:
            return {"success": False, "error": f"No receipt found for execution {execution_id}"}
        if not receipt_data.get("rollback_available"):
            return {"success": False, "error": "No rollback available for this execution"}

        results = []
        for snap_id in receipt_data.get("snapshot_refs", []):
            ok, msg = self.snapshot.rollback_file(snap_id)
            results.append({"snapshot_id": snap_id, "success": ok, "message": msg})

        all_ok = all(r["success"] for r in results)
        receipt = ExecutionReceipt.from_dict(receipt_data)
        receipt.rollback_executed = all_ok
        receipt.add_audit("rollback_attempted", {"results": results, "all_succeeded": all_ok})
        self._persist_receipt(receipt)
        return {"success": all_ok, "results": results}

    def _persist_receipt(self, receipt):
        path = os.path.join(self.receipts_dir, f"{receipt.execution_id}.json")
        if not os.path.exists(path):
            receipt.to_json(path)

    def _load_receipt_data(self, execution_id):
        path = os.path.join(self.receipts_dir, f"{execution_id}.json")
        if os.path.exists(path):
            with open(path, "r") as f:
                return json.load(f)
        return None

    def get_receipt(self, execution_id):
        return self._load_receipt_data(execution_id)

    def list_receipts(self) -> list[dict]:
        receipts = []
        for fname in sorted(os.listdir(self.receipts_dir)):
            if fname.endswith(".json"):
                with open(os.path.join(self.receipts_dir, fname), "r") as f:
                    receipts.append(json.load(f))
        return receipts

    def is_mutating(self, command: str) -> bool:
        return command in self.MUTATING_COMMANDS
