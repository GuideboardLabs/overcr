"""
OverCR Runtime — Workflow Runner (v0.8.0)

Orchestrates the execution of a WorkflowGraph.

The runner executes nodes in topological order, enforces all policy checks,
routes packets through OverCR (never directly between subagents), validates
every output, handles retries, and maintains an append-only audit trace.

Design:
  - Every node execution goes through WorkflowPolicy
  - Every edge handoff goes through WorkflowPolicy
  - Validation failure stops the workflow
  - Policy violation stops the workflow
  - Approval gate stops the workflow unless operator approval exists
  - Max retries stops the workflow
  - Audit trace records every node, edge, decision, failure, and approval boundary
  - Workflow is replayable from filesystem state
"""

import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from runtime.workflow_graph import WorkflowGraph, WorkflowNode, WorkflowEdge
from runtime.workflow_policy import WorkflowPolicy, PolicyDecision


# ──────────────────────────────────────────────
# Workflow execution states
# ──────────────────────────────────────────────

WORKFLOW_STATES = {
    "pending", "running", "paused", "completed", "failed", "stopped",
}

NODE_EXECUTION_STATES = {
    "pending", "running", "completed", "failed", "skipped", "waiting_approval",
}


# ──────────────────────────────────────────────
# Audit trace entry
# ──────────────────────────────────────────────

@dataclass
class WorkflowTraceEntry:
    """A single entry in the append-only workflow audit trace."""
    timestamp: str
    workflow_id: str
    graph_version: str
    entry_type: str  # node_start, node_complete, node_fail, edge_handoff,
                     # policy_check, approval_gate, retry, workflow_start,
                     # workflow_complete, workflow_fail
    node_id: Optional[str] = None
    edge_id: Optional[str] = None
    source_packet_id: Optional[str] = None
    target_packet_id: Optional[str] = None
    selected_subagent: Optional[str] = None
    selected_model: Optional[str] = None
    validation_result: Optional[dict] = None
    policy_result: Optional[dict] = None
    approval_required: bool = False
    execution_authority: Optional[str] = None
    fallback_used: bool = False
    elapsed_s: float = 0.0
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = {
            "timestamp": self.timestamp,
            "workflow_id": self.workflow_id,
            "graph_version": self.graph_version,
            "entry_type": self.entry_type,
        }
        if self.node_id is not None:
            d["node_id"] = self.node_id
        if self.edge_id is not None:
            d["edge_id"] = self.edge_id
        if self.source_packet_id is not None:
            d["source_packet_id"] = self.source_packet_id
        if self.target_packet_id is not None:
            d["target_packet_id"] = self.target_packet_id
        if self.selected_subagent is not None:
            d["selected_subagent"] = self.selected_subagent
        if self.selected_model is not None:
            d["selected_model"] = self.selected_model
        if self.validation_result is not None:
            d["validation_result"] = self.validation_result
        if self.policy_result is not None:
            d["policy_result"] = self.policy_result
        d["approval_required"] = self.approval_required
        if self.execution_authority is not None:
            d["execution_authority"] = self.execution_authority
        d["fallback_used"] = self.fallback_used
        d["elapsed_s"] = self.elapsed_s
        if self.details:
            d["details"] = self.details
        return d


# ──────────────────────────────────────────────
# Node execution result
# ──────────────────────────────────────────────

@dataclass
class NodeExecutionResult:
    """Result of executing a single workflow node."""
    node_id: str
    success: bool
    packet: Optional[dict] = None
    validation_result: Optional[dict] = None
    policy_result: Optional[dict] = None
    retry_count: int = 0
    elapsed_s: float = 0.0
    fallback_used: bool = False
    error: Optional[str] = None


# ──────────────────────────────────────────────
# Workflow Runner
# ──────────────────────────────────────────────

