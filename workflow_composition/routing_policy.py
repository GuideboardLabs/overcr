"""
OverCR v2.8.0 — Routing Policy

Explicit, auditable routing decisions for composite workflows.
Every decision records: evaluated conditions, matched rule,
operator context, workflow state snapshot, and timestamp.

Routing decisions are data-driven, not rule-engine-injected.
No dynamic code execution. Every path is traceable.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from workflow_composition.condition_evaluator import ConditionEvaluator


@dataclass
class RoutingDecision:
    """A single routing decision with full audit metadata."""
    source_node_id: str
    target_node_id: str
    decision_type: str  # 'static_edge', 'conditional_branch', 'fallback', 'escalation', 'rejection'
    matched_condition: Optional[dict] = None
    evaluated_conditions: list = field(default_factory=list)
    workflow_state_snapshot: dict = field(default_factory=dict)
    operator_context: str = ""
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict:
        return {
            "source_node_id": self.source_node_id,
            "target_node_id": self.target_node_id,
            "decision_type": self.decision_type,
            "matched_condition": self.matched_condition,
            "evaluated_conditions": [c.to_dict() for c in self.evaluated_conditions],
            "workflow_state_snapshot": self.workflow_state_snapshot,
            "operator_context": self.operator_context,
            "timestamp": self.timestamp,
        }


class RoutingPolicy:
    """
    Governed workflow routing engine.

    Determines the next node based on static edges, conditional
    edges, fallback routes, escalation triggers, and rejection paths.
    Every decision is recorded and auditable.
    """

    def __init__(self):
        self._decisions: list[RoutingDecision] = []

    # ── Routing methods ─────────────────────────────────

    def next_node(
        self,
        current_node_id: str,
        static_edges: list[dict],
        conditional_edges: list[dict],
        context_snapshot: dict,
        operator: str = "",
    ) -> RoutingDecision:
        """
        Determine the next node in the workflow.

        Priority order:
          1. Conditional edges (evaluated conditions, highest priority first)
          2. Static edges (first matching source)
          3. Fallback routes (if declared)
          4. None (workflow ends)

        Args:
            current_node_id: The node that just completed.
            static_edges: Standard edge definitions.
            conditional_edges: Conditional edge definitions with conditions.
            context_snapshot: Current workflow state for condition evaluation.
            operator: Operator identity for audit.
        """
        # 1. Check conditional edges from this source
        relevant_conditional = [
            e for e in conditional_edges
            if e.get("source") == current_node_id
        ]
        if relevant_conditional:
            matched = ConditionEvaluator.first_match(
                relevant_conditional, context_snapshot
            )
            if matched:
                evaluated = ConditionEvaluator.evaluate_all(
                    [matched.get("condition", {})], context_snapshot
                )
                decision = RoutingDecision(
                    source_node_id=current_node_id,
                    target_node_id=matched["target"],
                    decision_type="conditional_branch",
                    matched_condition=matched,
                    evaluated_conditions=evaluated,
                    workflow_state_snapshot=dict(context_snapshot),
                    operator_context=operator,
                )
                self._decisions.append(decision)
                return decision

        # 2. Check static edges from this source
        relevant_static = [
            e for e in static_edges
            if e.get("source") == current_node_id
        ]
        if relevant_static:
            edge = relevant_static[0]  # First matching static edge
            decision = RoutingDecision(
                source_node_id=current_node_id,
                target_node_id=edge["target"],
                decision_type="static_edge",
                workflow_state_snapshot=dict(context_snapshot),
                operator_context=operator,
            )
            self._decisions.append(decision)
            return decision

        # 3. No outgoing edges — workflow ends
        decision = RoutingDecision(
            source_node_id=current_node_id,
            target_node_id="",
            decision_type="rejection",
            workflow_state_snapshot=dict(context_snapshot),
            operator_context=operator,
        )
        self._decisions.append(decision)
        return decision

    def fallback_node(
        self,
        current_node_id: str,
        fallback_routes: dict,
        context_snapshot: dict,
        operator: str = "",
    ) -> RoutingDecision:
        """
        Determine the fallback node after a failure.

        Args:
            current_node_id: The failed node.
            fallback_routes: Dict mapping node_id -> fallback node_id.
            context_snapshot: Current workflow state.
            operator: Operator identity.
        """
        target = fallback_routes.get(current_node_id, "")
        decision = RoutingDecision(
            source_node_id=current_node_id,
            target_node_id=target,
            decision_type="fallback",
            workflow_state_snapshot=dict(context_snapshot),
            operator_context=operator,
        )
        self._decisions.append(decision)
        return decision

    def escalation_node(
        self,
        current_node_id: str,
        escalation_targets: list[dict],
        context_snapshot: dict,
        operator: str = "",
    ) -> RoutingDecision:
        """
        Determine the escalation target.

        Args:
            current_node_id: The node that triggered escalation.
            escalation_targets: List of escalation target dicts.
            context_snapshot: Current workflow state.
            operator: Operator identity.
        """
        target = "operator_review"  # Default escalation target
        if escalation_targets:
            target = escalation_targets[0].get("target", target)

        decision = RoutingDecision(
            source_node_id=current_node_id,
            target_node_id=target,
            decision_type="escalation",
            workflow_state_snapshot=dict(context_snapshot),
            operator_context=operator,
        )
        self._decisions.append(decision)
        return decision

    def rejection_node(
        self,
        current_node_id: str,
        reason: str,
        context_snapshot: dict,
        operator: str = "",
    ) -> RoutingDecision:
        """
        Record a rejection routing decision.

        Args:
            current_node_id: The rejected node.
            reason: Why it was rejected.
            context_snapshot: Current workflow state.
            operator: Operator identity.
        """
        decision = RoutingDecision(
            source_node_id=current_node_id,
            target_node_id="",
            decision_type="rejection",
            matched_condition={"reason": reason},
            workflow_state_snapshot=dict(context_snapshot),
            operator_context=operator,
        )
        self._decisions.append(decision)
        return decision

    # ── Audit ─────────────────────────────────────────

    def get_decisions(self) -> list[RoutingDecision]:
        """Get all routing decisions made so far."""
        return list(self._decisions)

    def export_trace(self) -> list[dict]:
        """Export all routing decisions as serializable dicts."""
        return [d.to_dict() for d in self._decisions]

    def reset(self):
        """Clear routing decisions for a new workflow."""
        self._decisions.clear()
