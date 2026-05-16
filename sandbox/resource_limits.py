"""
OverCR v2.7.0 — Resource Limits

Portable soft limits for sandbox execution. No hard dependency on
cgroups or kernel features. Implemented through subprocess-level
controls (timeout, output truncation) with placeholders for future
cgroup integration.
"""

from dataclasses import dataclass, field, asdict


@dataclass
class ResourceLimits:
    """
    Resource constraints for sandbox execution.

    All limits are soft — they are enforced at the subprocess level
    (timeout via signal, output via truncation). CPU and memory
    limits are placeholders for future cgroup integration.
    """

    # Time (enforced via subprocess.run timeout)
    timeout_s: float = 30.0

    # Output (enforced via string truncation post-capture)
    max_stdout_bytes: int = 1_048_576   # 1 MB
    max_stderr_bytes: int = 1_048_576   # 1 MB

    # Future cgroup placeholders (not enforced in v2.7)
    max_memory_bytes: int = 0  # 0 = no limit
    max_cpu_seconds: float = 0.0  # 0 = no limit
    max_processes: int = 0  # 0 = no limit

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ResourceLimits":
        return cls(
            timeout_s=data.get("timeout_s", 30.0),
            max_stdout_bytes=data.get("max_stdout_bytes", 1_048_576),
            max_stderr_bytes=data.get("max_stderr_bytes", 1_048_576),
            max_memory_bytes=data.get("max_memory_bytes", 0),
            max_cpu_seconds=data.get("max_cpu_seconds", 0.0),
            max_processes=data.get("max_processes", 0),
        )

    @classmethod
    def strict(cls, timeout_s: float = 10.0) -> "ResourceLimits":
        """Create strict limits for untrusted execution."""
        return cls(
            timeout_s=timeout_s,
            max_stdout_bytes=64_000,
            max_stderr_bytes=64_000,
        )

    def truncate_stdout(self, stdout: str) -> str:
        """Truncate stdout to max bytes."""
        if len(stdout.encode("utf-8", errors="replace")) > self.max_stdout_bytes:
            return stdout[:self.max_stdout_bytes // 2]  # Conservative: half for multi-byte safety
        return stdout

    def truncate_stderr(self, stderr: str) -> str:
        """Truncate stderr to max bytes."""
        if len(stderr.encode("utf-8", errors="replace")) > self.max_stderr_bytes:
            return stderr[:self.max_stderr_bytes // 2]
        return stderr
