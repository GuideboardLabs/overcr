"""
OverCR v2.7.0 — Local Backend

The default fallback backend. Wraps the existing v2.6
subprocess.run(shell=False) behavior with the Backend interface.
Always available, supports no kernel-level isolation features.
"""

import subprocess
import time
from sandbox.backends.base_backend import SandboxBackend
from sandbox.isolation_profile import IsolationProfile
from sandbox.resource_limits import ResourceLimits


class LocalBackend(SandboxBackend):
    """
    Default fallback backend — no kernel isolation.

    Uses subprocess.run(shell=False) exactly as v2.6. Always
    available. Supports zero kernel-level features but applies
    all v2.6 policy checks before execution.
    """

    @property
    def name(self) -> str:
        return "local"

    def available(self) -> bool:
        return True  # Always available

    def build_command(
        self,
        argv: list[str],
        profile: IsolationProfile,
    ) -> list[str]:
        # No wrapper — pass through directly
        return list(argv)

    def execute(
        self,
        argv: list[str],
        cwd: str,
        timeout_s: float,
        profile: IsolationProfile,
        limits: ResourceLimits,
    ) -> tuple[int, str, str, float]:
        start = time.time()
        stdout = ""
        stderr = ""
        exit_code = -1

        try:
            proc = subprocess.run(
                argv,
                cwd=cwd,
                timeout=timeout_s,
                capture_output=True,
                shell=False,
                env={},
            )
            stdout = proc.stdout.decode("utf-8", errors="replace")
            stderr = proc.stderr.decode("utf-8", errors="replace")
            exit_code = proc.returncode
        except subprocess.TimeoutExpired:
            exit_code = -2
            stderr = f"Timeout after {timeout_s}s"
        except Exception as e:
            exit_code = -3
            stderr = str(e)

        elapsed = time.time() - start

        # Apply output truncation
        stdout = limits.truncate_stdout(stdout)
        stderr = limits.truncate_stderr(stderr)

        return exit_code, stdout, stderr, elapsed

    def describe_isolation(self) -> str:
        return (
            "local (no kernel isolation): subprocess.run(shell=False), "
            "argv-only, empty environment, timeout enforced. "
            "No network blocking at kernel level — relies on CommandPolicy "
            "argument scanning for network detection."
        )

    def supports_network_block(self) -> bool:
        return False

    def supports_readonly_mounts(self) -> bool:
        return False

    def supports_resource_limits(self) -> bool:
        return False
