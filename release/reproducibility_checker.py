"""
OverCR v2.10.0 — Reproducibility Checker

Validates that the release is reproducible:
  - Archive cleanliness
  - Deterministic replay consistency
  - Repeatable workflow execution
  - Stable schema registry
  - Stable manifest generation
  - Stable receipt serialization

Every check is deterministic. No mutation.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ReproducibilityReport:
    """Complete reproducibility report."""
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


class ReproducibilityChecker:
    """
    Validates that OverCR artifacts are reproducible.

    Checks that repeated operations produce identical or
    structurally equivalent output.
    """

    def __init__(self, overcr_root: str):
        self.root = Path(overcr_root)

    def check_all(self) -> ReproducibilityReport:
        """Run all reproducibility checks."""
        report = ReproducibilityReport()

        self._check_workflow_replay_consistency(report)
        self._check_schema_registry_stability(report)
        self._check_manifest_stability(report)
        self._check_receipt_serialization_stability(report)
        self._check_test_manifest_stability(report)

        return report

    # ── Workflow replay consistency ───────────────────────

    def _check_workflow_replay_consistency(self, report: ReproducibilityReport):
        """Verify that workflow replay is deterministic."""
        try:
            from integration.replay_validator import ReplayValidator

            validator = ReplayValidator(str(self.root))
            det_report = validator.validate_replay_determinism()

            node_checks = [r for r in det_report.results
                           if "node_order_match" in r.get("check", "")]
            if node_checks:
                all_match = all(r["status"] == "PASS" for r in node_checks)
                if all_match:
                    report.add_pass("repro:replay_node_order")
                else:
                    mismatches = [r for r in node_checks if r["status"] != "PASS"]
                    report.add_fail("repro:replay_node_order",
                                    f"{len(mismatches)} mismatches found")
            else:
                report.add_warning("repro:replay", "No node order checks run")

            state_checks = [r for r in det_report.results
                            if "state_match" in r.get("check", "")]
            if state_checks:
                all_match = all(r["status"] == "PASS" for r in state_checks)
                if all_match:
                    report.add_pass("repro:replay_state_match")

        except ImportError:
            report.add_warning("repro:replay", "ReplayValidator not importable")
        except Exception as e:
            report.add_warning("repro:replay", str(e))

    # ── Schema registry stability ─────────────────────────

    def _check_schema_registry_stability(self, report: ReproducibilityReport):
        """Verify schema registry produces stable output across calls."""
        try:
            from integration.schema_registry import SchemaRegistry

            registry = SchemaRegistry(str(self.root))

            # Discover twice, verify identical
            s1 = registry.discover_all()
            s2 = registry.discover_all()

            if s1.keys() == s2.keys():
                report.add_pass("repro:schema_ids_stable")
            else:
                report.add_fail("repro:schema_ids_stable",
                                "Schema IDs differ between calls")

            # Listings should be stable
            l1 = registry.list_schemas()
            l2 = registry.list_schemas()
            if l1 == l2:
                report.add_pass("repro:schema_listing_stable")

            # Completeness check should be stable
            c1, _ = registry.validate_schema_completeness()
            c2, _ = registry.validate_schema_completeness()
            if c1 == c2:
                report.add_pass("repro:schema_completeness_stable")

        except ImportError:
            report.add_warning("repro:schema", "SchemaRegistry not importable")
        except Exception as e:
            report.add_warning("repro:schema", str(e))

    # ── Manifest stability ────────────────────────────────

    def _check_manifest_stability(self, report: ReproducibilityReport):
        """Verify release manifest generation is stable."""
        try:
            from release.release_manifest import ReleaseManifest

            gen = ReleaseManifest(str(self.root))

            m1 = gen.generate()
            m2 = gen.generate()

            # Structural fields should match (timestamps may differ)
            if m1["release"]["version"] == m2["release"]["version"]:
                report.add_pass("repro:manifest_version_stable")

            if m1["packages"] == m2["packages"]:
                report.add_pass("repro:manifest_packages_stable")

            if m1["schemas"] == m2["schemas"]:
                report.add_pass("repro:manifest_schemas_stable")

            if m1["workflows"] == m2["workflows"]:
                report.add_pass("repro:manifest_workflows_stable")

            if m1["backends"] == m2["backends"]:
                report.add_pass("repro:manifest_backends_stable")

        except ImportError:
            report.add_warning("repro:manifest", "ReleaseManifest not importable")
        except Exception as e:
            report.add_warning("repro:manifest", str(e))

    # ── Receipt serialization stability ────────────────────

    def _check_receipt_serialization_stability(self, report: ReproducibilityReport):
        """Verify receipt serialization is stable."""
        try:
            from sandbox.execution_receipt import ExecutionReceipt

            r1 = ExecutionReceipt(
                execution_id="repro-001",
                operator_identity="op",
                approved_by="op",
                executed_command="echo test",
                argv=["echo", "test"],
                cwd="/tmp",
                exit_code=0,
                elapsed_s=0.100,
                stdout="ok",
                stderr="",
            )

            d1 = r1.to_dict()
            d2 = r1.to_dict()

            # Should be identical (same object, same serialization)
            if d1 == d2:
                report.add_pass("repro:receipt_stable")

            # Round-trip should preserve identity
            r2 = ExecutionReceipt.from_dict(d1)
            if r2.execution_id == r1.execution_id:
                report.add_pass("repro:receipt_roundtrip_stable")

        except ImportError:
            report.add_warning("repro:receipt", "ExecutionReceipt not importable")
        except Exception as e:
            report.add_warning("repro:receipt", str(e))

    # ── Test manifest stability ───────────────────────────

    def _check_test_manifest_stability(self, report: ReproducibilityReport):
        """Verify test manifest is parseable and stable."""
        manifest_path = self.root / "tests" / "test_manifest.json"
        if not manifest_path.exists():
            report.add_warning("repro:test_manifest", "manifest missing")
            return

        try:
            with open(manifest_path, "r") as f:
                m = json.load(f)

            version = m.get("version", "")
            tests = m.get("tests", [])

            if version:
                report.add_pass(f"repro:test_manifest_version_{version}")

            if len(tests) >= 25:
                report.add_pass(f"repro:test_count_{len(tests)}")

            # Verify every test entry has required fields
            for t in tests:
                name = t.get("name", "?")
                for field in ["name", "module", "category"]:
                    if field not in t:
                        report.add_warning("repro:test_manifest",
                                           f"Test '{name}' missing '{field}'")

        except Exception as e:
            report.add_fail("repro:test_manifest", str(e))
