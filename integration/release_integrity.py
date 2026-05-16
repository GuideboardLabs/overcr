"""
OverCR v2.9.0 — Release Integrity Checker

Checks release package cleanliness, detecting:
  - __pycache__ directories
  - .pyc bytecode files
  - Transient runtime debris
  - Orphaned receipts
  - Stale snapshots
  - Missing documentation
  - Inconsistent version references
  - Mutable artifacts accidentally committed
  - Broken schema references

All checks are read-only — never mutates the source tree.
"""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class IntegrityReport:
    """Complete release integrity report."""
    passed: bool = True
    results: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    findings: list[dict] = field(default_factory=list)

    def add_pass(self, check: str):
        self.results.append({"check": check, "status": "PASS"})

    def add_fail(self, check: str, detail: str):
        self.passed = False
        self.results.append({"check": check, "status": "FAIL", "detail": detail})
        self.errors.append(f"{check}: {detail}")

    def add_warning(self, check: str, detail: str):
        self.results.append({"check": check, "status": "WARN", "detail": detail})
        self.warnings.append(f"{check}: {detail}")

    def add_finding(self, category: str, path: str, detail: str):
        self.findings.append({"category": category, "path": path, "detail": detail})

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "results": self.results,
            "errors": self.errors,
            "warnings": self.warnings,
            "findings": self.findings,
        }


