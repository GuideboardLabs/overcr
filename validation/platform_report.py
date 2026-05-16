"""
OverCR v2.10.1 Platform Report

Records the environment where v2.10.0 was validated. No claims of support
for platforms not tested. Purely informational.

Governance:
  - Record only — no modification
  - No claims beyond tested environment
  - OS, Python, shell, filesystem, deps, backends, known limitations
"""

import json
import os
import platform
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

OVERCR_ROOT = Path(os.environ.get("OVERCR_ROOT", str(Path(__file__).resolve().parent.parent)))
sys.path.insert(0, str(OVERCR_ROOT))


@dataclass
class PlatformReport:
    """Environment report for v2.10.0 validation."""
    timestamp: str = ""
    os_name: str = ""
    os_version: str = ""
    kernel: str = ""
    architecture: str = ""
    python_version: str = ""
    python_implementation: str = ""
    shell: str = ""
    filesystem: str = ""
    working_directory: str = ""

    # Optional dependencies
    optional_packages: dict = field(default_factory=dict)

    # Sandbox backends
    sandbox_backends: dict = field(default_factory=dict)

    # Hermes
    hermes_available: bool = False
    hermes_version: str = ""

    # Known limitations
    known_limitations: list = field(default_factory=list)
    notes: str = ""

    def collect(self) -> "PlatformReport":
        """Collect all platform information."""
        self.timestamp = datetime.now(timezone.utc).isoformat()

        # OS
        self.os_name = platform.system()
        self.os_version = platform.version()
        self.kernel = platform.release()
        self.architecture = platform.machine()

        # Python
        self.python_version = sys.version.split()[0]
        self.python_implementation = platform.python_implementation()

        # Shell
        self.shell = os.environ.get("SHELL", os.environ.get("COMSPEC", "unknown"))

        # Filesystem
        try:
            fs_stat = os.statvfs(str(OVERCR_ROOT))
            self.filesystem = f"f_frsize={fs_stat.f_frsize}"
        except Exception:
            self.filesystem = "unknown (statvfs failed)"

        self.working_directory = str(OVERCR_ROOT.resolve())

        # Optional deps
        self._collect_optional_packages()

        # Sandbox backends
        self._collect_sandbox_backends()

        # Hermes
        self._check_hermes()

        # Known limitations
        self._collect_limitations()

        return self

    def _collect_optional_packages(self):
        """Check availability of optional Python packages."""
        packages = [
            "pydantic",
            "markdown",
            "yaml",
            "rich",
            "textual",
            "psutil",
            "pandas",
        ]
        for pkg in packages:
            try:
                mod = __import__(pkg)
                version = getattr(mod, "__version__", "installed")
                self.optional_packages[pkg] = version
            except ImportError:
                self.optional_packages[pkg] = "not installed"

    def _collect_sandbox_backends(self):
        """Check sandbox backend availability."""
        backends = {
            "firejail": "firejail",
            "bubblewrap": "bwrap",
            "podman": "podman",
            "docker": "docker",
        }
        for name, binary in backends.items():
            path = shutil.which(binary)
            self.sandbox_backends[name] = {
                "available": path is not None,
                "path": path or "",
            }

    def _check_hermes(self):
        """Check if Hermes CLI is available."""
        hermes_path = shutil.which("hermes")
        self.hermes_available = hermes_path is not None
        if self.hermes_available:
            import subprocess

            try:
                result = subprocess.run(
                    ["hermes", "--version"],
                    capture_output=True, text=True, timeout=5,
                )
                self.hermes_version = result.stdout.strip().split("\n")[0]
            except Exception:
                self.hermes_version = "version check failed"
        else:
            self.hermes_version = ""

    def _collect_limitations(self):
        """Record known platform limitations."""
        limitations = []

        # WSL detection
        if "microsoft" in self.kernel.lower() or "WSL" in self.os_version:
            limitations.append(
                "Running under WSL (Windows Subsystem for Linux). "
                "Filesystem performance differs from bare-metal Linux. "
                "Sandbox backends (firejail/bubblewrap) may have reduced functionality."
            )

        # macOS
        if self.os_name == "Darwin":
            limitations.append(
                "macOS: sandbox backends firejail/bubblewrap not available. "
                "LocalBackend only. Kernel isolation features unavailable."
            )

        # Windows native
        if self.os_name == "Windows":
            limitations.append(
                "Windows: no sandbox backends (LocalBackend only). "
                "Path handling differs from POSIX. Tests targeting POSIX paths may fail."
            )

        # Python version
        py_ver = tuple(int(x) for x in self.python_version.split(".")[:2])
        if py_ver < (3, 9):
            limitations.append(
                f"Python {self.python_version} is below minimum supported 3.9."
            )

        # Missing backends
        for name, info in self.sandbox_backends.items():
            if not info["available"] and name in ("firejail", "bubblewrap"):
                limitations.append(
                    f"Sandbox backend '{name}' not available. "
                    "LocalBackend fallback only (no kernel isolation)."
                )

        # Missing Hermes
        if not self.hermes_available:
            limitations.append(
                "Hermes CLI not available. Inference tests requiring Hermes will skip."
            )

        self.known_limitations = limitations

        # Notes
        notes_parts = []
        if self.os_name == "Linux":
            notes_parts.append("Primary development and validation platform.")
        if self.optional_packages.get("rich") == "not installed":
            notes_parts.append("Rich not installed — TUI rendering falls back to plain text.")
        if self.optional_packages.get("textual") == "not installed":
            notes_parts.append("Textual not installed — TUI views use render_plain() fallback.")

        self.notes = " ".join(notes_parts) if notes_parts else "No notable platform observations."

    def to_dict(self) -> dict:
        """Serialize to JSON-safe dict."""
        return {
            "timestamp": self.timestamp,
            "os": {
                "name": self.os_name,
                "version": self.os_version,
                "kernel": self.kernel,
                "architecture": self.architecture,
            },
            "python": {
                "version": self.python_version,
                "implementation": self.python_implementation,
            },
            "shell": self.shell,
            "filesystem": self.filesystem,
            "working_directory": self.working_directory,
            "optional_packages": self.optional_packages,
            "sandbox_backends": {
                name: info["available"] for name, info in self.sandbox_backends.items()
            },
            "hermes": {
                "available": self.hermes_available,
                "version": self.hermes_version,
            },
            "known_limitations": self.known_limitations,
            "notes": self.notes,
        }


def collect_report() -> dict:
    """Convenience function: collect and return platform report dict."""
    report = PlatformReport()
    report.collect()
    return report.to_dict()
