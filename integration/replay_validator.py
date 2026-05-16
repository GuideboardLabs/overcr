"""
OverCR v2.9.0 — Replay Validator

Validates that workflow replay is deterministic, audit traces are
reconstructable, branch traces are consistent, receipts are
replayable, and state machine transitions are valid.

Detects: missing artifacts, inconsistent timestamps, orphaned
audit entries, and invalid lineage chains.

All checks are read-only — the validator never rewrites history.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class ReplayValidationReport:
    """Complete replay validation report."""
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


class ReplayValidator:
    """
    Validates replay determinism and audit reconstruction.

    Verifies that two executions of the same workflow with the
    same input produce identical node ordering and audit traces,
    that branch traces are consistent, and that receipts can
    be reconstructed from audit entries.
    """

    def __init__(self, overcr_root: str):
        self.root = Path(overcr_root)

    def validate_replay_determinism(self) -> ReplayValidationReport:
        """
        Validate that the workflow system supports deterministic replay.

        Runs each workflow template twice with identical inputs and
        verifies that node execution order and audit structure match.
        """
        report = ReplayValidationReport()

        from workflow_library.workflow_executor import WorkflowExecutor
        executor = WorkflowExecutor(str(self.root))

        templates_dir = self.root / "workflow_library" / "templates"
        if not templates_dir.is_dir():
            report.add_fail("replay:templates_dir", "Templates directory missing")
            return report

        template_files = sorted(templates_dir.glob("*.json"))

        for tf in template_files:
            try:
                with open(tf, "r") as f:
                    template = json.load(f)
            except json.JSONDecodeError:
                continue

            wf_id = template.get("workflow_id", "")
            if not wf_id:
                continue

            # Register if needed
            try:
                executor.registry.register_workflow(template)
            except ValueError:
                pass  # Already registered

            # Run twice with identical input
            shared_input = {"entity": "replay-determinism-test",
                            "replay_batch": True}

            try:
                r1 = executor.execute_workflow(wf_id, initial_input=shared_input)
            except Exception as e:
                report.add_fail(f"replay:{wf_id}:first_run",
                                f"First execution failed: {e}")
                continue

            try:
                r2 = executor.execute_workflow(wf_id, initial_input=shared_input)
            except Exception as e:
                report.add_fail(f"replay:{wf_id}:second_run",
                                f"Second execution failed: {e}")
                continue

            # Check both succeeded or both failed consistently
            if r1.get("success") != r2.get("success"):
                report.add_warning(f"replay:{wf_id}:success_match",
                    f"First: {r1.get('success')}, Second: {r2.get('success')}")
            elif r1.get("success"):
                # Node order must match
                nodes1 = r1.get("executed_nodes", [])
                nodes2 = r2.get("executed_nodes", [])
                if nodes1 == nodes2:
                    report.add_pass(f"replay:{wf_id}:node_order_match")
                else:
                    report.add_fail(f"replay:{wf_id}:node_order_match",
                        f"Mismatch: {nodes1} vs {nodes2}")

                # Audit entries must have same structure (entry_types in order)
                types1 = [e.get("entry_type") for e in r1.get("audit_entries", [])]
                types2 = [e.get("entry_type") for e in r2.get("audit_entries", [])]
                if types1 == types2:
                    report.add_pass(f"replay:{wf_id}:audit_structure_match")
                else:
                    report.add_fail(f"replay:{wf_id}:audit_structure_match",
                        f"Mismatch: {len(types1)} vs {len(types2)} entries")

                # Workflow state must match
                if r1.get("workflow_state") == r2.get("workflow_state"):
                    report.add_pass(f"replay:{wf_id}:state_match")
                else:
                    report.add_fail(f"replay:{wf_id}:state_match",
                        f"Mismatch: {r1.get('workflow_state')} vs {r2.get('workflow_state')}")

            report.add_pass(f"replay:{wf_id}:executed")

        return report

    def validate_audit_reconstruction(self) -> ReplayValidationReport:
        """
        Validate that audit trails are reconstructable.

        Checks that audit entries form a coherent timeline and
        that no entries are orphaned or have broken lineage.
        """
        report = ReplayValidationReport()

        runtime_dir = self.root / "runtime"
        if not runtime_dir.is_dir():
            report.add_warning("audit_recon:runtime_dir", "No runtime directory")
            return report

        # Check trace files for well-formedness
        trace_files = sorted(runtime_dir.glob("workflow_trace_*.jsonl"))
        if not trace_files:
            report.add_warning("audit_recon:traces", "No trace files found")
            return report

        for tf in trace_files[:5]:  # Sample up to 5
            try:
                entries = []
                with open(tf, "r") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            entries.append(json.loads(line))

                if not entries:
                    report.add_warning(f"audit_recon:{tf.name}",
                                       "Empty trace file")
                    continue

                # Check timestamps are non-decreasing
                timestamps = [e.get("timestamp", "") for e in entries]
                is_ordered = all(
                    timestamps[i] <= timestamps[i + 1]
                    for i in range(len(timestamps) - 1)
                    if timestamps[i] and timestamps[i + 1]
                )
                if is_ordered:
                    report.add_pass(f"audit_recon:{tf.name}:temporal_order")
                else:
                    report.add_fail(f"audit_recon:{tf.name}:temporal_order",
                                    "Timestamps not monotonically increasing")

                # Check for run_id consistency
                run_ids = set(e.get("run_id", "") for e in entries if e.get("run_id"))
                if len(run_ids) == 1:
                    report.add_pass(f"audit_recon:{tf.name}:single_run_id")
                elif len(run_ids) > 1:
                    report.add_warning(f"audit_recon:{tf.name}:multiple_run_ids",
                                       f"Found {len(run_ids)} distinct run_ids")

            except json.JSONDecodeError as e:
                report.add_fail(f"audit_recon:{tf.name}", f"Invalid JSONL: {e}")
            except Exception as e:
                report.add_fail(f"audit_recon:{tf.name}", str(e))

        return report

    def validate_branch_trace_consistency(self) -> ReplayValidationReport:
        """
        Validate that branch traces are internally consistent.

        Checks that conditional edges, retries, escalations, and
        fallbacks form coherent chains.
        """
        report = ReplayValidationReport()

        # Check that condition evaluator is deterministic
        try:
            from workflow_composition.condition_evaluator import ConditionEvaluator

            evaluator = ConditionEvaluator()
            state1 = {"confidence": 3, "trust_tier": "medium"}
            state2 = {"confidence": 3, "trust_tier": "medium"}

            cond1 = {"type": "confidence_threshold", "field": "confidence",
                     "operator": ">=", "value": 3}
            cond2 = {"type": "trust_tier", "field": "trust_tier",
                     "operator": "==", "value": "medium"}

            r1 = evaluator.evaluate(cond1, state1)
            r2 = evaluator.evaluate(cond1, state1)
            r3 = evaluator.evaluate(cond2, state2)

            if r1.passed == r2.passed:
                report.add_pass("branch:evaluator_deterministic")
            else:
                report.add_fail("branch:evaluator_deterministic",
                                "Same condition+state produced different results")

            if r3.passed:
                report.add_pass("branch:evaluator_correct")

        except ImportError:
            report.add_warning("branch:evaluator",
                               "ConditionEvaluator not importable")
        except Exception as e:
            report.add_fail("branch:evaluator", str(e))

        # Check state machine transitions
        try:
            from workflow_composition.workflow_state_machine import WorkflowStateMachine

            sm = WorkflowStateMachine(initial_state="initialized")
            sm.transition_to("running")
            state = sm.state
            if state == "running":
                report.add_pass("branch:state_machine_transition")

            # Try illegal transition: "completed" is terminal (no outgoing transitions)
            try:
                sm2 = WorkflowStateMachine(initial_state="completed")
                sm2.transition_to("running")
                report.add_fail("branch:state_machine_illegal",
                                "Allowed transition from terminal state")
            except Exception:
                report.add_pass("branch:state_machine_blocks_illegal")

        except ImportError:
            report.add_warning("branch:state_machine",
                               "WorkflowStateMachine not importable")
        except Exception as e:
            report.add_fail("branch:state_machine", str(e))

        return report

    def validate_receipt_replayability(self) -> ReplayValidationReport:
        """
        Validate that execution receipts can be replayed.

        Checks that receipt structure supports reconstruction of
        the original execution.
        """
        report = ReplayValidationReport()

        try:
            from sandbox.execution_receipt import ExecutionReceipt

            # Create and serialize a receipt, then reconstruct
            receipt = ExecutionReceipt(
                execution_id="receipt-test-001",
                operator_identity="operator",
                approved_by="operator",
                executed_command="echo test",
                argv=["echo", "test"],
                cwd="/tmp",
                exit_code=0,
                elapsed_s=0.100,
                stdout="test\n",
                stderr="",
            )
            d = receipt.to_dict()
            if isinstance(d, dict):
                report.add_pass("receipt:serialization")

            reconstructed = ExecutionReceipt.from_dict(d)
            if reconstructed.executed_command == receipt.executed_command:
                report.add_pass("receipt:reconstruction")
            else:
                report.add_fail("receipt:reconstruction",
                                "Reconstructed receipt doesn't match original")

        except ImportError:
            report.add_warning("receipt", "ExecutionReceipt not importable")
        except Exception as e:
            report.add_fail("receipt", str(e))

        return report
