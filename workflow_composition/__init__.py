"""
OverCR v2.8.0 — Workflow Composition & Conditional Routing

Governed conditional orchestration with composable subworkflows,
branching, retry policy, escalation, and operator-aware routing.

This release is about controlled workflow intelligence — not
autonomous agent swarms. Every decision is auditable, replayable,
and filesystem-backed.

Exports:
  - ConditionEvaluator: data-driven condition evaluation (no eval())
  - RoutingPolicy: explicit routing with recorded decisions
  - RetryPolicy: bounded retries with escalation trigger
  - EscalationPolicy: operator-review escalation
  - SubworkflowLoader: version-pinned, cycle-safe subworkflow loading
  - WorkflowStateMachine: validated state transitions
  - BranchTrace: append-only branch decision trace
"""

from workflow_composition.condition_evaluator import ConditionEvaluator, EvaluatedCondition
from workflow_composition.routing_policy import RoutingPolicy, RoutingDecision
from workflow_composition.retry_policy import RetryPolicy, RetryRecord
from workflow_composition.escalation_policy import EscalationPolicy, EscalationRecord
from workflow_composition.subworkflow_loader import SubworkflowLoader, SubworkflowRef, SubworkflowLoadError
from workflow_composition.workflow_state_machine import WorkflowStateMachine, StateTransition, InvalidTransitionError
from workflow_composition.branch_trace import BranchTrace, BranchEntry

__all__ = [
    "ConditionEvaluator", "EvaluatedCondition",
    "RoutingPolicy", "RoutingDecision",
    "RetryPolicy", "RetryRecord",
    "EscalationPolicy", "EscalationRecord",
    "SubworkflowLoader", "SubworkflowRef", "SubworkflowLoadError",
    "WorkflowStateMachine", "StateTransition", "InvalidTransitionError",
    "BranchTrace", "BranchEntry",
]

__version__ = "2.8.0"