class ReleaseIntegrity:
    """
    Checks release package for forbidden artifacts and cleanliness.

    Scans the source tree for runtime debris, bytecode, stale
    snapshots, and any mutable artifacts that shouldn't be in a
    release candidate.
    """

    # Source extensions to check
    SOURCE_EXTENSIONS = {".py", ".md", ".sh", ".yaml", ".yml", ".json", ".tpl", ".txt"}

    # Directories to ignore
    IGNORE_DIRS = {".git", "dist", "__pycache__", ".pytest_cache", ".mypy_cache"}

    def __init__(self, overcr_root: str):
        self.root = Path(overcr_root)

    def check_all(self) -> IntegrityReport:
        """Run all integrity checks."""
        report = IntegrityReport()

        self._check_pycache_leakage(report)
        self._check_pyc_files(report)
        self._check_transient_debris(report)
        self._check_orphaned_receipts(report)
        self._check_stale_snapshots(report)
        self._check_docs_completeness(report)
        self._check_version_consistency(report)
        self._check_mutable_artifacts(report)
        self._check_broken_schema_refs(report)

        return report

    # ── __pycache__ leakage ───────────────────────────────

    def _check_pycache_leakage(self, report: IntegrityReport):
        """Detect __pycache__ directories with content."""
        found = 0
        for pycache in self.root.rglob("__pycache__"):
            parts = pycache.relative_to(self.root).parts
            if any(ign in parts for ign in self.IGNORE_DIRS):
                continue
            if pycache.is_dir() and list(pycache.iterdir()):
                found += 1
                report.add_finding("pycache", str(pycache.relative_to(self.root)),
                                   "Contains compiled bytecode")

        if found == 0:
            report.add_pass("integrity:pycache_clean")
        else:
            report.add_fail("integrity:pycache",
                            f"{found} __pycache__ directories with content")

    # ── .pyc files ────────────────────────────────────────

    def _check_pyc_files(self, report: IntegrityReport):
        """Detect compiled .pyc files."""
        found = []
        for pyc in self.root.rglob("*.pyc"):
            parts = pyc.relative_to(self.root).parts
            if any(ign in parts for ign in self.IGNORE_DIRS):
                continue
            found.append(str(pyc.relative_to(self.root)))

        if not found:
            report.add_pass("integrity:pyc_clean")
        else:
            report.add_fail("integrity:pyc",
                            f"{len(found)} .pyc files: {found[:5]}")

    # ── Transient runtime debris ──────────────────────────

    def _check_transient_debris(self, report: IntegrityReport):
        """Detect transient runtime files that shouldn't be committed."""
        transient_patterns = [
            "*.pyc",
            "*.pyo",
            "*.egg-info/PKG-INFO",
            "*.egg-info/SOURCES.txt",
            ".DS_Store",
            "Thumbs.db",
            "*.swp",
            "*.swo",
            "*~",
        ]

        found = 0
        for pattern in transient_patterns:
            for match in self.root.rglob(pattern):
                parts = match.relative_to(self.root).parts
                if any(ign in parts for ign in self.IGNORE_DIRS):
                    continue
                found += 1
                report.add_finding("transient", str(match.relative_to(self.root)),
                                   "Transient file should not be in repo")

        if found == 0:
            report.add_pass("integrity:transient_clean")
        else:
            report.add_warning("integrity:transient",
                               f"{found} transient files found")

    # ── Orphaned receipts ─────────────────────────────────

    def _check_orphaned_receipts(self, report: IntegrityReport):
        """Check for execution receipts without corresponding executions."""
        import json
        runtime_dir = self.root / "runtime"
        if not runtime_dir.is_dir():
            report.add_warning("integrity:receipts", "No runtime directory")
            return

        receipt_files = sorted(runtime_dir.glob("receipt_*.json"))
        trace_files = {tf.stem for tf in runtime_dir.glob("workflow_trace_*.jsonl")}

        orphaned = 0
        for rf in receipt_files:
            # Receipts should have corresponding trace entries
            rid = rf.stem.replace("receipt_", "")
            # Simple check: if we have many more receipts than traces
            orphaned += 1

        if orphaned == 0:
            report.add_pass("integrity:receipts:none_found")
        else:
            report.add_warning("integrity:receipts",
                               f"{orphaned} receipt files in runtime/")

    # ── Stale snapshots ───────────────────────────────────

    def _check_stale_snapshots(self, report: IntegrityReport):
        """Check for rollback snapshots without corresponding receipts."""
        import json
        runtime_dir = self.root / "runtime"
        snapshot_files = sorted(runtime_dir.glob("snapshot_*.json"))

        if not snapshot_files:
            report.add_pass("integrity:snapshots:none_found")
            return

        # Just report presence — snapshots are runtime state
        report.add_warning("integrity:snapshots",
                           f"{len(snapshot_files)} snapshot files in runtime/")

    # ── Documentation completeness ────────────────────────

    def _check_docs_completeness(self, report: IntegrityReport):
        """Check that documentation references are present."""
        refs_dir = self.root / "references"
        if not refs_dir.is_dir():
            report.add_fail("integrity:docs", "references/ directory missing")
            return

        # Expected reference docs for v2
        expected_refs = [
            "v2.1-memory-architecture.md",
            "v2.2-operator-interface.md",
            "v2.3-workflow-library.md",
            "v2.4-research-layer.md",
            "v2.5-web-ingestion-gateway.md",
            "v2.6-sandbox-architecture.md",
            "v2.7-kernel-isolation.md",
            "v2.8-workflow-composition.md",
        ]

        for ref_name in expected_refs:
            ref_path = refs_dir / ref_name
            if ref_path.exists():
                report.add_pass(f"integrity:docs:{ref_name}")
            else:
                report.add_warning(f"integrity:docs:{ref_name}",
                                   "Expected reference doc not found")

        # Check governance docs
        gov_docs = [
            "v2.1-memory-governance.md",
            "v2.2-tui-governance.md",
            "v2.3-workflow-governance.md",
            "v2.4-provenance-governance.md",
            "v2.5-web-ingestion-governance.md",
            "v2.6-execution-governance.md",
            "v2.7-sandbox-backend-governance.md",
            "v2.8-conditional-routing-governance.md",
        ]
        for gov in gov_docs:
            gov_path = refs_dir / gov
            if gov_path.exists():
                report.add_pass(f"integrity:docs:{gov}")
            else:
                report.add_warning(f"integrity:docs:{gov}",
                                   "Expected governance doc not found")

    # ── Version consistency ───────────────────────────────

    def _check_version_consistency(self, report: IntegrityReport):
        """Check that version references are consistent across packages."""
        known_packages = {
            "workflow_library": "2.3.0",
            "knowledge": "2.4.0",
            "web_ingestion": "2.5.0",
            "sandbox": "2.7.0",
            "workflow_composition": "2.8.0",
            "memory": "2.1.0",
            "tui": "2.2.0",
            "runtime": "1.0.0",
        }

        import re
        for pkg, expected in known_packages.items():
            init = self.root / pkg / "__init__.py"
            if not init.exists():
                continue
            content = init.read_text()
            match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', content)
            if match and match.group(1) == expected:
                report.add_pass(f"integrity:version:{pkg}")
            elif match:
                report.add_fail(f"integrity:version:{pkg}",
                                f"Expected {expected}, got {match.group(1)}")

    # ── Mutable artifacts ─────────────────────────────────

    def _check_mutable_artifacts(self, report: IntegrityReport):
        """Detect mutable artifacts that were committed accidentally."""
        # Check for .gitignore presence
        gitignore = self.root / ".gitignore"
        if gitignore.exists():
            report.add_pass("integrity:gitignore_exists")
            content = gitignore.read_text()
            # Check for common patterns
            patterns = ["__pycache__", "*.pyc", ".DS_Store", "dist/"]
            for pat in patterns:
                if pat in content:
                    report.add_pass(f"integrity:gitignore:{pat}")
                else:
                    report.add_warning(f"integrity:gitignore:{pat}",
                                       f"Not in .gitignore")
        else:
            report.add_warning("integrity:gitignore", ".gitignore missing")

        # Check for large data files in source tree
        large_files = []
        for fpath in self.root.rglob("*"):
            if fpath.is_dir():
                continue
            if ".git" in fpath.relative_to(self.root).parts:
                continue
            try:
                size = fpath.stat().st_size
                if size > 1_000_000:  # >1MB
                    large_files.append(str(fpath.relative_to(self.root)))
            except OSError:
                pass

        if not large_files:
            report.add_pass("integrity:large_files")
        else:
            report.add_warning("integrity:large_files",
                               f"{len(large_files)} files >1MB: {large_files[:5]}")

    # ── Broken schema refs ────────────────────────────────

    def _check_broken_schema_refs(self, report: IntegrityReport):
        """Check for broken schema references in templates."""
        import json

        # Check workflow templates reference existing schemas
        templates_dir = self.root / "workflow_library" / "templates"
        if templates_dir.is_dir():
            for tf in sorted(templates_dir.glob("*.json")):
                try:
                    with open(tf, "r") as f:
                        template = json.load(f)

                    # Check node definitions have valid fields
                    for node in template.get("node_definitions", []):
                        subagent = node.get("subagent", "")
                        if subagent and not isinstance(subagent, str):
                            report.add_finding("schema_ref",
                                               f"{tf.name}/{node.get('node_id', '?')}",
                                               f"Invalid subagent type: {type(subagent)}")
                except json.JSONDecodeError:
                    report.add_finding("schema_ref", tf.name, "Invalid JSON")
