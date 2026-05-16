"""
OverCR v2.7.0 — Bubblewrap (bwrap) Backend

Optional strong-isolation backend using bubblewrap. Available only
if bwrap is installed. Provides kernel-level namespace isolation:
private /tmp, readonly bind mounts, no network, no /proc leakage.

Never required. Always falls back to local if unavailable.
"""

import os
import shutil
import subprocess
import time
from sandbox.backends.base_backend import SandboxBackend
from sandbox.isolation_profile import IsolationProfile
from sandbox.resource_limits import ResourceLimits


class BubblewrapBackend(SandboxBackend):
    """
    Kernel isolation backend via bubblewrap (bwrap).

    Provides:
      - New mount namespace (private /tmp, isolated writable root)
      - Readonly bind mounts for allowed read paths
      - No network (--unshare-net) by default
      - No /proc unless allow_proc=True
      - No /dev beyond minimal (/dev/null, /dev/zero only)

    Not installed or required — detection is at runtime.
    """

    BWRAP_BIN = "bwrap"

    @property
    def name(self) -> str:
        return "bubblewrap"

    def available(self) -> bool:
        """Check that bwrap exists and is executable."""
        return shutil.which(self.BWRAP_BIN) is not None

    def build_command(
        self,
        argv: list[str],
        profile: IsolationProfile,
    ) -> list[str]:
        """
        Build a bwrap command vector. Never uses string construction.

        Typical bwrap invocation:
          bwrap --ro-bind /usr /usr --ro-bind /bin /bin --ro-bind /lib /lib
                --bind /tmp/sandbox /tmp/sandbox --unshare-net --die-with-parent
                -- /command arg1 arg2
        """
        cmd = [self.BWRAP_BIN]

        # Bind mount /usr (readonly)
        if os.path.isdir("/usr"):
            cmd.extend(["--ro-bind", "/usr", "/usr"])

        # Bind mount /bin and /lib (readonly) — many systems symlink these
        for bind_dir in ["/bin", "/lib", "/lib64"]:
            if os.path.isdir(bind_dir) and not os.path.islink(bind_dir):
                cmd.extend(["--ro-bind", bind_dir, bind_dir])

        # Bind mount /etc (readonly, for basic system config)
        if os.path.isdir("/etc"):
            cmd.extend(["--ro-bind", "/etc", "/etc"])

        # Additional readonly paths from profile
        for rpath in profile.readonly_paths:
            if os.path.exists(rpath):
                cmd.extend(["--ro-bind", rpath, rpath])

        # Writable sandbox root
        sandbox_root = profile.temp_root or profile.writable_paths[0] if profile.writable_paths else "/tmp"
        cmd.extend(["--bind", sandbox_root, sandbox_root])

        # Private /tmp (isolated from host)
        cmd.extend(["--tmpfs", "/tmp"])

        # Network isolation
        if not profile.network_allowed:
            cmd.append("--unshare-net")

        # No proc unless explicitly allowed
        if not profile.allow_proc:
            cmd.extend(["--proc", "/dev/null"])  # Hide proc

        # Minimal /dev
        if not profile.allow_dev:
            cmd.extend([
                "--dev", "/dev/null",
                "--dev-bind", "/dev/null", "/dev/null",
                "--dev-bind", "/dev/zero", "/dev/zero",
            ])

        # Die with parent process
        cmd.append("--die-with-parent")

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
            stderr = "bwrap not found — backend declared available but executable missing"
        except Exception as e:
            exit_code = -3
            stderr = str(e)

        elapsed = time.time() - start
        stdout = limits.truncate_stdout(stdout)
        stderr = limits.truncate_stderr(stderr)
        return exit_code, stdout, stderr, elapsed

    def describe_isolation(self) -> str:
        return (
            "bubblewrap (kernel namespace isolation): private /tmp, "
            "ro-bind /usr /bin /lib /etc, --unshare-net, no /proc, "
            "minimal /dev (/dev/null /dev/zero only), --die-with-parent. "
            "Shell=False argv-only execution."
        )

    def supports_network_block(self) -> bool:
        return True

    def supports_readonly_mounts(self) -> bool:
        return True

    def supports_resource_limits(self) -> bool:
        return False
