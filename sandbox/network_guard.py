"""
OverCR v2.6.0 — Network Guard

Default-deny all outbound network access from the sandbox.
No socket creation allowed. No DNS resolution for external hosts.
No connection to localhost services. Every attempted network
use is recorded in the audit trail.

This is a policy-level guard — it intercepts at the command
validation layer. Future versions may integrate with kernel-level
isolation (Firejail, Bubblewrap, seccomp).
"""

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class NetworkCheck:
    """Result of a network access check."""
    allowed: bool
    reason: str = ""
    blocked_target: str = ""


class NetworkGuard:
    """
    Default-deny network access for sandbox commands.

    All network operations are blocked unless explicitly whitelisted
    (there is no whitelist in v2.6.0 — all network is denied).

    Detection methods:
      - Blocked command names (curl, wget, ssh, nc, etc.)
      - URL patterns in arguments
      - IP address patterns in arguments
      - Hostname patterns that suggest network targets
    """

    # Patterns indicating network access attempts
    URL_PATTERN = re.compile(
        r"(?:https?|ftp|sftp|ssh|git|rsync|telnet)://[^\s]+", re.IGNORECASE
    )
    IP_PATTERN = re.compile(
        r"\b(?:\d{1,3}\.){3}\d{1,3}\b(?::\d+)?"
    )
    DOMAIN_PATTERN = re.compile(
        r"\b(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}\b",
        re.IGNORECASE,
    )

    # Localhost addresses
    LOCALHOST_PATTERNS = [
        "127.0.0.1", "::1", "localhost", "0.0.0.0",
    ]

    def __init__(self, allow_localhost: bool = False):
        """
        Args:
            allow_localhost: If True, localhost connections are allowed.
                            Default: False (blocked).
        """
        self.allow_localhost = allow_localhost

    def check_command(self, command: str) -> NetworkCheck:
        """
        Check if a command is a network-access tool.

        Returns: NetworkCheck with allowed=False if command is blocked.
        """
        blocked_net_cmds = {
            "curl", "wget", "ssh", "scp", "sftp", "rsync",
            "nc", "ncat", "netcat", "telnet", "ftp",
            "git",  # Git has network capabilities; sub-commands are gated separately
            "ping", "traceroute", "tracert", "nslookup", "dig", "host",
            "http", "https",  # Rare but possible as command aliases
        }

        if command.lower().strip() in blocked_net_cmds:
            return NetworkCheck(
                allowed=False,
                reason=f"Network-access command '{command}' is blocked",
                blocked_target=command,
            )

        return NetworkCheck(allowed=True)

    def check_args(self, args: list[str]) -> list[NetworkCheck]:
        """
        Scan command arguments for network-access patterns.

        Returns: List of NetworkCheck results (empty if clean).
        """
        violations = []

        for arg in args:
            # URL patterns
            url_match = self.URL_PATTERN.search(arg)
            if url_match:
                violations.append(NetworkCheck(
                    allowed=False,
                    reason=f"URL pattern in argument: {url_match.group()}",
                    blocked_target=url_match.group()[:80],
                ))

            # IP address patterns
            ip_match = self.IP_PATTERN.search(arg)
            if ip_match:
                ip = ip_match.group()
                # Check if it's localhost
                for lh in self.LOCALHOST_PATTERNS:
                    if ip.startswith(lh):
                        if not self.allow_localhost:
                            violations.append(NetworkCheck(
                                allowed=False,
                                reason=f"Localhost access blocked: {ip}",
                                blocked_target=ip,
                            ))
                        break
                else:
                    violations.append(NetworkCheck(
                        allowed=False,
                        reason=f"IP address in argument (potential network target): {ip}",
                        blocked_target=ip,
                    ))

            # Domain name patterns (heuristic — may false-positive on filenames)
            # Only flag when combined with network-relevant context
            domain_match = self.DOMAIN_PATTERN.search(arg)
            if domain_match:
                domain = domain_match.group()
                # Check for network-relevant context words
                context_words = {
                    "connect", "download", "upload", "fetch", "pull", "push",
                    "remote", "server", "proxy", "api", "host", "endpoint",
                }
                arg_lower = arg.lower()
                if any(w in arg_lower for w in context_words):
                    violations.append(NetworkCheck(
                        allowed=False,
                        reason=f"Domain with network context: {domain}",
                        blocked_target=domain[:80],
                    ))

        return violations

    def is_network_attempt(self, command: str, args: list[str]) -> tuple[bool, list[NetworkCheck]]:
        """
        Comprehensive check: is this execution attempting network access?

        Returns: (has_violation, list_of_violations)
        """
        violations = []

        cmd_check = self.check_command(command)
        if not cmd_check.allowed:
            violations.append(cmd_check)

        violations.extend(self.check_args(args))

        return len(violations) > 0, violations