class WorkflowRunner:
    """
    Executes a WorkflowGraph with full governance.

    Execution flow:
      1. Build and validate the graph
      2. Run full workflow policy check
      3. Execute nodes in topological order
      4. For each node: check policy -> execute -> validate -> check edges
      5. For each edge: check policy -> transform packet -> handoff to target
      6. Record every step in the audit trace
      7. Stop on any failure, violation, or missing approval
    """

    def __init__(
        self,
        root: str,
        policy: Optional[WorkflowPolicy] = None,
        worker_fn=None,
        validator_fn=None,
        allow_deterministic_fallback: bool = True,
    ):
        """
        Args:
            root: OverCR root directory (for filesystem state)
            policy: WorkflowPolicy instance (or default)
            worker_fn: Callable(node, input_packet) -> dict for executing nodes.
                       If None, nodes produce simulated/deterministic output.
            validator_fn: Callable(packet) -> (valid, errors, warnings) for validation.
                       If None, uses tools/validate_packet.py.
            allow_deterministic_fallback: Whether deterministic fallback is allowed
        """
        self.root = Path(root)
        self.policy = policy or WorkflowPolicy(
            allow_deterministic_fallback=allow_deterministic_fallback
        )
        self.worker_fn = worker_fn
        self._validator_fn = validator_fn
        self._validator_module = None

        # Execution state
        self.workflow_state = "pending"
        self.node_states: dict[str, str] = {}
        self.node_results: dict[str, NodeExecutionResult] = {}
        self.node_packets: dict[str, dict] = {}  # node_id -> output packet
        self.node_retry_counts: dict[str, int] = {}
        self.operator_approvals: dict[str, dict] = {}  # edge_id or node_id -> approval
        self.trace: list[WorkflowTraceEntry] = []
        self._task_counter: int = 0

        # Audit trace persistence
        self.trace_dir = self.root / "runtime"
        self.trace_dir.mkdir(parents=True, exist_ok=True)

    @property
    def validator(self):
        """Lazy-load the packet validator."""
        if self._validator_fn:
            return self._validator_fn
        if self._validator_module is None:
            import importlib.util
            tools_dir = self.root / "tools"
            spec = importlib.util.spec_from_file_location(
                "validate_packet", tools_dir / "validate_packet.py"
            )
            self._validator_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self._validator_module)
        return self._validator_module.validate_packet

    # ── Trace writing ────────────────────────────────────

    def _add_trace(self, entry: WorkflowTraceEntry):
        """Add entry to in-memory trace and append to disk."""
        self.trace.append(entry)
        trace_path = self.trace_dir / f"workflow_trace_{entry.workflow_id}.jsonl"
        with open(trace_path, "a") as f:
            f.write(json.dumps(entry.to_dict()) + "\n")

    def _make_trace(
        self,
        entry_type: str,
        workflow_id: str,
        graph_version: str,
        **kwargs,
    ) -> WorkflowTraceEntry:
        return WorkflowTraceEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            workflow_id=workflow_id,
            graph_version=graph_version,
            entry_type=entry_type,
            **kwargs,
        )

    # ── Execution ──────────────────────────────────────

    def run(
        self,
        graph: WorkflowGraph,
        initial_input: Optional[dict] = None,
        operator_approvals: Optional[dict] = None,
    ) -> dict:
        """
        Execute a workflow graph.

        Args:
            graph: The validated WorkflowGraph to execute
            initial_input: Optional input data for root nodes
            operator_approvals: Optional dict of pre-granted approvals
                                {node_id or edge_id: {"decision": "approved", ...}}

        Returns:
            dict with:
              - success: bool
              - workflow_id: str
              - workflow_state: str
              - executed_nodes: list of node_ids executed
              - failed_nodes: list of node_ids that failed
              - trace: list of trace entries
              - error: str if workflow failed
              - final_workflow_state: str
        """
        # Apply any pre-granted approvals
        if operator_approvals:
            self.operator_approvals.update(operator_approvals)

        workflow_id = graph.workflow_id
        graph_version = graph.version

        # 1. Build and validate graph
        valid, build_errors = graph.build()
        if not valid:
            self.workflow_state = "failed"
            self._add_trace(self._make_trace(
                "workflow_fail", workflow_id, graph_version,
                details={"reason": "Graph build failed", "errors": build_errors},
            ))
            return {
                "success": False,
                "workflow_id": workflow_id,
                "workflow_state": "failed",
                "executed_nodes": [],
                "failed_nodes": [],
                "trace": [e.to_dict() for e in self.trace],
                "error": f"Graph build failed: {build_errors}",
                "final_workflow_state": "failed",
            }

        # 2. Full workflow policy check
        full_check = self.policy.check_full_workflow(graph, self.operator_approvals)
        self._add_trace(self._make_trace(
            "policy_check", workflow_id, graph_version,
            policy_result=full_check.to_dict(),
            details={"phase": "pre_execution"},
        ))
        if not full_check.allowed:
            self.workflow_state = "failed"
            self._add_trace(self._make_trace(
                "workflow_fail", workflow_id, graph_version,
                policy_result=full_check.to_dict(),
                details={"reason": "Pre-execution policy violation"},
            ))
            return {
                "success": False,
                "workflow_id": workflow_id,
                "workflow_state": "failed",
                "executed_nodes": [],
                "failed_nodes": [],
                "trace": [e.to_dict() for e in self.trace],
                "error": f"Policy violation: {full_check.reason}",
                "final_workflow_state": "failed",
            }

        # 3. Initialize node states
        for node_id in graph.nodes:
            self.node_states[node_id] = "pending"
            self.node_retry_counts[node_id] = 0
        self.workflow_state = "running"

        self._add_trace(self._make_trace(
            "workflow_start", workflow_id, graph_version,
            details={"name": graph.name, "nodes": list(graph.nodes.keys())},
        ))

        # 4. Execute in topological order
        executed_nodes = []
        failed_nodes = []

        try:
            topo_order = graph.topological_order()
        except ValueError as e:
            self.workflow_state = "failed"
            self._add_trace(self._make_trace(
                "workflow_fail", workflow_id, graph_version,
                details={"reason": f"Topological order failed: {e}"},
            ))
            return {
                "success": False,
                "workflow_id": workflow_id,
                "workflow_state": "failed",
                "executed_nodes": [],
                "failed_nodes": [],
                "trace": [e.to_dict() for e in self.trace],
                "error": str(e),
                "final_workflow_state": "failed",
            }

        current_input = initial_input or {}

        for node_id in topo_order:
            node = graph.nodes[node_id]
            self.node_states[node_id] = "running"

            # Gather input from predecessor edges
            node_input = dict(current_input)
            for edge in graph.edges_to(node_id):
                src_packet = self.node_packets.get(edge.source_node_id, {})
                if src_packet:
                    # Apply transformation rule if specified
                    transformed = self._apply_transformation(
                        edge.transformation_rule, src_packet
                    )
                    node_input.update(transformed)

            # 5. Node execution with policy check and retry
            result = self._execute_node(
                graph, node, node_input, workflow_id, graph_version
            )
            self.node_results[node_id] = result

            if result.success:
                self.node_states[node_id] = "completed"
                self.node_packets[node_id] = result.packet or {}
                executed_nodes.append(node_id)
            else:
                self.node_states[node_id] = "failed"
                failed_nodes.append(node_id)
                # Validation failure or policy violation stops the workflow
                self.workflow_state = "failed"
                self._add_trace(self._make_trace(
                    "workflow_fail", workflow_id, graph_version,
                    node_id=node_id,
                    selected_subagent=node.subagent,
                    details={"reason": result.error, "node_failed": True},
                ))
                break

            # 6. Edge handoffs for this node's outgoing edges
            for edge in graph.edges_from(node_id):
                edge_result = self._process_edge(
                    graph, edge, workflow_id, graph_version
                )
                if not edge_result.allowed:
                    self.workflow_state = "failed"
                    failed_nodes.append(edge.target_node_id)
                    self._add_trace(self._make_trace(
                        "workflow_fail", workflow_id, graph_version,
                        edge_id=edge.edge_id,
                        policy_result=edge_result.to_dict(),
                        details={"reason": f"Edge handoff failed: {edge_result.reason}"},
                    ))
                    break

            if self.workflow_state == "failed":
                break

        # 7. Finalize
        if self.workflow_state == "running":
            self.workflow_state = "completed"

        self._add_trace(self._make_trace(
            "workflow_complete" if self.workflow_state == "completed" else "workflow_fail",
            workflow_id, graph_version,
            details={
                "final_state": self.workflow_state,
                "executed": executed_nodes,
                "failed": failed_nodes,
            },
        ))

        return {
            "success": self.workflow_state == "completed",
            "workflow_id": workflow_id,
            "workflow_state": self.workflow_state,
            "executed_nodes": executed_nodes,
            "failed_nodes": failed_nodes,
            "trace": [e.to_dict() for e in self.trace],
            "error": None if self.workflow_state == "completed" else "Workflow failed",
            "final_workflow_state": self.workflow_state,
        }

    # ── Node execution with retry ────────────────────────

    def _execute_node(
        self,
        graph: WorkflowGraph,
        node: WorkflowNode,
        input_data: dict,
        workflow_id: str,
        graph_version: str,
    ) -> NodeExecutionResult:
        """Execute a single node with policy checks, validation, and retry."""
        start_time = time.time()

        # Policy check
        policy_check = self.policy.check_node_execution(graph, node)
        self._add_trace(self._make_trace(
            "policy_check", workflow_id, graph_version,
            node_id=node.node_id,
            selected_subagent=node.subagent,
            policy_result=policy_check.to_dict(),
            approval_required=policy_check.details.get("approval_required", False),
        ))
        if not policy_check.allowed:
            elapsed = time.time() - start_time
            return NodeExecutionResult(
                node_id=node.node_id,
                success=False,
                policy_result=policy_check.to_dict(),
                elapsed_s=elapsed,
                error=f"Policy violation: {policy_check.reason}",
            )

        # Approval check
        approval_check = self.policy.check_approval_required(
            node, operator_approval=self.operator_approvals.get(node.node_id)
        )
        self._add_trace(self._make_trace(
            "approval_gate", workflow_id, graph_version,
            node_id=node.node_id,
            approval_required=not approval_check.allowed,
            policy_result=approval_check.to_dict(),
        ))
        if not approval_check.allowed:
            elapsed = time.time() - start_time
            return NodeExecutionResult(
                node_id=node.node_id,
                success=False,
                policy_result=approval_check.to_dict(),
                elapsed_s=elapsed,
                error=f"Approval required: {approval_check.reason}",
            )

        # Execute with retry loop
        retry_count = self.node_retry_counts.get(node.node_id, 0)
        while True:
            # Log node start
            self._add_trace(self._make_trace(
                "node_start", workflow_id, graph_version,
                node_id=node.node_id,
                selected_subagent=node.subagent,
                approval_required=(node.approval_policy == "always"),
                execution_authority="overcr_routed",
                details={"retry_count": retry_count},
            ))

            # Execute the node
            packet = None
            fallback_used = False
            error = None

            if self.worker_fn:
                try:
                    packet = self.worker_fn(node, input_data)
                except Exception as e:
                    error = str(e)
            else:
                # Deterministic simulated output
                packet = self._deterministic_output(node, input_data)

            # If worker failed and deterministic fallback allowed
            if packet is None and error:
                fallback_policy = self.policy.check_deterministic_fallback(
                    node, inference_failed=True
                )
                if fallback_policy.allowed:
                    packet = self._deterministic_output(node, input_data)
                    fallback_used = True
                    self._add_trace(self._make_trace(
                        "retry", workflow_id, graph_version,
                        node_id=node.node_id,
                        fallback_used=True,
                        details={"reason": "Worker failed, fallback to deterministic"},
                    ))

            # Validate the output packet
            if packet:
                valid, errors, warnings = self.validator(packet)
                validation_result = {
                    "valid": valid, "errors": errors, "warnings": warnings,
                }
                self._add_trace(self._make_trace(
                    "policy_check", workflow_id, graph_version,
                    node_id=node.node_id,
                    validation_result=validation_result,
                    details={"phase": "post_execution_validation"},
                ))

                if not valid:
                    # Validation failure — check if retry allowed
                    retry_check = self.policy.check_retry_allowed(
                        node, retry_count, last_error=str(errors)
                    )
                    if retry_check.allowed:
                        retry_count += 1
                        self.node_retry_counts[node.node_id] = retry_count
                        self._add_trace(self._make_trace(
                            "retry", workflow_id, graph_version,
                            node_id=node.node_id,
                            policy_result=retry_check.to_dict(),
                            details={"retry_count": retry_count, "max_retries": node.max_retries},
                        ))
                        continue  # Retry
                    else:
                        # Retries exhausted — try deterministic fallback
                        fallback_policy = self.policy.check_deterministic_fallback(
                            node, inference_failed=True
                        )
                        if fallback_policy.allowed:
                            packet = self._deterministic_output(node, input_data)
                            fallback_used = True
                            self._add_trace(self._make_trace(
                                "retry", workflow_id, graph_version,
                                node_id=node.node_id,
                                fallback_used=True,
                                details={"reason": "Validation failed after retries, fallback to deterministic"},
                            ))
                            # Re-validate the deterministic fallback packet
                            if packet:
                                valid_fb, errors_fb, warnings_fb = self.validator(packet)
                                if valid_fb:
                                    validation_result = {
                                        "valid": True, "errors": [], "warnings": warnings_fb,
                                    }
                                    self._add_trace(self._make_trace(
                                        "node_complete", workflow_id, graph_version,
                                        node_id=node.node_id,
                                        selected_subagent=node.subagent,
                                        source_packet_id=packet.get("packet_type", ""),
                                        approval_required=(node.approval_policy == "always"),
                                        fallback_used=True,
                                        elapsed_s=time.time() - start_time,
                                    ))
                                    elapsed = time.time() - start_time
                                    return NodeExecutionResult(
                                        node_id=node.node_id,
                                        success=True,
                                        packet=packet,
                                        validation_result=validation_result,
                                        retry_count=retry_count,
                                        elapsed_s=elapsed,
                                        fallback_used=True,
                                    )

                        elapsed = time.time() - start_time
                        return NodeExecutionResult(
                            node_id=node.node_id,
                            success=False,
                            validation_result=validation_result,
                            policy_result=retry_check.to_dict(),
                            retry_count=retry_count,
                            elapsed_s=elapsed,
                            error=f"Validation failed after {retry_count} retries: {errors}",
                        )

                # Validated — log completion
                self._add_trace(self._make_trace(
                    "node_complete", workflow_id, graph_version,
                    node_id=node.node_id,
                    selected_subagent=node.subagent,
                    source_packet_id=packet.get("packet_type", ""),
                    approval_required=(node.approval_policy == "always"),
                    fallback_used=fallback_used,
                    elapsed_s=time.time() - start_time,
                ))

                elapsed = time.time() - start_time
                return NodeExecutionResult(
                    node_id=node.node_id,
                    success=True,
                    packet=packet,
                    validation_result=validation_result,
                    retry_count=retry_count,
                    elapsed_s=elapsed,
                    fallback_used=fallback_used,
                )
            else:
                # No packet produced — worker error
                retry_check = self.policy.check_retry_allowed(
                    node, retry_count, last_error=error
                )
                if retry_check.allowed:
                    retry_count += 1
                    self.node_retry_counts[node.node_id] = retry_count
                    self._add_trace(self._make_trace(
                        "retry", workflow_id, graph_version,
                        node_id=node.node_id,
                        details={"retry_count": retry_count, "error": error},
                    ))
                    continue  # Retry
                else:
                    elapsed = time.time() - start_time
                    return NodeExecutionResult(
                        node_id=node.node_id,
                        success=False,
                        retry_count=retry_count,
                        elapsed_s=elapsed,
                        error=f"Node execution failed after {retry_count} retries: {error}",
                    )

    # ── Edge processing ──────────────────────────────────

    def _process_edge(
        self,
        graph: WorkflowGraph,
        edge: WorkflowEdge,
        workflow_id: str,
        graph_version: str,
    ) -> PolicyDecision:
        """Process an edge handoff between nodes."""
        source_packet = self.node_packets.get(edge.source_node_id, {})
        src_packet_id = source_packet.get("packet_type", "unknown")

        # Policy check on edge
        edge_check = self.policy.check_edge_handoff(graph, edge, source_packet)
        self._add_trace(self._make_trace(
            "policy_check", workflow_id, graph_version,
            edge_id=edge.edge_id,
            source_packet_id=src_packet_id,
            target_packet_id=edge.target_node_id,
            policy_result=edge_check.to_dict(),
            approval_required=(edge.approval_gate == "always"),
            details={"phase": "edge_handoff"},
        ))
        if not edge_check.allowed:
            return edge_check

        # Edge approval check
        if edge.approval_gate == "always":
            approval = self.operator_approvals.get(edge.edge_id)
            if not approval or approval.get("decision") != "approved":
                return PolicyDecision(
                    allowed=False,
                    reason=f"Edge '{edge.edge_id}' requires approval but none granted",
                    policy_name="edge_approval_gate",
                )

        # Log successful handoff
        self._add_trace(self._make_trace(
            "edge_handoff", workflow_id, graph_version,
            edge_id=edge.edge_id,
            source_packet_id=src_packet_id,
            target_packet_id=edge.target_node_id,
            approval_required=(edge.approval_gate == "always"),
            execution_authority="overcr_routed",
            details={
                "transformation_rule": edge.transformation_rule,
                "accepted_types": edge.accepted_packet_types,
            },
        ))

        return PolicyDecision(
            allowed=True,
            reason="Edge handoff processed through OverCR",
            policy_name="edge_handoff",
        )

    # ── Transformation rules ────────────────────────────

    def _apply_transformation(
        self,
        rule: Optional[str],
        packet: dict,
    ) -> dict:
        """Apply a transformation rule to extract relevant context from a packet."""
        if not rule or not packet:
            return {}

        rule_handlers = {
            "extract_public_signal_context": self._extract_public_signal_context,
            "extract_signal_for_planning": self._extract_signal_for_planning,
            "extract_patch_for_simulation": self._extract_patch_for_simulation,
        }

        handler = rule_handlers.get(rule)
        if handler:
            return handler(packet)

        # Unknown rule — pass through
        return packet

    @staticmethod
    def _extract_public_signal_context(packet: dict) -> dict:
        """Extract public-signal context from a KnowER packet for CryER."""
        context = {
            "source_packet_type": packet.get("packet_type", ""),
            "source_subagent": packet.get("source", ""),
            "summary": packet.get("summary", ""),
        }
        # Extract claim data if present
        payload = packet.get("payload", packet.get("claim_data", {}))
        if payload:
            context["payload_summary"] = str(payload)[:500]
        return context

    @staticmethod
    def _extract_signal_for_planning(packet: dict) -> dict:
        """Extract signal data from a CryER packet for PypER planning."""
        context = {
            "source_packet_type": packet.get("packet_type", ""),
            "source_subagent": packet.get("source", ""),
            "summary": packet.get("summary", ""),
        }
        recon_data = packet.get("recon_data", packet.get("signal_data", {}))
        if recon_data:
            context["recon_data"] = recon_data
        return context

    @staticmethod
    def _extract_patch_for_simulation(packet: dict) -> dict:
        """Extract patch plan data from a CodER packet for PypER simulation."""
        context = {
            "source_packet_type": packet.get("packet_type", ""),
            "source_subagent": packet.get("source", ""),
            "summary": packet.get("summary", ""),
        }
        patch_data = packet.get("patch_data", packet.get("payload", {}))
        if patch_data:
            context["patch_data"] = patch_data
        return context

    # ── Deterministic output generation ──────────────────

    def _deterministic_output(
        self,
        node: WorkflowNode,
        input_data: dict,
    ) -> dict:
        """
        Generate a deterministic simulated output packet for a node.

        This produces a valid packet that will pass L1-L6 validation.
        """
        now = datetime.now(timezone.utc).isoformat()

        self._task_counter += 1
        task_id = f"task-{self._task_counter:04d}"

        # Base packet structure
        packet = {
            "packet_type": node.packet_type,
            "version": "1.0",
            "timestamp": now,
            "source": node.subagent,
            "target": "overcr",
            "task_id": task_id,
            "summary": f"Deterministic output from {node.subagent}/{node.node_id}",
        }

        # Subagent-specific deterministic payloads
        if node.subagent == "knower" and node.packet_type == "knower_claim_review":
            raw_claim = (
                input_data.get("raw_claims", ["test claim"])[0]
                if isinstance(input_data.get("raw_claims"), list)
                else "test claim"
            )
            packet.update({
                "claim_review_data": {
                    "topic": "deterministic review topic",
                    "claims": [
                        {
                            "text": raw_claim,
                            "classification": "fact",
                            "confidence": 3,
                            "source_quality": "primary",
                            "evidence": [],
                            "unknowns": [],
                        }
                    ],
                    "operator_brief": "Deterministic simulated claim review — no real analysis performed.",
                },
                "approval_required": False,
                "governance": {
                    "deterministic_mode": True,
                    "inference_used": False,
                },
            })

        elif node.subagent == "cryer" and node.packet_type == "cryer_recon":
            packet.update({
                "recon_data": {
                    "targets": [{
                        "entity": input_data.get("entity", "example-entity"),
                        "type": "business",
                        "signals": {
                            "reputation": {"yield_score": 70, "confidence": 80},
                            "engagement": {"level": "moderate"},
                        },
                        "raw_sources": [
                            "https://example.com/deterministic-source"
                        ],
                    }],
                },
                "audit_trail": {
                    "collection_timestamps": [now],
                    "methods_used": ["public_search"],
                },
                "approval_required": False,
                "governance": {
                    "deterministic_mode": True,
                    "inference_used": False,
                },
            })

        elif node.subagent == "cryer" and node.packet_type == "cryer_engagement_signal":
            packet.update({
                "engagement_signal_data": {
                    "entity": input_data.get("entity", "example-entity"),
                    "metrics": [
                        {
                            "type": "review_count",
                            "classification": "observed",
                            "value": "42",
                            "confidence": 85,
                            "source_quality": "primary",
                            "unknowns": [],
                        }
                    ],
                    "engagement_summary": "Deterministic simulated engagement signal — no real data collected.",
                    "recommended_routing": "overcr",
                },
                "approval_required": False,
                "governance": {
                    "deterministic_mode": True,
                    "inference_used": False,
                },
            })

        elif node.subagent == "pyper" and node.packet_type == "pyper_execution_plan":
            packet.update({
                "execution_plan_data": {
                    "plan_description": "Deterministic simulated execution plan",
                    "entity": "overcr",
                    "steps": [
                        {
                            "step_index": 1,
                            "description": "Review engagement signal data",
                            "safety_classification": "safe",
                        },
                    ],
                    "dependency_analysis": {"upstream": ["cryer"], "downstream": []},
                    "dry_run_summary": "Simulated dry run completed with no side effects.",
                    "rollback_plan": "No changes were made; no rollback needed.",
                    "sandbox_recommendation": "Run in sandboxed environment before production.",
                },
                "approval_required": True,
                "execution_authority": "none",
                "governance": {
                    "deterministic_mode": True,
                    "inference_used": False,
                },
            })

        elif node.subagent == "pyper" and node.packet_type == "pyper_execution_receipt":
            packet.update({
                "receipt_data": {
                    "execution_type": "simulated",
                    "step_receipts": [
                        {
                            "step_index": 1,
                            "actual_execution": False,
                        },
                    ],
                    "overall_result": "SIMULATED — no real execution occurred",
                    "side_effects": [],
                },
                "approval_required": True,
                "execution_authority": "none",
                "governance": {
                    "deterministic_mode": True,
                    "inference_used": False,
                },
            })

        elif node.subagent == "coder" and node.packet_type == "coder_patch_plan":
            packet.update({
                "patch_plan_data": {
                    "code_inspection_summary": "Deterministic simulated code inspection — no real code reviewed.",
                    "bug_diagnosis": {
                        "summary": "Simulated bug diagnosis for deterministic output.",
                        "root_cause": "N/A — deterministic mode, no real bug identified.",
                        "confidence": 0.0,
                    },
                    "patch_plan": {
                        "description": "Advisory patch — no filesystem mutation",
                        "files_to_modify": ["example.py"],
                        "estimated_complexity": "low",
                    },
                    "proposed_diff": "--- a/example.py\n+++ b/example.py\n# deterministic: no real changes",
                    "test_plan": {
                        "test_cases": [
                            "Verify deterministic output packet is valid",
                        ],
                    },
                    "rollback_plan": "No changes were made; no rollback needed.",
                    "risk_notes": {
                        "level": "low",
                        "factors": ["Deterministic mode — no real patches applied"],
                        "mitigations": ["All changes are simulated only"],
                    },
                },
                "approval_required": True,
                "governance": {
                    "deterministic_mode": True,
                    "inference_used": False,
                },
            })

        else:
            # Generic deterministic output
            packet.update({
                "payload": {
                    "deterministic": True,
                    "input_summary": str(input_data)[:200],
                },
                "approval_required": node.approval_policy == "always",
                "governance": {
                    "deterministic_mode": True,
                    "inference_used": False,
                },
            })

        return packet

    # ── Replay from filesystem ──────────────────────────

    @classmethod
    def replay_from_trace(cls, root: str, workflow_id: str) -> dict:
        """
        Replay a workflow from its audit trace on disk.

        Reads the append-only JSONL trace and reconstructs the
        execution state without re-executing any nodes.
        """
        trace_path = Path(root) / "runtime" / f"workflow_trace_{workflow_id}.jsonl"
        if not trace_path.exists():
            return {"success": False, "error": f"Trace not found: {trace_path}"}

        entries = []
        with open(trace_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

        if not entries:
            return {"success": False, "error": "Empty trace file"}

        # Reconstruct state from trace
        executed_nodes = []
        failed_nodes = []
        final_state = "unknown"
        workflow_id_found = ""

        for entry in entries:
            entry_type = entry.get("entry_type", "")
            if entry_type == "node_complete":
                nid = entry.get("node_id", "")
                if nid and nid not in executed_nodes:
                    executed_nodes.append(nid)
            elif entry_type == "workflow_complete":
                final_state = "completed"
                workflow_id_found = entry.get("workflow_id", workflow_id)
            elif entry_type == "workflow_fail":
                final_state = "failed"
                workflow_id_found = entry.get("workflow_id", workflow_id)
            elif entry_type == "node_start" and entry.get("node_id"):
                nid = entry["node_id"]
                # If started but not completed, it failed
                if nid not in executed_nodes and nid not in failed_nodes:
                    # Check if there's a matching node_complete
                    completed = any(
                        e.get("entry_type") == "node_complete"
                        and e.get("node_id") == nid
                        for e in entries
                    )
                    if not completed:
                        failed_nodes.append(nid)

        return {
            "success": final_state == "completed",
            "workflow_id": workflow_id_found or workflow_id,
            "final_state": final_state,
            "executed_nodes": executed_nodes,
            "failed_nodes": failed_nodes,
            "trace_entries": len(entries),
        }

    # ── Query helpers ───────────────────────────────────

    def get_trace_summary(self) -> dict:
        """Get a summary of the current trace."""
        return {
            "total_entries": len(self.trace),
            "workflow_state": self.workflow_state,
            "node_states": dict(self.node_states),
            "node_packets": {nid: p.get("packet_type", "") for nid, p in self.node_packets.items()},
            "operator_approvals": list(self.operator_approvals.keys()),
        }