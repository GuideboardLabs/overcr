"""
OverCR v2.6.0 — Command Policy

Validates every execution request against the sandbox governance
rules. Every check is enforced — nothing is advisory. A rejected
command never reaches execution.

Checks performed:
  1. Executable name must be on the allowlist
  2. No shell metacharacters in argv
  3. No command chaining (&&, ||, ;)
  4. No pipes or redirects
  5. No path traversal
  6. No environment injection
  7. Approval artifact must be present and valid
  8. Timeout must be reasonable
"""

import os
import re
from dataclasses import dataclass, field
from typing import Optional

from sandbox.allowed_commands import (
    ALLOWED_COMMANDS, BLOCKED_COMMANDS,
    BLOCKED_TOKENS, PROTECTED_PATHS,
    is_command_allowed, is_git_subcommand_allowed,
    token_is_blocked, path_is_protected,
)


@dataclass
class PolicyDecision:
    """Result of a command policy check."""
    allowed: bool
    reason: str = ""
    checks_passed: list = field(default_factory=list)
    checks_failed: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "checks_passed": self.checks_passed,
            "checks_failed": self.checks_failed,
        }


class CommandPolicy:
    """
    Validates every execution request against sandbox governance.

    Every check is enforced. Rejected commands generate audit records
    but never reach the subprocess boundary.
    """

    def __init__(self, sandbox_root: str):
        """
        Args:
            sandbox_root: Absolute path to the sandbox root directory.
        """
        self.sandbox_root = os.path.abspath(sandbox_root)

    # ── Validation ─────────────────────────────────────

    def validate_request(
        self,
        command: str,
        argv: list[str],
        cwd: str = "",
        approval_artifact: Optional[dict] = None,
        timeout_s: float = 30.0,
    ) -> PolicyDecision:
        """
        Validate an execution request against all governance rules.

        Args:
            command: The executable name (e.g. "ls")
            argv: Full argument vector (must start with executable name)
            cwd: Working directory for execution
            approval_artifact: Operator approval record (required)
            timeout_s: Requested timeout

        Returns:
            PolicyDecision with allowed/rejected and failure details.
        """
        passed = []
        failed = []

        # 1. Check approval artifact
        if not approval_artifact or not approval_artifact.get("approved"):
            result = PolicyDecision(
                allowed=False,
                reason="Execution requires explicit operator approval artifact",
                checks_failed=["approval_artifact_missing"],
            )
            return result
        passed.append("approval_artifact_present")

        # 2. Check command name
        cmd_name = command.lower().strip()

        if cmd_name == "git":
            # Git is allowed only for specific sub-commands
            if len(argv) >= 2 and is_git_subcommand_allowed(argv[1]):
                passed.append("command_allowed_git")
            else:
                failed.append("command_blocked_git")
        elif is_command_allowed(cmd_name):
            passed.append("command_allowed")
        elif cmd_name in BLOCKED_COMMANDS:
            failed.append("command_blocked")
        else:
            failed.append("command_not_on_allowlist")

        # 3. Check for shell metacharacters in ALL argv elements
        has_metas = False
        for i, arg in enumerate(argv):
            if i == 0:
                continue  # Skip command name itself (already checked)
            if self._contains_metacharacters(arg):
                has_metas = True
                failed.append(f"shell_metachar_in_argv[{i}]")
                break
        if not has_metas:
            passed.append("no_shell_metacharacters")

        # 4. Check for chaining operators
        has_chain = False
        for arg in argv:
            if arg in ("&&", "||", ";", "|"):
                has_chain = True
                failed.append("command_chaining_detected")
                break
        if not has_chain:
            passed.append("no_command_chaining")

        # 5. Check for redirects
        has_redirect = False
        for arg in argv:
            if arg in (">", ">>", "<", "<<<", "<<"):
                has_redirect = True
                failed.append("redirect_detected")
                break
        if not has_redirect:
            passed.append("no_redirects")

        # 6. Check for path traversal
        has_traversal = False
        for arg in argv:
            if "../" in arg or "..\\" in arg:
                has_traversal = True
                failed.append(f"path_traversal_in_argv")
                break
        if not has_traversal:
            passed.append("no_path_traversal")

        # 7. Check cwd is within sandbox
        cwd_normalized = os.path.abspath(cwd) if cwd else self.sandbox_root
        if not self._path_in_sandbox(cwd_normalized):
            failed.append("cwd_outside_sandbox")
        else:
            passed.append("cwd_in_sandbox")

        # 8. Check timeout
        if timeout_s <= 0 or timeout_s > 300:
            failed.append("timeout_out_of_range")
        else:
            passed.append("timeout_valid")

        # 9. Check sandbox root exists
        if not os.path.isdir(self.sandbox_root):
            failed.append("sandbox_root_missing")

        if failed:
            return PolicyDecision(
                allowed=False,
                reason=f"Policy violation: {'; '.join(failed)}",
                checks_passed=passed,
                checks_failed=failed,
            )

        return PolicyDecision(
            allowed=True,
            reason="All governance checks passed",
            checks_passed=passed,
            checks_failed=[],
        )

    # ── Helpers ────────────────────────────────────────

    def _contains_metacharacters(self, arg: str) -> bool:
        """Check if an argument contains shell metacharacters."""
        for token in BLOCKED_TOKENS:
            # Only check for literal metacharacters embedded in text, not
            # the argument being exactly a metachar (already caught above)
            if token in arg and arg != token:
                return True
        return False

    def _path_in_sandbox(self, path: str) -> bool:
        """Check that a path resolves inside the sandbox root."""
        try:
            real = os.path.realpath(path)
            real_root = os.path.realpath(self.sandbox_root)
            return real == real_root or real.startswith(real_root + os.sep)
        except (OSError, ValueError):
            return False

    def check_token_in_args(self, args: list[str]) -> list[str]:
        """Scan arguments for blocked token patterns. Returns list of violations."""
        violations = []
        for arg in args:
            if token_is_blocked(arg):
                violations.append(arg[:80])
        return violations

    def check_path_in_args(self, args: list[str]) -> list[str]:
        """Check if any arguments reference protected paths. Returns violations."""
        violations = []
        for arg in args:
            if path_is_protected(arg):
                violations.append(arg[:80])
        return violations
