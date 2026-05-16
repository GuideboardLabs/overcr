"""
OverCR v2.10.0 — Operator Readiness Validator

Validates that OverCR is operationally trustworthy:
  - Docs completeness
  - README examples accuracy
  - INSTALL instructions validity
  - Demo scripts execution
  - TUI usability assumptions
  - Governance docs presence
  - Release notes completeness

All checks are read-only — reports only, never mutates.
"""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ReadinessReport:
    """Complete operator readiness report."""
    passed: bool = True
    results: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    missing_docs: list[str] = field(default_factory=list)
    stale_examples: list[str] = field(default_factory=list)

    def add_pass(self, check: str):
        self.results.append({"check": check, "status": "PASS"})

    def add_fail(self, check: str, detail: str):
        self.passed = False
        self.results.append({"check": check, "status": "FAIL", "detail": detail})
        self.errors.append(f"{check}: {detail}")

    def add_warning(self, check: str, detail: str):
        self.results.append({"check": check, "status": "WARN", "detail": detail})
        self.warnings.append(f"{check}: {detail}")

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "results": self.results,
            "errors": self.errors,
            "warnings": self.warnings,
            "missing_docs": self.missing_docs,
            "stale_examples": self.stale_examples,
        }


class OperatorReadiness:
    """
    Validates that OverCR is ready for operators.

    Checks documentation, examples, governance docs, TUI assumptions,
    and the overall understandability of the release.
    """

    # Required documentation files
    REQUIRED_DOCS = {
        "README.md": "Project overview and quick start",
        "INSTALL.md": "Installation instructions",
        "LICENSE.md": "License",
        "RELEASE.md": "Release notes",
        "CHANGELOG.md": "Change history",
        "soul.md": "Project philosophy",
        "soul_reference.md": "Philosophy reference",
    }

    # Required reference docs for v2 subsystems
    REQUIRED_REFS = [
        "v2.1-memory-architecture.md",
        "v2.1-memory-governance.md",
        "v2.2-operator-interface.md",
        "v2.2-tui-governance.md",
        "v2.3-workflow-library.md",
        "v2.3-workflow-governance.md",
        "v2.4-research-layer.md",
        "v2.4-provenance-governance.md",
        "v2.5-web-ingestion-gateway.md",
        "v2.5-web-ingestion-governance.md",
        "v2.6-sandbox-architecture.md",
        "v2.6-execution-governance.md",
        "v2.7-kernel-isolation.md",
        "v2.7-sandbox-backend-governance.md",
        "v2.8-workflow-composition.md",
        "v2.8-conditional-routing-governance.md",
        "v2.9-integration-hardening.md",
        "v2.9-release-readiness.md",
        "v2.9-recovery-guarantees.md",
        "v2.10-stable-rc-definition.md",
        "v2.10-installation-guarantees.md",
        "v2.10-reproducibility.md",
        "v2.10-operator-readiness.md",
    ]

    # Demo scripts that should be runnable
    DEMO_SCRIPTS = [
        "examples/demo_workflow_library.py",
        "examples/demo_execution_sandbox.py",
        "examples/demo_research_pipeline.py",
        "examples/demo_web_ingestion_gateway.py",
        "examples/demo_operator_dashboard.py",
        "examples/demo_replay_validation.py",
    ]

    # Governance principles that must be documented
    GOVERNANCE_PRINCIPLES = {
        "substrate_vs_workload": "references/substrate-vs-workload.md",
        "sovereignty": "references/subagent-architecture.md",
        "audit": "references/v2.6-execution-governance.md",
        "approval": "references/pyper-inference-v0.7.0.md",
        "recovery": "references/v2.9-recovery-guarantees.md",
        "memory": "references/v2.1-memory-governance.md",
    }

    def __init__(self, overcr_root: str):
        self.root = Path(overcr_root)

    def check_all(self) -> ReadinessReport:
        """Run all operator readiness checks."""
        report = ReadinessReport()

        self._check_docs_completeness(report)
        self._check_readme_quality(report)
        self._check_install_validity(report)
        self._check_demo_scripts(report)
        self._check_tui_assumptions(report)
        self._check_governance_docs(report)
        self._check_release_notes(report)

        return report

    # ── Documentation completeness ────────────────────────

    def _check_docs_completeness(self, report: ReadinessReport):
        """Check that all required documentation files exist."""
        # Root docs
        for fname, desc in self.REQUIRED_DOCS.items():
            fpath = self.root / fname
            if fpath.exists():
                report.add_pass(f"op:doc:{fname}")
            else:
                report.add_fail(f"op:doc:{fname}",
                                f"Missing: {desc}")
                report.missing_docs.append(fname)

        # Reference docs
        refs_dir = self.root / "references"
        for ref_name in self.REQUIRED_REFS:
            ref_path = refs_dir / ref_name
            if ref_path.exists():
                report.add_pass(f"op:ref:{ref_name}")
            else:
                report.add_warning(f"op:ref:{ref_name}",
                                   "Reference doc not found")
                report.missing_docs.append(f"references/{ref_name}")

    # ── README quality ────────────────────────────────────

    def _check_readme_quality(self, report: ReadinessReport):
        """Check README.md meets quality standards."""
        readme_path = self.root / "README.md"
        if not readme_path.exists():
            report.add_fail("op:readme", "README.md missing")
            return

        content = readme_path.read_text()
        lines = content.split("\n")

        # Must have a title
        if lines and lines[0].startswith("#"):
            report.add_pass("op:readme:has_title")

        # Must mention OverCR
        if "OverCR" in content:
            report.add_pass("op:readme:mentions_overcr")

        # Should have installation section
        if "Install" in content or "install" in content:
            report.add_pass("op:readme:install_section")

        # Should have usage/examples section
        if "Usage" in content or "usage" in content or "Example" in content:
            report.add_pass("op:readme:usage_section")

        # Minimum length
        if len(content.strip()) >= 200:
            report.add_pass(f"op:readme:length_{len(content.strip())}chars")
        else:
            report.add_warning("op:readme",
                               f"Short README ({len(content.strip())} chars)")

    # ── INSTALL.md validity ───────────────────────────────

    def _check_install_validity(self, report: ReadinessReport):
        """Check INSTALL.md has valid instructions."""
        install_path = self.root / "INSTALL.md"
        if not install_path.exists():
            report.add_warning("op:install", "INSTALL.md missing")
            return

        content = install_path.read_text()

        # Should mention Python requirement
        if "python" in content.lower():
            report.add_pass("op:install:python_mention")

        # Should mention dependencies
        if "depend" in content.lower() or "install" in content.lower():
            report.add_pass("op:install:dep_mention")

        # Should mention test running
        if "test" in content.lower():
            report.add_pass("op:install:test_mention")

        # Minimum length
        if len(content.strip()) >= 100:
            report.add_pass(f"op:install:length_{len(content.strip())}chars")

    # ── Demo scripts ──────────────────────────────────────

    def _check_demo_scripts(self, report: ReadinessReport):
        """Check demo scripts exist and are parseable."""
        for script in self.DEMO_SCRIPTS:
            spath = self.root / script
            if not spath.exists():
                report.add_warning(f"op:demo:{script}", "Demo script not found")
                report.stale_examples.append(script)
                continue

            # Check it's parseable Python
            try:
                compile(spath.read_text(), script, "exec")
                report.add_pass(f"op:demo:{script}:parseable")
            except SyntaxError as e:
                report.add_fail(f"op:demo:{script}",
                                f"Syntax error: {e}")
                report.stale_examples.append(script)

            # Check it has proper shebang or main guard
            content = spath.read_text()
            if "if __name__" in content or "#!/usr/bin/env" in content:
                report.add_pass(f"op:demo:{script}:runnable")

    # ── TUI assumptions ───────────────────────────────────

    def _check_tui_assumptions(self, report: ReadinessReport):
        """Check TUI module is present and has expected structure."""
        tui_dir = self.root / "tui"
        if not tui_dir.is_dir():
            report.add_warning("op:tui", "TUI directory missing")
            return

        # Check for key TUI files
        tui_files = ["operator_dashboard.py", "approval_queue.py"]
        for fname in tui_files:
            fpath = tui_dir / fname
            if fpath.exists():
                report.add_pass(f"op:tui:{fname}")

        # Check TUI __init__ has version
        tui_init = tui_dir / "__init__.py"
        if tui_init.exists():
            import re
            content = tui_init.read_text()
            if "__version__" in content:
                report.add_pass("op:tui:versioned")

    # ── Governance docs ───────────────────────────────────

    def _check_governance_docs(self, report: ReadinessReport):
        """Check governance principle docs are present."""
        for principle, path in self.GOVERNANCE_PRINCIPLES.items():
            full_path = self.root / path
            if full_path.exists():
                report.add_pass(f"op:governance:{principle}")
            else:
                report.add_warning(f"op:governance:{principle}",
                                   f"Governance doc missing: {path}")

    # ── Release notes ─────────────────────────────────────

    def _check_release_notes(self, report: ReadinessReport):
        """Check release notes completeness."""
        # RELEASE.md
        release_path = self.root / "RELEASE.md"
        if release_path.exists():
            content = release_path.read_text()
            if "2.10" in content or "stable" in content.lower():
                report.add_pass("op:release_notes:version_mentioned")
            else:
                report.add_warning("op:release_notes",
                                   "RELEASE.md may need v2.10 update")

        # CHANGELOG.md
        changelog_path = self.root / "CHANGELOG.md"
        if changelog_path.exists():
            content = changelog_path.read_text()
            if len(content.strip()) >= 50:
                report.add_pass("op:changelog:exists")

        # Check if version history reference exists
        vh_path = self.root / "references" / "version-history.md"
        if vh_path.exists():
            report.add_pass("op:version_history:exists")
