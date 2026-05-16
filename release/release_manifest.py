"""
OverCR v2.10.0 — Release Manifest

Generates a machine-readable manifest for the entire v2.10 release,
  including:
  - Version
  - Schema versions
  - Workflow versions
  - Runtime assumptions
  - Optional backends
  - Compatibility guarantees
  - Known limitations
  - Release timestamp
  - Git metadata if available
"""

import json
import platform
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class ReleaseManifestEntry:
    """A single entry in the release manifest."""
    name: str
    value: str
    category: str  # version, schema, runtime, backend, compat, limitation


class ReleaseManifest:
    """
    Generates a machine-readable release manifest.

    Includes everything needed to understand what this release contains
    and what it requires.
    """

    def __init__(self, overcr_root: str):
        self.root = Path(overcr_root)

    def generate(self) -> dict:
        """
        Generate the full release manifest as a dict.

        Returns a dict suitable for JSON serialization.
        """
        import re

        manifest = {
            "release": {
                "version": "2.10.0",
                "codename": "Stable Release Candidate",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "release_type": "stable-candidate",
            },
            "environment": {
                "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
                "os": f"{platform.system()} {platform.release()} ({platform.machine()})",
                "python_path": sys.executable,
            },
            "packages": self._collect_package_versions(),
            "schemas": self._collect_schema_versions(),
            "workflows": self._collect_workflow_versions(),
            "backends": self._collect_backend_info(),
            "dependencies": self._collect_dependencies(),
            "compatibility": {
                "python_minimum": "3.10",
                "os_supported": [
                    "Linux (x86_64, aarch64)",
                    "WSL2",
                    "macOS (x86_64, arm64) — local backend only",
                ],
                "filesystem_requirements": [
                    "POSIX file permissions",
                    "Symlink support",
                    "Case-sensitive filesystem preferred",
                ],
                "backends_supported": self._collect_backend_info(),
            },
            "governance": {
                "validation": "L1-L6 packet validation preserved from v1.0.0",
                "approval": "All PypER execution requires operator approval",
                "audit": "Append-only JSONL audit traces",
                "replay": "Deterministic replay from audit artifacts",
                "memory": "Advisory semantic memory, no auto-resolution",
                "sandbox": "Shell=False mandatory, approval-gated execution",
            },
            "known_limitations": [
                "bubblewrap backend requires bwrap binary + user namespaces (Linux >= 4.18)",
                "firejail backend requires firejail binary + SUID support",
                "macOS: only local backend available",
                "No automatic migration from v1 — manual upgrade only",
                "Optional dependencies markdown, pydantic may be absent",
            ],
            "artifacts_included": self._collect_artifact_summary(),
            "git_metadata": self._collect_git_metadata(),
            "test_status": self._collect_test_status(),
        }

        return manifest

    def _collect_package_versions(self) -> dict:
        """Collect all package version strings."""
        import re
        versions = {}
        pkg_dirs = [
            "runtime", "memory", "tui", "workflow_library",
            "workflow_composition", "knowledge", "sandbox",
            "web_ingestion", "integration", "release",
        ]
        for pkg in pkg_dirs:
            init = self.root / pkg / "__init__.py"
            if not init.exists():
                versions[pkg] = "MISSING"
                continue
            content = init.read_text()
            match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', content)
            versions[pkg] = match.group(1) if match else "UNVERSIONED"
        return versions

    def _collect_schema_versions(self) -> dict:
        """Collect schema versions from schema_registry."""
        try:
            from integration.schema_registry import SchemaRegistry
            registry = SchemaRegistry(str(self.root))
            schemas = registry.discover_all()
            return {
                sid: {"version": e.version, "exists": e.path.exists(),
                      "path": str(e.path.relative_to(self.root))}
                for sid, e in sorted(schemas.items())
            }
        except ImportError:
            return {"error": "SchemaRegistry not importable"}

    def _collect_workflow_versions(self) -> dict:
        """Collect workflow template versions."""
        import json
        workflows = {}
        templates_dir = self.root / "workflow_library" / "templates"
        if templates_dir.is_dir():
            for tf in sorted(templates_dir.glob("*.json")):
                try:
                    with open(tf, "r") as f:
                        t = json.load(f)
                    workflows[t.get("workflow_id", tf.stem)] = {
                        "version": t.get("version", "unversioned"),
                        "name": t.get("workflow_name", ""),
                        "nodes": len(t.get("node_definitions", [])),
                        "edges": len(t.get("edge_definitions", [])),
                    }
                except Exception:
                    workflows[tf.stem] = {"version": "ERROR"}
        return workflows

    def _collect_backend_info(self) -> dict:
        """Collect sandbox backend availability."""
        import shutil
        backends = {"local": {"available": True, "path": "built-in"}}

        bwrap = shutil.which("bwrap")
        backends["bubblewrap"] = {
            "available": bwrap is not None,
            "path": bwrap or None,
            "notes": "Linux only, user namespaces required",
        }

        fj = shutil.which("firejail")
        backends["firejail"] = {
            "available": fj is not None,
            "path": fj or None,
            "notes": "Linux only, SUID required",
        }

        return backends

    def _collect_dependencies(self) -> dict:
        """Check optional dependency availability."""
        deps = {}
        for mod in ["yaml", "requests", "rich", "markdown", "pydantic"]:
            try:
                __import__(mod)
                deps[mod] = "available"
            except ImportError:
                deps[mod] = "missing"
        return deps

    def _collect_artifact_summary(self) -> dict:
        """Collect a summary of included artifacts."""
        counts = {}
        for d in ["tests", "examples", "references", "scripts"]:
            p = self.root / d
            if p.is_dir():
                counts[d] = sum(1 for _ in p.rglob("*.py") if _.is_file())
            else:
                counts[d] = 0

        # Count workflow templates
        tmpl = self.root / "workflow_library" / "templates"
        counts["workflow_templates"] = (
            sum(1 for _ in tmpl.glob("*.json")) if tmpl.is_dir() else 0
        )

        # Count schemas
        schema_count = 0
        for schema_dir in [
            "workflow_library/schema",
            "workflow_composition/schema",
            "memory/schema",
            "knowledge/schema",
            "sandbox/schema",
            "web_ingestion/schema",
        ]:
            sd = self.root / schema_dir
            if sd.is_dir():
                schema_count += sum(1 for _ in sd.glob("*.json"))

        counts["schemas"] = schema_count
        return counts

    def _collect_git_metadata(self) -> dict:
        """Collect git metadata if available."""
        git = {"available": False}

        try:
            import shutil
            if not shutil.which("git"):
                return git

            result = subprocess.run(
                ["git", "-C", str(self.root), "rev-parse", "HEAD"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                git["available"] = True
                git["commit"] = result.stdout.strip()

            result = subprocess.run(
                ["git", "-C", str(self.root), "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                git["branch"] = result.stdout.strip()

            result = subprocess.run(
                ["git", "-C", str(self.root), "describe", "--tags", "--always"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                git["describe"] = result.stdout.strip()

        except Exception:
            pass

        return git

    def _collect_test_status(self) -> dict:
        """Collect test status from manifest."""
        manifest_path = self.root / "tests" / "test_manifest.json"
        if not manifest_path.exists():
            return {"available": False}

        try:
            with open(manifest_path, "r") as f:
                m = json.load(f)
            tests = m.get("tests", [])
            return {
                "available": True,
                "count": len(tests),
                "categories": sorted(set(t["category"] for t in tests)),
                "manifest_version": m.get("version", "unknown"),
            }
        except Exception:
            return {"available": False, "error": "Failed to parse manifest"}
