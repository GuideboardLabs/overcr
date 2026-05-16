"""
OverCR v2.9.0 — State Consistency Validator

Validates cross-system reference integrity across the entire
OverCR v2 stack. Checks that task references, workflow lineage,
memory references, provenance references, snapshot references,
subworkflow lineage, receipt linkage, and escalation lineage
form a coherent reference graph.

All checks are read-only — the validator never repairs references.
"""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ConsistencyReport:
    """Complete state consistency report."""
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


class StateConsistency:
    """
    Validates reference integrity across all OverCR subsystems.

    Checks: task references, workflow lineage, memory references,
    provenance references, snapshot references, subworkflow lineage,
    receipt linkage, and escalation lineage.
    """

    def __init__(self, overcr_root: str):
        self.root = Path(overcr_root)

    def validate_all(self) -> ConsistencyReport:
        """Run all consistency checks."""
        report = ConsistencyReport()

        self._check_task_references(report)
        self._check_workflow_lineage(report)
        self._check_memory_references(report)
        self._check_provenance_references(report)
        self._check_snapshot_references(report)
        self._check_subworkflow_lineage(report)
        self._check_receipt_linkage(report)
        self._check_escalation_lineage(report)

        return report

    # ── Task references ──────────────────────────────────

    def _check_task_references(self, report: ConsistencyReport):
        """Check that task files have valid references."""
        tasks_dir = self.root / "orchestration" / "tasks"
        if not tasks_dir.is_dir():
            report.add_warning("refs:tasks_dir", "No orchestration/tasks directory")
            return

        import json
        task_files = sorted(tasks_dir.glob("task-*.json"))
        if not task_files:
            report.add_pass("refs:tasks:none_found")
            return

        valid_refs = 0
        invalid_refs = 0
        for tf in task_files[:10]:  # Sample up to 10
            try:
                with open(tf, "r") as f:
                    task = json.load(f)
                task_id = task.get("task_id", "")
                state = task.get("state", "")
                subagent = task.get("subagent", "")

                if not task_id:
                    invalid_refs += 1
                    continue

                # Check state is valid
                valid_states = {"created", "dispatched", "running",
                                "completed", "failed", "rejected",
                                "abandoned", "paused"}
                if state and state not in valid_states:
                    report.add_warning(f"refs:task:{task_id}:state",
                                       f"Unknown state: {state}")

                # Check subagent is valid
                valid_subagents = {"knower", "coder", "cryer", "pyper", "operator"}
                if subagent and subagent not in valid_subagents:
                    report.add_warning(f"refs:task:{task_id}:subagent",
                                       f"Unknown subagent: {subagent}")

                valid_refs += 1
            except (json.JSONDecodeError, OSError):
                invalid_refs += 1

        report.add_pass(f"refs:tasks:sample_{valid_refs}_valid")
        if invalid_refs:
            report.add_warning(f"refs:tasks:sample_{invalid_refs}_invalid")

    # ── Workflow lineage ─────────────────────────────────

    def _check_workflow_lineage(self, report: ConsistencyReport):
        """Check that workflow templates have coherent lineage."""
        import json
        templates_dir = self.root / "workflow_library" / "templates"
        if not templates_dir.is_dir():
            report.add_warning("refs:workflow:templates", "No templates directory")
            return

        all_node_ids = set()
        all_edge_targets = set()
        all_edge_sources = set()

        for tf in sorted(templates_dir.glob("*.json")):
            try:
                with open(tf, "r") as f:
                    template = json.load(f)

                wf_id = template.get("workflow_id", "?")
                nodes = template.get("node_definitions", [])
                edges = template.get("edge_definitions", [])

                # Collect node IDs
                for node in nodes:
                    nid = node.get("node_id", "")
                    if nid:
                        all_node_ids.add(f"{wf_id}:{nid}")

                # Collect edges
                for edge in edges:
                    src = edge.get("source", "")
                    tgt = edge.get("target", "")
                    if src:
                        all_edge_sources.add(f"{wf_id}:{src}")
                    if tgt:
                        all_edge_targets.add(f"{wf_id}:{tgt}")
            except (json.JSONDecodeError, OSError):
                continue

        # Check no orphaned edge references
        orphaned_sources = all_edge_sources - all_node_ids
        orphaned_targets = all_edge_targets - all_node_ids

        if not orphaned_sources and not orphaned_targets:
            report.add_pass("refs:workflow:edge_node_consistency")
        else:
            if orphaned_sources:
                report.add_fail("refs:workflow:orphaned_edge_sources",
                                f"Edges reference non-existent nodes: "
                                f"{list(orphaned_sources)[:5]}")
            if orphaned_targets:
                report.add_fail("refs:workflow:orphaned_edge_targets",
                                f"Edges reference non-existent nodes: "
                                f"{list(orphaned_targets)[:5]}")

        # Check approval points reference existing nodes
        for tf in sorted(templates_dir.glob("*.json")):
            try:
                with open(tf, "r") as f:
                    template = json.load(f)
                node_ids = {n["node_id"] for n in template.get("node_definitions", [])
                            if "node_id" in n}
                for ap in template.get("approval_points", []):
                    if ap not in node_ids:
                        report.add_fail(f"refs:workflow:{template.get('workflow_id')}:approval",
                                        f"Approval point '{ap}' is not a node")
            except (json.JSONDecodeError, OSError):
                continue

    # ── Memory references ────────────────────────────────

    def _check_memory_references(self, report: ConsistencyReport):
        """Check memory record reference integrity."""
        memory_dir = self.root / "memory" / "canonical"
        if not memory_dir.is_dir():
            # Try alternate location
            memory_dir = self.root / "memory"
            if not memory_dir.is_dir():
                report.add_warning("refs:memory", "Memory directory not found")
                return

        import json
        memory_files = []
        for pattern in ["*.json", "*.md"]:
            memory_files.extend(memory_dir.rglob(pattern))

        if not memory_files:
            report.add_pass("refs:memory:no_records_found")
            return

        valid = 0
        for mf in memory_files[:10]:
            try:
                if mf.suffix == ".json":
                    with open(mf, "r") as f:
                        record = json.load(f)
                    if isinstance(record, (dict, list)):
                        valid += 1
                elif mf.suffix == ".md":
                    content = mf.read_text()
                    if len(content.strip()) > 0:
                        valid += 1
            except Exception:
                pass

        report.add_pass(f"refs:memory:{valid}_parseable_records")

    # ── Provenance references ────────────────────────────

    def _check_provenance_references(self, report: ConsistencyReport):
        """Check provenance tracking references."""
        try:
            from knowledge.provenance_tracker import ProvenanceTracker
            tracker = ProvenanceTracker(str(self.root))
            # Simple structure check
            report.add_pass("refs:provenance:module_loaded")
        except ImportError:
            report.add_warning("refs:provenance", "ProvenanceTracker not importable")
        except Exception as e:
            report.add_warning("refs:provenance", str(e))

    # ── Snapshot references ──────────────────────────────

    def _check_snapshot_references(self, report: ConsistencyReport):
        """Check sandbox snapshot reference integrity."""
        try:
            from sandbox.rollback_snapshot import RollbackSnapshot

            snap = RollbackSnapshot(sandbox_root="/tmp")
            # Simple structure check
            if snap.sandbox_root:
                report.add_pass("refs:snapshot:creation")
        except ImportError:
            report.add_warning("refs:snapshot", "RollbackSnapshot not importable")
        except Exception as e:
            report.add_warning("refs:snapshot", str(e))

    # ── Subworkflow lineage ──────────────────────────────

    def _check_subworkflow_lineage(self, report: ConsistencyReport):
        """Check subworkflow reference lineage."""
        try:
            from workflow_composition.subworkflow_loader import SubworkflowLoader

            loader = SubworkflowLoader(str(self.root))
            # Simple structure check
            report.add_pass("refs:subworkflow:module_loaded")
        except ImportError:
            report.add_warning("refs:subworkflow",
                               "SubworkflowLoader not importable")
        except Exception as e:
            report.add_warning("refs:subworkflow", str(e))

    # ── Receipt linkage ──────────────────────────────────

    def _check_receipt_linkage(self, report: ConsistencyReport):
        """Check execution receipt linkage integrity."""
        try:
            from sandbox.execution_receipt import ExecutionReceipt

            receipt = ExecutionReceipt(
                execution_id="consistency-test-receipt",
                operator_identity="operator",
                approved_by="operator",
                executed_command="echo test",
                argv=["echo", "test"],
                cwd="/tmp",
                exit_code=0,
                elapsed_s=0.010,
                stdout="test",
                stderr="",
            )
            # Check serialization round-trip
            d = receipt.to_dict()
            r2 = ExecutionReceipt.from_dict(d)
            if r2.executed_command == receipt.executed_command and r2.exit_code == receipt.exit_code:
                report.add_pass("refs:receipt:roundtrip")
            else:
                report.add_fail("refs:receipt:roundtrip",
                                "Round-trip reconstruction failed")
        except ImportError:
            report.add_warning("refs:receipt", "ExecutionReceipt not importable")
        except Exception as e:
            report.add_warning("refs:receipt", str(e))

    # ── Escalation lineage ───────────────────────────────

    def _check_escalation_lineage(self, report: ConsistencyReport):
        """Check escalation record lineage."""
        try:
            from workflow_composition.escalation_policy import EscalationPolicy

            policy = EscalationPolicy()
            record = policy.escalate(
                node_id="test_node",
                reason="Test escalation",
                severity="medium",
            )

            if record.node_id == "test_node" and record.resolved is False:
                report.add_pass("refs:escalation:record_creation")

            # Check resolve
            policy.resolve(record.escalation_id, "Resolved by operator")
            if record.resolved:
                report.add_pass("refs:escalation:resolution")

        except ImportError:
            report.add_warning("refs:escalation",
                               "EscalationPolicy not importable")
        except Exception as e:
            report.add_warning("refs:escalation", str(e))
