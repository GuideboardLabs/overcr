"""
OverCR v2.10.0 — Version Matrix

Tracks compatibility across the full version lineage:
  - v1 → v2 compatibility
  - Schema evolution lineage
  - Workflow template compatibility
  - Sandbox backend compatibility
  - Optional dependency compatibility

Machine-readable report for release engineering.
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class VersionMatrixEntry:
    """A single version lineage entry."""
    version: str
    package: str
    introduced: str = ""
    compatible_with: list[str] = field(default_factory=list)
    breaking_changes: list[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "package": self.package,
            "introduced": self.introduced,
            "compatible_with": self.compatible_with,
            "breaking_changes": self.breaking_changes,
            "notes": self.notes,
        }


class VersionMatrix:
    """
    Tracks the full version compatibility matrix for OverCR.

    Maps every version to its compatibility surface — what it
    depends on, what it's compatible with, and what changed.
    """

    # Known version lineage
    VERSION_LINEAGE = [
        {
            "version": "1.0.0", "package": "runtime",
            "introduced": "v1 base",
            "compatible_with": ["all v1 artifacts"],
            "breaking_changes": [],
            "notes": "L1-L6 validation, approval gates, audit",
        },
        {
            "version": "2.1.0", "package": "memory",
            "introduced": "Semantic memory layer",
            "compatible_with": ["1.0.0"],
            "breaking_changes": [],
            "notes": "Advisory memory, no auto-resolution, filesystem-first",
        },
        {
            "version": "2.2.0", "package": "tui",
            "introduced": "Operator TUI",
            "compatible_with": ["1.0.0", "2.1.0"],
            "breaking_changes": [],
            "notes": "Observatory not cockpit, no auto-approve",
        },
        {
            "version": "2.3.0", "package": "workflow_library",
            "introduced": "Workflow library",
            "compatible_with": ["1.0.0", "2.1.0", "2.2.0"],
            "breaking_changes": [],
            "notes": "5 frozen workflow templates, replay support",
        },
        {
            "version": "2.4.0", "package": "knowledge",
            "introduced": "Research & knowledge layer",
            "compatible_with": ["1.0.0", "2.1.0", "2.2.0", "2.3.0"],
            "breaking_changes": [],
            "notes": "Source registry, provenance tracker, contradiction detector",
        },
        {
            "version": "2.5.0", "package": "web_ingestion",
            "introduced": "Web ingestion gateway",
            "compatible_with": ["1.0.0", "2.1.0", "2.2.0", "2.3.0", "2.4.0"],
            "breaking_changes": [],
            "notes": "URL validation, prompt injection scanner, mock fetcher for tests",
        },
        {
            "version": "2.6.0", "package": "sandbox",
            "introduced": "Execution sandbox",
            "compatible_with": ["1.0.0", "2.1.0", "2.2.0", "2.3.0", "2.4.0", "2.5.0"],
            "breaking_changes": [],
            "notes": "Superseded by 2.7.0 — command allowlist, shell=False, rollback snapshots",
        },
        {
            "version": "2.7.0", "package": "sandbox",
            "introduced": "Kernel isolation backends",
            "compatible_with": ["1.0.0", "2.1.0", "2.2.0", "2.3.0", "2.4.0", "2.5.0"],
            "breaking_changes": [],
            "notes": "bubblewrap/firejail backends, backend selector, isolation profiles. Evolved from 2.6.0 in-place.",
        },
        {
            "version": "2.8.0", "package": "workflow_composition",
            "introduced": "Conditional routing & composition",
            "compatible_with": ["1.0.0", "2.1.0", "2.2.0", "2.3.0", "2.4.0", "2.5.0", "2.7.0"],
            "breaking_changes": [],
            "notes": "Condition evaluator, state machine, subworkflow loader, escalation policy",
        },
        {
            "version": "2.9.0", "package": "integration",
            "introduced": "Integration hardening",
            "compatible_with": [
                "1.0.0", "2.1.0", "2.2.0", "2.3.0",
                "2.4.0", "2.5.0", "2.7.0", "2.8.0",
            ],
            "breaking_changes": [],
            "notes": "8 read-only validators, 4 check scripts, recovery verifier",
        },
        {
            "version": "2.10.0", "package": "release",
            "introduced": "Stable RC consolidation",
            "compatible_with": [
                "1.0.0", "2.1.0", "2.2.0", "2.3.0",
                "2.4.0", "2.5.0", "2.7.0", "2.8.0", "2.9.0",
            ],
            "breaking_changes": [],
            "notes": "Release builder, semantic compatibility, install validator, operator readiness",
        },
    ]

    def __init__(self, overcr_root: str):
        self.root = Path(overcr_root)

    def generate(self) -> dict:
        """
        Generate the full version matrix as a machine-readable dict.

        Includes: version lineage, schema evolution, backend compat,
        optional dependency matrix, and cross-version guarantees.
        """
        matrix = {
            "generated_at": self._now(),
            "total_versions": len(self.VERSION_LINEAGE),
            "version_lineage": self.VERSION_LINEAGE,
            "schema_evolution": self._collect_schema_evolution(),
            "backend_compatibility": self._collect_backend_matrix(),
            "dependency_matrix": self._collect_dependency_matrix(),
            "compatibility_guarantees": {
                "backward_compat": (
                    "All v2.x releases are backward-compatible with v1.0.0 "
                    "packet validation (L1-L6). Workflow templates from v2.3.0 "
                    "execute on v2.10.0 executor."
                ),
                "forward_compat": (
                    "v2.10.0 schemas are forward-compatible: any new v2.11+ "
                    "release will need to maintain this matrix."
                ),
                "breaking_threshold": (
                    "No breaking changes across the full v2 lineage. "
                    "The only in-place evolution was sandbox 2.6.0 → 2.7.0, "
                    "which is additive (new backends, no field removal)."
                ),
            },
            "verified_at": self._collect_verified_versions(),
        }

        return matrix

    def _now(self) -> str:
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()

    def _collect_schema_evolution(self) -> dict:
        """Track schema evolution across versions."""
        try:
            from integration.schema_registry import SchemaRegistry
            registry = SchemaRegistry(str(self.root))
            schemas = registry.discover_all()
            return {
                sid: {
                    "version": e.version,
                    "path": str(e.path.relative_to(self.root)),
                    "exists": e.path.exists(),
                }
                for sid, e in sorted(schemas.items())
            }
        except ImportError:
            return {"error": "SchemaRegistry not importable"}

    def _collect_backend_matrix(self) -> dict:
        """Build backend compatibility matrix."""
        return {
            "local": {
                "introduced": "2.6.0 (in sandbox package, evolved to 2.7.0)",
                "platforms": ["Linux", "macOS", "WSL2"],
                "features": ["shell=False execution", "basic isolation"],
                "always_available": True,
            },
            "bubblewrap": {
                "introduced": "2.7.0",
                "platforms": ["Linux (x86_64, aarch64)"],
                "features": ["network isolation", "read-only bind mounts",
                              "tmpfs /tmp", "PID namespace"],
                "requirements": ["bwrap binary", "user namespaces (kernel >= 4.18)"],
            },
            "firejail": {
                "introduced": "2.7.0",
                "platforms": ["Linux (x86_64)"],
                "features": ["network isolation", "seccomp filters",
                              "private /tmp", "no D-Bus"],
                "requirements": ["firejail binary", "SUID support"],
            },
        }

    def _collect_dependency_matrix(self) -> dict:
        """Build optional dependency matrix."""
        deps = {}
        for mod, desc in [
            ("yaml", "Config file parsing"),
            ("requests", "HTTP fetches for web ingestion"),
            ("rich", "Terminal rendering for TUI"),
            ("markdown", "Markdown processing for document ingestion"),
            ("pydantic", "Type validation enhancement"),
        ]:
            try:
                __import__(mod)
                deps[mod] = {"available": True, "description": desc, "required": False}
            except ImportError:
                deps[mod] = {"available": False, "description": desc, "required": False}
        return deps

    def _collect_verified_versions(self) -> list[str]:
        """Collect versions verified in the current environment."""
        import re
        verified = []
        for pkg in [
            "runtime", "memory", "tui", "workflow_library",
            "workflow_composition", "knowledge", "sandbox",
            "web_ingestion", "integration", "release",
        ]:
            init = self.root / pkg / "__init__.py"
            if not init.exists():
                verified.append(f"{pkg}=MISSING")
                continue
            content = init.read_text()
            match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', content)
            if match:
                verified.append(f"{pkg}={match.group(1)}")
            else:
                verified.append(f"{pkg}=UNVERSIONED")
        return verified
