"""
OverCR v2.9.0 — Compatibility Matrix

Generates a machine-readable compatibility report covering:
  - Python versions
  - Optional sandbox backends
  - Runtime adapters
  - Filesystem assumptions
  - Optional dependencies
  - Supported OS targets

This report is deterministic and portable — no external services
are required to generate it.
"""

import json
import platform
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class CompatibilityReport:
    """Machine-readable compatibility report."""
    generated_at: str = ""
    python_version: str = ""
    os_info: str = ""
    backends: dict = field(default_factory=dict)
    optional_deps: dict = field(default_factory=dict)
    filesystem_requirements: list[str] = field(default_factory=list)
    supported_os: list[str] = field(default_factory=list)
    runtime_adapters: list[dict] = field(default_factory=list)
    known_issues: list[str] = field(default_factory=list)
    results: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "generated_at": self.generated_at,
            "python_version": self.python_version,
            "os_info": self.os_info,
            "backends": self.backends,
            "optional_dependencies": self.optional_deps,
            "filesystem_requirements": self.filesystem_requirements,
            "supported_operating_systems": self.supported_os,
            "runtime_adapters": self.runtime_adapters,
            "known_issues": self.known_issues,
            "results": self.results,
        }


class CompatibilityMatrix:
    """
    Generates a machine-readable compatibility report.

    Scans the environment and reports on available backends,
    optional dependencies, and platform compatibility.
    """

    # Optional Python dependencies
    OPTIONAL_DEPS = [
        ("yaml", "YAML support for config files"),
        ("requests", "HTTP fetches for web ingestion"),
        ("markdown", "Markdown processing for document ingestion"),
        ("rich", "Rich terminal rendering for TUI"),
        ("pydantic", "Type validation (optional enhancement)"),
    ]

    # Supported operating systems
    SUPPORTED_OS = [
        "Linux (x86_64)",
        "Linux (aarch64)",
        "macOS (x86_64)",
        "macOS (arm64)",
        "WSL2 (Windows Subsystem for Linux)",
    ]

    # Filesystem requirements
    FS_REQUIREMENTS = [
        "Case-sensitive filesystem (ext4, APFS case-sensitive, NTFS in WSL)",
        "POSIX file permissions",
        "Symlink support",
        "At least 100MB free for runtime state",
        "JSONL append support (atomic appends for audit)",
    ]

    # Known limitations
    KNOWN_ISSUES = [
        "bubblewrap backend requires bwrap binary and user namespaces (Linux kernel >= 4.18)",
        "firejail backend requires firejail binary and SUID/setuid support",
        "WSL2: bubblewrap may fail if user namespaces not enabled in kernel",
        "macOS: bubblewrap not available; firejail not available; use local backend only",
        "Rich TUI: requires terminal with Unicode/emoji support for full rendering",
    ]

    def __init__(self, overcr_root: str):
        self.root = Path(overcr_root)

    def generate(self) -> CompatibilityReport:
        """Generate the full compatibility report."""
        from datetime import datetime, timezone

        report = CompatibilityReport()
        report.generated_at = datetime.now(timezone.utc).isoformat()
        report.python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        report.os_info = f"{platform.system()} {platform.release()} ({platform.machine()})"
        report.filesystem_requirements = self.FS_REQUIREMENTS
        report.supported_os = self.SUPPORTED_OS
        report.known_issues = self.KNOWN_ISSUES

        # Check backends
        self._check_backends(report)

        # Check optional deps
        self._check_optional_deps(report)

        # Check runtime adapters
        self._check_runtime_adapters(report)

        # Check filesystem
        self._check_filesystem(report)

        return report

    def _check_backends(self, report: CompatibilityReport):
        """Check availability of sandbox backends."""
        backends = {}

        # Local backend (always)
        backends["local"] = {"available": True, "path": "built-in", "notes": ""}

        # Bubblewrap
        bwrap = shutil.which("bwrap")
        if bwrap:
            backends["bubblewrap"] = {"available": True, "path": bwrap,
                                       "notes": "User namespaces required"}
        else:
            backends["bubblewrap"] = {"available": False, "path": None,
                                       "notes": "bwrap binary not found"}

        # Firejail
        fj = shutil.which("firejail")
        if fj:
            backends["firejail"] = {"available": True, "path": fj,
                                     "notes": "SUID/setuid required"}
        else:
            backends["firejail"] = {"available": False, "path": None,
                                     "notes": "firejail binary not found"}

        report.backends = backends

        # Add pass/fail results
        for name, info in backends.items():
            status = "PASS" if info["available"] else "WARN"
            report.results.append({
                "check": f"backend:{name}",
                "status": status,
                "available": info["available"],
            })

    def _check_optional_deps(self, report: CompatibilityReport):
        """Check availability of optional dependencies."""
        deps = {}
        for module_name, desc in self.OPTIONAL_DEPS:
            available = False
            try:
                __import__(module_name)
                available = True
            except ImportError:
                pass

            deps[module_name] = {"available": available, "description": desc}

            status = "PASS" if available else "WARN"
            report.results.append({
                "check": f"dep:{module_name}",
                "status": status,
                "available": available,
                "description": desc,
            })

        report.optional_deps = deps

    def _check_runtime_adapters(self, report: CompatibilityReport):
        """Check runtime adapter compatibility."""
        adapters = []

        # Check Hermes CLI adapter
        try:
            from inference.hermes_cli_adapter import HermesCLIAdapter
            adapter = HermesCLIAdapter()
            available = adapter.check_available()
            adapters.append({
                "name": "hermes_cli",
                "available": available,
                "description": "Hermes CLI inference adapter",
                "type": "inference",
            })
            report.results.append({
                "check": "adapter:hermes_cli",
                "status": "PASS" if available else "WARN",
                "available": available,
            })
        except ImportError:
            adapters.append({
                "name": "hermes_cli",
                "available": False,
                "description": "Hermes CLI inference adapter",
                "type": "inference",
            })
            report.results.append({
                "check": "adapter:hermes_cli",
                "status": "WARN",
                "available": False,
                "detail": "Module not importable",
            })

        # Check mock adapter (always available)
        adapters.append({
            "name": "mock_adapter",
            "available": True,
            "description": "Mock inference adapter for testing",
            "type": "inference",
        })
        report.results.append({
            "check": "adapter:mock",
            "status": "PASS",
            "available": True,
        })

        # Check output sanitizer
        try:
            from inference.output_sanitizer import OutputSanitizer
            adapters.append({
                "name": "output_sanitizer",
                "available": True,
                "description": "Deterministic JSON extraction from model output",
                "type": "sanitizer",
            })
            report.results.append({
                "check": "adapter:sanitizer",
                "status": "PASS",
                "available": True,
            })
        except ImportError:
            adapters.append({
                "name": "output_sanitizer",
                "available": False,
                "description": "Output sanitizer",
                "type": "sanitizer",
            })
            report.results.append({
                "check": "adapter:sanitizer",
                "status": "WARN",
                "available": False,
            })

        report.runtime_adapters = adapters

    def _check_filesystem(self, report: CompatibilityReport):
        """Check filesystem suitability."""
        # Check workspace is writable
        try:
            test_file = self.root / ".compat_test"
            test_file.write_text("test")
            test_file.unlink()
            report.results.append({
                "check": "filesystem:writable",
                "status": "PASS",
            })
        except Exception as e:
            report.results.append({
                "check": "filesystem:writable",
                "status": "FAIL",
                "detail": str(e),
            })

        # Check temp directory
        import tempfile
        try:
            with tempfile.NamedTemporaryFile(prefix="overcr-compat-") as tf:
                pass
            report.results.append({
                "check": "filesystem:temp",
                "status": "PASS",
            })
        except Exception as e:
            report.results.append({
                "check": "filesystem:temp",
                "status": "FAIL",
                "detail": str(e),
            })

        # Check symlink support
        try:
            import os
            test_symlink = self.root / ".compat_symlink_test"
            if test_symlink.exists():
                test_symlink.unlink()
            os.symlink(self.root / "README.md", test_symlink)
            if test_symlink.exists():
                test_symlink.unlink()
                report.results.append({
                    "check": "filesystem:symlinks",
                    "status": "PASS",
                })
            else:
                report.results.append({
                    "check": "filesystem:symlinks",
                    "status": "FAIL",
                    "detail": "Symlink creation failed silently",
                })
        except OSError as e:
            report.results.append({
                "check": "filesystem:symlinks",
                "status": "WARN",
                "detail": str(e),
            })
