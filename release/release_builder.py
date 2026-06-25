"""
OverCR v2.10.0 — Release Builder

Generates clean release artifacts:
  - Release archive (tar.gz)
  - SHA256 manifest
  - Release metadata
  - Compatibility manifest
  - Schema manifest
  - Package inventory

Requirements:
  - Deterministic archive ordering where possible
  - Exclude transient runtime artifacts
  - Exclude mutable audit debris
  - Include version inventory
  - Never include runtime secrets or transient state
"""

import hashlib
import json
import os
import tarfile
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


@dataclass
class ReleaseBuild:
    """Complete release build result."""
    archive_path: str = ""
    archive_size: int = 0
    sha256: str = ""
    generated_at: str = ""
    file_count: int = 0
    results: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def add_result(self, check: str, status: str, detail: str = ""):
        self.results.append({"check": check, "status": status, "detail": detail})
        if status == "FAIL":
            self.errors.append(f"{check}: {detail}")

    def to_dict(self) -> dict:
        return {
            "archive_path": self.archive_path,
            "archive_size": self.archive_size,
            "sha256": self.sha256,
            "generated_at": self.generated_at,
            "file_count": self.file_count,
            "results": self.results,
            "errors": self.errors,
        }


class ReleaseBuilder:
    """
    Builds a clean release archive from the source tree.

    Excludes runtime state, bytecode, git artifacts, and any
    mutable debris that shouldn't ship in a release.
    """

    # Directories to include in release
    INCLUDE_DIRS = [
        "runtime", "memory", "tui", "workflow_library",
        "workflow_composition", "knowledge", "sandbox",
        "web_ingestion", "integration", "release",
        "subagents", "tools", "tests", "references",
        "scripts", "examples", "orchestration",
        "config", "docs",
    ]

    # Files to include at root
    ROOT_FILES = [
        "README.md", "INSTALL.md", "LICENSE.md", "RELEASE.md",
        "CHANGELOG.md", "boot.sh", "soul.md", "soul_reference.md",
    ]

    # Patterns to exclude
    EXCLUDE_PATTERNS = [
        "__pycache__", "*.pyc", "*.pyo",
        ".git", ".gitignore", ".DS_Store",
        "runtime/audit.jsonl", "runtime/workflow_trace_*",
        "runtime/receipt_*", "runtime/snapshot_*",
        "runtime/compatibility_matrix_*",
        "runtime/integration_hardening_summary*",
        "*.egg-info", "dist/", "*.tar.gz",
    ]

    def __init__(self, overcr_root: str):
        self.root = Path(overcr_root)

    def build(self, output_dir: Optional[str] = None) -> ReleaseBuild:
        """
        Build a release archive.

        Args:
            output_dir: Where to write the archive. Defaults to root/dist/.
        """
        build = ReleaseBuild()
        build.generated_at = datetime.now(timezone.utc).isoformat()

        if output_dir:
            out = Path(output_dir)
        else:
            out = self.root / "dist"
        out.mkdir(parents=True, exist_ok=True)

        # Determine version
        version = "2.10.0"
        version_file = self.root / "release" / "__init__.py"
        if version_file.exists():
            import re
            content = version_file.read_text()
            match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', content)
            if match:
                version = match.group(1)

        archive_name = f"overcr-{version}.tar.gz"
        archive_path = out / archive_name

        # Collect files
        files_to_add = []
        seen = set()

        # Root files
        for fname in self.ROOT_FILES:
            fpath = self.root / fname
            if fpath.exists() and fpath.is_file():
                files_to_add.append((fpath, fname))
                seen.add(fname)

        # Directories
        for dname in self.INCLUDE_DIRS:
            dpath = self.root / dname
            if not dpath.is_dir():
                build.add_result(f"dir:{dname}", "WARN", "Directory not found")
                continue

            for fpath in dpath.rglob("*"):
                if fpath.is_dir():
                    continue
                rel = str(fpath.relative_to(self.root))
                # Skip excluded patterns
                if self._is_excluded(rel):
                    continue
                if rel in seen:
                    continue
                seen.add(rel)
                files_to_add.append((fpath, rel))

        # Sort for deterministic archive ordering
        files_to_add.sort(key=lambda x: x[1])

        # Create archive
        try:
            with tarfile.open(archive_path, "w:gz") as tar:
                for fpath, arcname in files_to_add:
                    tar.add(fpath, arcname=arcname)

            build.archive_path = str(archive_path)
            build.file_count = len(files_to_add)
            build.archive_size = archive_path.stat().st_size
            build.add_result("build:archive", "PASS",
                             f"{build.file_count} files, "
                             f"{build.archive_size:,} bytes")

        except Exception as e:
            build.add_result("build:archive", "FAIL", str(e))
            return build

        # Generate SHA256
        try:
            sha = hashlib.sha256()
            with open(archive_path, "rb") as f:
                while True:
                    chunk = f.read(65536)
                    if not chunk:
                        break
                    sha.update(chunk)
            build.sha256 = sha.hexdigest()
            build.add_result("build:sha256", "PASS", build.sha256)

            # Write SHA256 manifest
            manifest_path = out / f"{archive_name}.sha256"
            manifest_path.write_text(f"{build.sha256}  {archive_name}\n")
            build.add_result("build:manifest", "PASS", str(manifest_path))

        except Exception as e:
            build.add_result("build:sha256", "FAIL", str(e))

        # Generate metadata
        try:
            metadata = {
                "version": version,
                "archive": archive_name,
                "sha256": build.sha256,
                "generated_at": build.generated_at,
                "file_count": build.file_count,
                "archive_size": build.archive_size,
                "packages": self._get_package_versions(),
            }
            meta_path = out / f"overcr-{version}.meta.json"
            meta_path.write_text(json.dumps(metadata, indent=2))
            build.add_result("build:metadata", "PASS", str(meta_path))

        except Exception as e:
            build.add_result("build:metadata", "FAIL", str(e))

        return build

    def _is_excluded(self, rel_path: str) -> bool:
        """Check if a relative path matches any exclusion pattern."""
        parts = rel_path.split("/")
        for part in parts:
            if part == "__pycache__":
                return True
            if part.endswith(".pyc") or part.endswith(".pyo"):
                return True
            if part == ".DS_Store":
                return True
            if part == ".git" or part == ".gitignore":
                return True

        # Check runtime state files
        if rel_path.startswith("runtime/") and (
            "audit.jsonl" in rel_path or
            "workflow_trace_" in rel_path or
            "receipt_" in rel_path or
            "snapshot_" in rel_path or
            "compatibility_matrix_" in rel_path or
            "integration_hardening" in rel_path
        ):
            return True

        if ".egg-info" in rel_path:
            return True

        return False

    def _get_package_versions(self) -> dict:
        """Collect all package versions."""
        import re
        versions = {}
        for pkg in self.INCLUDE_DIRS:
            init = self.root / pkg / "__init__.py"
            if not init.exists():
                continue
            content = init.read_text()
            match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', content)
            if match:
                versions[pkg] = match.group(1)
        return versions
