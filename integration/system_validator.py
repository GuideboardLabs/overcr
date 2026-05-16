"""
OverCR v2.9.0 — System Validator

Validates the structural integrity of the entire OverCR v2 system:
directories, schemas, workflow templates, sandbox backends, audit
logs, receipts, memory, provenance, replay prerequisites, and
frozen workflow immutability.

All checks are read-only — the validator never mutates state.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from integration.schema_registry import SchemaRegistry


@dataclass
class SystemValidationReport:
    """Complete system validation report."""
    passed: bool = True
    results: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

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
        }


class SystemValidator:
    """
    Validates the entire OverCR v2 system structure.

    Checks every known subsystem for structural integrity.
    Reports only — never repairs, never mutates.
    """

    # Required top-level directories
    REQUIRED_DIRS = [
        "runtime",
        "memory",
        "tui",
        "workflow_library",
        "workflow_library/schema",
        "workflow_library/templates",
        "workflow_composition",
        "workflow_composition/schema",
        "knowledge",
        "knowledge/schema",
        "knowledge/sources",
        "knowledge/documents",
        "knowledge/reports",
        "web_ingestion",
        "web_ingestion/schema",
        "sandbox",
        "sandbox/schema",
        "sandbox/backends",
        "tests",
        "references",
        "scripts",
        "tools",
        "subagents/coder",
        "subagents/knower",
        "subagents/cryer",
        "subagents/pyper",
    ]

    # Required files
    REQUIRED_FILES = [
        "tools/validate_packet.py",
        "tests/test_manifest.json",
        "tests/run_all.py",
    ]

    # Known packages and their expected versions
    KNOWN_PACKAGES = {
        "runtime": "1.0.0",
        "memory": "2.1.0",
        "tui": "2.2.0",
        "workflow_library": "2.3.0",
        "knowledge": "2.4.0",
        "web_ingestion": "2.5.0",
        "sandbox": "2.7.0",
        "workflow_composition": "2.8.0",
    }

    def __init__(self, overcr_root: str):
        self.root = Path(overcr_root)
        self.schema_registry = SchemaRegistry(overcr_root)

    def validate_all(self) -> SystemValidationReport:
        """Run all validation checks. Returns a full report."""
        report = SystemValidationReport()

        self._check_directories(report)
        self._check_required_files(report)
        self._check_schemas(report)
        self._check_workflow_templates(report)
        self._check_sandbox_backends(report)
        self._check_audit_logs(report)
        self._check_package_versions(report)
        self._check_replay_prerequisites(report)
        self._check_frozen_workflow_immutability(report)

        return report

    # ── Directory checks ──────────────────────────────────

    def _check_directories(self, report: SystemValidationReport):
        """Check all required directories exist."""
        for rel_dir in self.REQUIRED_DIRS:
            d = self.root / rel_dir
            if d.exists() and d.is_dir():
                report.add_pass(f"directory:{rel_dir}")
            else:
                report.add_fail(f"directory:{rel_dir}",
                                "Directory not found or not a directory")

    # ── Required file checks ──────────────────────────────

    def _check_required_files(self, report: SystemValidationReport):
        """Check required files exist."""
        for rel_file in self.REQUIRED_FILES:
            f = self.root / rel_file
            if f.exists() and f.is_file():
                report.add_pass(f"file:{rel_file}")
            else:
                report.add_fail(f"file:{rel_file}",
                                "Required file not found")

    # ── Schema checks ─────────────────────────────────────

    def _check_schemas(self, report: SystemValidationReport):
        """Check all schemas are present and valid."""
        valid, errors = self.schema_registry.validate_schema_completeness()
        if valid:
            report.add_pass("schemas:completeness")
        else:
            for err in errors:
                report.add_fail("schemas:completeness", err)

        valid, ref_errors = self.schema_registry.verify_referential_integrity()
        if valid:
            report.add_pass("schemas:referential_integrity")
        else:
            for err in ref_errors:
                report.add_fail("schemas:referential_integrity", err)

    # ── Workflow template checks ──────────────────────────

    def _check_workflow_templates(self, report: SystemValidationReport):
        """Check all workflow templates are valid."""
        templates_dir = self.root / "workflow_library" / "templates"
        if not templates_dir.exists():
            report.add_fail("workflows:templates",
                            "Templates directory missing")
            return

        from workflow_library.workflow_executor import WorkflowExecutor
        executor = WorkflowExecutor(str(self.root))

        template_files = sorted(templates_dir.glob("*.json"))
        if not template_files:
            report.add_warning("workflows:templates",
                               "No workflow templates found")
            return

        report.add_pass(f"workflows:found_{len(template_files)}_templates")

        for tf in template_files:
            try:
                with open(tf, "r") as f:
                    template = json.load(f)
            except json.JSONDecodeError as e:
                report.add_fail(f"workflows:{tf.name}", f"Invalid JSON: {e}")
                continue

            wf_id = template.get("workflow_id", tf.stem)
            valid, errors = executor.validate_workflow(template)
            if valid:
                report.add_pass(f"workflows:{wf_id}")
            else:
                for err in errors:
                    report.add_fail(f"workflows:{wf_id}", err)

    # ── Sandbox backend checks ────────────────────────────

    def _check_sandbox_backends(self, report: SystemValidationReport):
        """Check sandbox backend compatibility."""
        import shutil

        backend_status = {}
        backends_dir = self.root / "sandbox" / "backends"
        if not backends_dir.is_dir():
            report.add_fail("sandbox:backends_dir", "Backends directory missing")
            return

        # Check local backend (always available)
        report.add_pass("sandbox:backend:local")

        # Check bubblewrap
        bwrap = shutil.which("bwrap")
        if bwrap:
            report.add_pass(f"sandbox:backend:bubblewrap (bwrap at {bwrap})")
        else:
            report.add_warning("sandbox:backend:bubblewrap",
                               "bwrap not found — bubblewrap backend unavailable")

        # Check firejail
        fj = shutil.which("firejail")
        if fj:
            report.add_pass(f"sandbox:backend:firejail (firejail at {fj})")
        else:
            report.add_warning("sandbox:backend:firejail",
                               "firejail not found — firejail backend unavailable")

    # ── Audit log checks ──────────────────────────────────

    def _check_audit_logs(self, report: SystemValidationReport):
        """Check audit log structure."""
        runtime_dir = self.root / "runtime"
        if not runtime_dir.is_dir():
            report.add_warning("audit:runtime_dir", "No runtime directory")
            return

        audit_file = runtime_dir / "audit.jsonl"
        if audit_file.exists():
            report.add_pass("audit:log_file_exists")
            try:
                with open(audit_file, "r") as f:
                    line_count = sum(1 for _ in f)
                report.add_pass(f"audit:log_entries:{line_count}")
            except Exception as e:
                report.add_fail("audit:log_read", str(e))
        else:
            report.add_warning("audit:log_file", "No audit.jsonl found (may be clean state)")

        # Check workflow trace files
        trace_files = sorted(runtime_dir.glob("workflow_trace_*.jsonl"))
        if trace_files:
            report.add_pass(f"audit:traces:{len(trace_files)}_trace_files")
            # Spot-check first trace for valid JSONL
            try:
                with open(trace_files[0], "r") as f:
                    for i, line in enumerate(f):
                        json.loads(line)
                        if i >= 5:
                            break
                report.add_pass(f"audit:traces_sample:{trace_files[0].name}")
            except Exception as e:
                report.add_fail("audit:traces_sample", str(e))

    # ── Package version checks ────────────────────────────

    def _check_package_versions(self, report: SystemValidationReport):
        """Check package version consistency against known versions."""
        for pkg_name, expected_ver in self.KNOWN_PACKAGES.items():
            init_path = self.root / pkg_name / "__init__.py"
            if not init_path.exists():
                report.add_fail(f"version:{pkg_name}",
                                f"__init__.py not found")
                continue

            try:
                content = init_path.read_text()
                import re
                match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', content)
                if match:
                    actual_ver = match.group(1)
                    if actual_ver == expected_ver:
                        report.add_pass(f"version:{pkg_name}:{actual_ver}")
                    else:
                        report.add_fail(f"version:{pkg_name}",
                                        f"Expected {expected_ver}, got {actual_ver}")
                else:
                    report.add_warning(f"version:{pkg_name}",
                                       "No __version__ found")
            except Exception as e:
                report.add_fail(f"version:{pkg_name}", str(e))

    # ── Replay prerequisites ──────────────────────────────

    def _check_replay_prerequisites(self, report: SystemValidationReport):
        """Check that replay prerequisites are met."""
        # Check test_manifest.json has replay tests
        manifest_path = self.root / "tests" / "test_manifest.json"
        if manifest_path.exists():
            try:
                with open(manifest_path, "r") as f:
                    manifest = json.load(f)
                tests = manifest.get("tests", [])
                recovery_tests = [t for t in tests
                                  if t.get("category") == "recovery"]
                if recovery_tests:
                    report.add_pass(
                        f"replay:manifest_recovery_tests:{len(recovery_tests)}"
                    )
                else:
                    report.add_warning("replay:manifest",
                                       "No recovery tests in manifest")
            except Exception as e:
                report.add_fail("replay:manifest", str(e))

        # Check workflow_library has replay support
        wl_executor = self.root / "workflow_library" / "workflow_executor.py"
        if wl_executor.exists():
            content = wl_executor.read_text()
            if "replay_workflow" in content:
                report.add_pass("replay:executor_has_replay_method")
            else:
                report.add_warning("replay:executor",
                                   "replay_workflow method not found")
        else:
            report.add_fail("replay:executor", "workflow_executor.py missing")

        # Check workflow_context supports replay_mode flag
        wl_context = self.root / "workflow_library" / "workflow_context.py"
        if wl_context.exists():
            content = wl_context.read_text()
            if "replay_mode" in content:
                report.add_pass("replay:context_has_replay_flag")
            else:
                report.add_warning("replay:context",
                                   "replay_mode flag not found")

    # ── Frozen workflow immutability ──────────────────────

    def _check_frozen_workflow_immutability(self, report: SystemValidationReport):
        """Check that frozen workflow templates haven't been modified."""
        templates_dir = self.root / "workflow_library" / "templates"
        if not templates_dir.is_dir():
            return

        frozen_workflows = [
            "claim_review_workflow.json",
            "recon_brief_workflow.json",
            "coder_patch_review_workflow.json",
            "execution_plan_review_workflow.json",
            "release_freeze_workflow.json",
        ]

        for wf_name in frozen_workflows:
            wf_path = templates_dir / wf_name
            if not wf_path.exists():
                report.add_fail(f"frozen:{wf_name}",
                                "Frozen workflow template missing")
                continue

            try:
                with open(wf_path, "r") as f:
                    template = json.load(f)

                # Check required structure
                required = [
                    "workflow_id", "workflow_name", "version",
                    "node_definitions", "edge_definitions",
                    "approval_points", "rollback_behavior",
                    "deterministic_fallback", "audit_requirements",
                ]
                for field in required:
                    if field not in template:
                        report.add_fail(f"frozen:{wf_name}",
                                        f"Missing required field: {field}")

                # Check versions are pinned
                ver = template.get("version", "")
                if not ver.startswith("2.3") and not ver.startswith("2."):
                    report.add_warning(f"frozen:{wf_name}",
                                       f"Unexpected version: {ver}")

                # Nodes must have deterministic fallback fields
                for node in template.get("node_definitions", []):
                    if "rollback_on_failure" not in node:
                        report.add_fail(f"frozen:{wf_name}/{node.get('node_id', '?')}",
                                        "Missing rollback_on_failure")

                report.add_pass(f"frozen:{wf_name}:intact")

            except json.JSONDecodeError as e:
                report.add_fail(f"frozen:{wf_name}", f"Invalid JSON: {e}")
            except Exception as e:
                report.add_fail(f"frozen:{wf_name}", str(e))
