"""
OverCR v2.9.0 — Migration Checker

Validates v1 → v2 compatibility assumptions without performing
automatic migrations. Checks schema versioning consistency,
workflow version pinning, backward compatibility metadata, and
frozen release upgrade paths.

This is validation-only — the checker never auto-converts artifacts.
"""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class MigrationReport:
    """Complete migration compatibility report."""
    passed: bool = True
    results: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    upgrade_path_viable: bool = True

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
            "upgrade_path_viable": self.upgrade_path_viable,
        }


class MigrationChecker:
    """
    Validates migration compatibility across version boundaries.

    Checks v1 → v2 compatibility, schema versioning consistency,
    workflow version pinning, and backward compatibility metadata
    without performing any automatic conversions.
    """

    # Known v1 components that must be preserved
    V1_PRESERVED_COMPONENTS = {
        "tools/validate_packet.py": "L1-L6 validation",
        "runtime/__init__.py": "Runtime version 1.0.0",
        "subagents/coder/": "CodER worker",
        "subagents/knower/": "KnowER worker",
        "subagents/cryer/": "CryER worker",
        "subagents/pyper/": "PypER worker",
        "orchestration/task_counter.json": "Task counter",
    }

    def __init__(self, overcr_root: str):
        self.root = Path(overcr_root)

    def check_all(self) -> MigrationReport:
        """Run all migration compatibility checks."""
        report = MigrationReport()

        self._check_v1_preservation(report)
        self._check_schema_versioning(report)
        self._check_workflow_pinning(report)
        self._check_backward_compat_metadata(report)
        self._check_upgrade_paths(report)

        return report

    # ── V1 preservation ──────────────────────────────────

    def _check_v1_preservation(self, report: MigrationReport):
        """Check that v1 components are preserved in v2."""
        for path, desc in self.V1_PRESERVED_COMPONENTS.items():
            full_path = self.root / path
            if full_path.exists():
                report.add_pass(f"migration:v1_preserved:{path}")
            else:
                report.add_fail(f"migration:v1_preserved:{path}",
                                f"V1 component missing: {desc}")

        # Check validate_packet.py is still the canonical validator
        vp = self.root / "tools" / "validate_packet.py"
        if vp.exists():
            content = vp.read_text()
            if "def validate_packet" in content:
                report.add_pass("migration:v1_validate_packet_signature")
            else:
                report.add_fail("migration:v1_validate_packet",
                                "validate_packet function missing")
        else:
            report.add_fail("migration:v1_validate_packet",
                            "tools/validate_packet.py not found")

    # ── Schema versioning ────────────────────────────────

    def _check_schema_versioning(self, report: MigrationReport):
        """Check that schema versions are consistent and traceable."""
        import json

        # Check workflow template schema versioning
        schema_path = self.root / "workflow_library" / "schema" / "workflow_template.schema.json"
        if not schema_path.exists():
            report.add_fail("migration:schema:workflow_template",
                            "Schema file missing")
            return

        try:
            with open(schema_path, "r") as f:
                schema = json.load(f)
            title = schema.get("title", "")
            if "2.3.0" in title:
                report.add_pass("migration:schema:workflow_template_versioned")
            else:
                report.add_warning("migration:schema:workflow_template",
                                   f"Title: {title} — check version pinning")
        except json.JSONDecodeError as e:
            report.add_fail("migration:schema:workflow_template", f"Invalid JSON: {e}")

        # Check composite workflow schema
        comp_schema_path = self.root / "workflow_composition" / "schema" / "composite_workflow.schema.json"
        if comp_schema_path.exists():
            try:
                with open(comp_schema_path, "r") as f:
                    comp_schema = json.load(f)
                title = comp_schema.get("title", "")
                if "2.8.0" in title:
                    report.add_pass("migration:schema:composite_versioned")
                else:
                    report.add_warning("migration:schema:composite",
                                       f"Title: {title} — check version pinning")
            except json.JSONDecodeError as e:
                report.add_fail("migration:schema:composite", f"Invalid JSON: {e}")
        else:
            report.add_warning("migration:schema:composite",
                               "composite_workflow.schema.json not found")

    # ── Workflow version pinning ─────────────────────────

    def _check_workflow_pinning(self, report: MigrationReport):
        """Check that workflow templates have pinned versions."""
        import json
        templates_dir = self.root / "workflow_library" / "templates"

        if not templates_dir.is_dir():
            report.add_warning("migration:pin:templates", "No templates directory")
            return

        for tf in sorted(templates_dir.glob("*.json")):
            try:
                with open(tf, "r") as f:
                    template = json.load(f)

                wf_id = template.get("workflow_id", tf.stem)
                version = template.get("version", "")

                if version:
                    report.add_pass(f"migration:pin:{wf_id}:{version}")
                else:
                    report.add_warning(f"migration:pin:{wf_id}",
                                       "No version field")

                # Check subworkflow refs have pinned versions (if present)
                subworkflow_refs = template.get("subworkflow_refs", [])
                for ref in subworkflow_refs:
                    ref_id = ref.get("ref_id", "?")
                    ref_ver = ref.get("version", "")
                    if ref_ver:
                        report.add_pass(
                            f"migration:pin:{wf_id}:subref_{ref_id}_{ref_ver}"
                        )
                    else:
                        report.add_warning(
                            f"migration:pin:{wf_id}:subref_{ref_id}",
                            "Subworkflow ref missing version pin"
                        )

            except json.JSONDecodeError as e:
                report.add_fail(f"migration:pin:{tf.name}", f"Invalid JSON: {e}")

    # ── Backward compatibility metadata ──────────────────

    def _check_backward_compat_metadata(self, report: MigrationReport):
        """Check for backward compatibility metadata."""
        import json

        # Check test manifest has version tracking
        manifest_path = self.root / "tests" / "test_manifest.json"
        if manifest_path.exists():
            try:
                with open(manifest_path, "r") as f:
                    manifest = json.load(f)
                version = manifest.get("version", "")
                if version:
                    report.add_pass(f"migration:compat:manifest_version_{version}")
                else:
                    report.add_warning("migration:compat:manifest",
                                       "No version in test manifest")

                # Check test categories include all v1+v2 subsystems
                categories = set(t.get("category", "") for t in manifest.get("tests", []))
                expected = {"governance", "audit", "recovery", "workflow",
                            "memory", "tui", "worker", "inference",
                            "validation", "sovereignty", "routing"}
                missing = expected - categories
                if missing:
                    report.add_warning("migration:compat:test_categories",
                                       f"Missing categories: {missing}")
                else:
                    report.add_pass("migration:compat:test_categories")

            except json.JSONDecodeError as e:
                report.add_fail("migration:compat:manifest", f"Invalid JSON: {e}")
        else:
            report.add_fail("migration:compat:manifest", "test_manifest.json missing")

    # ── Upgrade paths ────────────────────────────────────

    def _check_upgrade_paths(self, report: MigrationReport):
        """Validate upgrade paths between versions, handling in-place evolution."""
        import json

        versions = ["2.3.0", "2.4.0", "2.5.0", "2.6.0", "2.7.0", "2.8.0"]
        version_init = {
            "2.3.0": "workflow_library/__init__.py",
            "2.4.0": "knowledge/__init__.py",
            "2.5.0": "web_ingestion/__init__.py",
            "2.6.0": "sandbox/__init__.py",  # sandbox evolved to v2.7.0
            "2.7.0": "sandbox/__init__.py",
            "2.8.0": "workflow_composition/__init__.py",
        }

        # Packages where versions evolved in-place (e.g. sandbox 2.6.0 -> 2.7.0)
        EVOLVED_PACKAGES = {"2.6.0": "2.7.0"}

        all_found = True
        for ver in versions:
            init_path = self.root / version_init[ver]
            if init_path.exists():
                import re
                content = init_path.read_text()
                match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', content)
                if match and match.group(1) == ver:
                    report.add_pass(f"migration:upgrade:{ver}_present")
                elif match and ver in EVOLVED_PACKAGES and match.group(1) == EVOLVED_PACKAGES[ver]:
                    report.add_pass(f"migration:upgrade:{ver}_evolved_to_{match.group(1)}")
                elif match:
                    report.add_fail(f"migration:upgrade:{ver}",
                                    f"Expected {ver}, found {match.group(1)}")
                    all_found = False
                else:
                    report.add_warning(f"migration:upgrade:{ver}",
                                       "No __version__ found")
            else:
                report.add_fail(f"migration:upgrade:{ver}",
                                f"{version_init[ver]} not found")
                all_found = False

        if all_found:
            report.add_pass("migration:upgrade_chain_intact")
        else:
            report.add_warning("migration:upgrade_chain",
                               "Some version links are broken")
            report.upgrade_path_viable = False
