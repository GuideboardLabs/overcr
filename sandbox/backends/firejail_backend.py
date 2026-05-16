"""
OverCR v2.7.0 — Firejail Backend

Optional isolation backend using firejail. Available only if
firejail is installed. Provides profile-based kernel isolation
with private working directory, net=none, and readonly restrictions.

Never required. Always falls back to local if unavailable.
"""

import os
import shutil
import subprocess
import time
from sandbox.backends.base_backend import SandboxBackend
from sandbox.isolation_profile import IsolationProfile
from sandbox.resource_limits import ResourceLimits


class FirejailBackend(SandboxBackend):
    """
    Kernel isolation backend via firejail.

    Provides:
      - Private working directory (--private=)
      - No network (--net=none)
      - Readonly restrictions (--read-only=)
      - Seccomp filtering (firejail default)
      - Timeout enforced

    Not installed or required — detection at runtime.
    """

    FIREJAIL_BIN = "firejail"

    @property
    def name(self) -> str:
        return "firejail"

    def available(self) -> bool:
        """Check that firejail exists and is executable."""
        return shutil.which(self.FIREJAIL_BIN) is not None

    def build_command(
        self,
        argv: list[str],
        profile: IsolationProfile,
    ) -> list[str]:
        """
        Build a firejail command vector. Never uses string construction.

        Typical firejail invocation:
          firejail --net=none --private=/tmp/sandbox --read-only=/usr
                    --timeout=00:00:30 -- /command arg1 arg2
        """
        cmd = [self.FIREJAIL_BIN]

        # Network isolation
        if not profile.network_allowed:
            cmd.append("--net=none")

        # Private working directory
        if profile.temp_root:
            cmd.extend(["--private=" + profile.temp_root])
        elif profile.writable_paths:
            cmd.extend(["--private=" + profile.writable_paths[0]])

        # Readonly paths from profile
        for rpath in profile.readonly_paths:
            if os.path.exists(rpath):
                cmd.append(f"--read-only={rpath}")

        # No D-Bus (avoid host service access)
        cmd.append("--nodbus")

        # No 3D acceleration
        cmd.append("--no3d")

        # Timeout as HH:MM:SS from seconds
        mins = int(profile.max_runtime_s // 60)
        secs = int(profile.max_runtime_s % 60)
        cmd.append(f"--timeout=00:{mins:02d}:{secs:02d}")

        # Quiet mode (less output noise)
        cmd.append("--quiet")

        # Separator before user command
        cmd.append("--")

        # User command
        cmd.extend(argv)

        return cmd

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
        except FileNotFoundError:
            exit_code = -3
            stderr = "firejail not found — backend declared available but executable missing"
        except Exception as e:
            exit_code = -3
            stderr = str(e)

        elapsed = time.time() - start
        stdout = limits.truncate_stdout(stdout)
        stderr = limits.truncate_stderr(stderr)
        return exit_code, stdout, stderr, elapsed

    def describe_isolation(self) -> str:
        return (
            "firejail (profile-based kernel isolation): --net=none, "
            "--private=<sandbox>, --read-only=<paths>, --nodbus, --no3d, "
            "seccomp filtering. Shell=False argv-only execution."
        )

    def supports_network_block(self) -> bool:
        return True

    def supports_readonly_mounts(self) -> bool:
        return True

    def supports_resource_limits(self) -> bool:
        return True  # firejail has --rlimit-* options
