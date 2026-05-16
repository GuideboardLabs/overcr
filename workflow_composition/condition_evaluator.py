"""
OverCR v2.8.0 — Condition Evaluator

Deterministic evaluation of workflow conditions. No eval(), no
dynamic code execution. Every condition is a data-driven comparison
against workflow state, node outcomes, or packet metadata.

Supported condition types:
  - confidence_threshold
  - trust_tier
  - validation_result
  - approval_decision
  - contradiction_present
  - retry_exhausted
  - escalation_triggered
  - fallback_active
  - always / never
"""

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class EvaluatedCondition:
    """Result of evaluating a single condition."""
    condition_type: str
    passed: bool
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "condition_type": self.condition_type,
            "passed": self.passed,
            "details": self.details,
        }


class ConditionEvaluator:
    """
    Evaluates workflow conditions deterministically.

    All conditions are data-driven comparisons. No Python eval(),
    no dynamic expression parsing, no code injection surface.
    """

    @staticmethod
    def evaluate(condition: dict, context: dict) -> EvaluatedCondition:
        """
        Evaluate a single condition against workflow context.

        Args:
            condition: Dict with type, field, operator, value.
            context: Workflow state snapshot (node outcomes, trust tiers, etc.)

        Returns:
            EvaluatedCondition with passed=True/False.
        """
        ctype = condition.get("type", "always")
        op = condition.get("operator", "==")
        field = condition.get("field", "")
        expected = condition.get("value")
        negate = condition.get("negate", False)

        # Resolve actual value from context
        actual = ConditionEvaluator._resolve(field, context)

        # Evaluate based on type
        result = ConditionEvaluator._eval_type(ctype, op, actual, expected, context)

        if negate:
            result = not result

        return EvaluatedCondition(
            condition_type=ctype,
            passed=result,
            details={"field": field, "operator": op,
                     "actual": str(actual)[:100], "expected": str(expected)[:100],
                     "negated": negate},
        )

    @staticmethod
    def _resolve(field: str, context: dict) -> Any:
        """Resolve a dot-separated field path from context dict."""
        if not field:
            return None
        parts = field.split(".")
        current = context
        for p in parts:
            if isinstance(current, dict):
                current = current.get(p)
            else:
                return None
        return current

    @staticmethod
    def _eval_type(ctype: str, op: str, actual: Any, expected: Any,
                   context: dict) -> bool:
        """Evaluate based on condition type and operator."""

        if ctype == "always":
            return True
        if ctype == "never":
            return False

        # Confidence threshold
        if ctype == "confidence_threshold":
            if actual is None:
                return False
            return ConditionEvaluator._compare(op, actual, expected)

        # Trust tier comparison
        if ctype == "trust_tier":
            trust_ranks = {"verified": 4, "reputable": 3,
                           "unknown": 2, "suspicious": 1, "rejected": 0}
            actual_rank = trust_ranks.get(str(actual).lower(), 0)
            expected_rank = trust_ranks.get(str(expected).lower(), 0)
            return ConditionEvaluator._compare(op, actual_rank, expected_rank)

        # Validation result
        if ctype == "validation_result":
            if op == "==":
                return actual == expected
            if op == "!=":
                return actual != expected
            return actual == expected

        # Approval decision
        if ctype == "approval_decision":
            return str(actual).lower() == str(expected).lower()

        # Contradiction presence
        if ctype == "contradiction_present":
            return bool(actual)

        # Retry exhausted
        if ctype == "retry_exhausted":
            return ConditionEvaluator._compare(op, actual, expected)

        # Escalation triggered
        if ctype == "escalation_triggered":
            return bool(actual)

        # Fallback active
        if ctype == "fallback_active":
            return bool(actual)

        # Generic — unknown types fail safely
        return False

    @staticmethod
    def _compare(op: str, actual: Any, expected: Any) -> bool:
        """Compare two values with a given operator."""
        try:
            if op == ">":
                return float(actual) > float(expected)
            if op == ">=":
                return float(actual) >= float(expected)
            if op == "<":
                return float(actual) < float(expected)
            if op == "<=":
                return float(actual) <= float(expected)
            if op == "==":
                return str(actual) == str(expected)
            if op == "!=":
                return str(actual) != str(expected)
            if op == "in":
                return actual in expected if isinstance(expected, (list, set, tuple)) else False
            if op == "not_in":
                return actual not in expected if isinstance(expected, (list, set, tuple)) else True
            if op == "exists":
                return actual is not None
            if op == "not_exists":
                return actual is None
        except (ValueError, TypeError):
            return False
        return False

    @staticmethod
    def evaluate_all(conditions: list[dict], context: dict) -> list[EvaluatedCondition]:
        """Evaluate a list of conditions. Returns all results."""
        return [ConditionEvaluator.evaluate(c, context) for c in conditions]

    @staticmethod
    def all_pass(conditions: list[dict], context: dict) -> bool:
        """Check if all conditions pass."""
        results = ConditionEvaluator.evaluate_all(conditions, context)
        return all(r.passed for r in results)

    @staticmethod
    def first_match(conditional_edges: list[dict], context: dict) -> Optional[dict]:
        """
        Find the first matching conditional edge (highest priority).

        Returns the matching edge dict, or None if no match.
        """
        sorted_edges = sorted(conditional_edges,
                              key=lambda e: e.get("priority", 0))
        for edge in sorted_edges:
            cond = edge.get("condition", {})
            if ConditionEvaluator.evaluate(cond, context).passed:
                return edge
        return None
