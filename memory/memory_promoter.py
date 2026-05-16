"""
OverCR Semantic Memory — Memory Promoter v2.1.0

Promotes candidate operational artifacts into semantic memory records.

Governance constraints:
  - Promotion requires EXPLICIT promotion rules — no autonomous promotion
    from arbitrary model output
  - Every promoted memory has provenance.type = 'promotion_rule'
  - provenance.rule identifies the exact rule that triggered promotion
  - Promotion CANNOT mutate operational state
  - Promotion CANNOT override task truth
  - Promoted memories are status='active' by default (advisory, not authoritative)

Promotion rules are defined in PROMOTION_RULES below. To add a new rule,
a developer must:
  1. Add the rule definition to PROMOTION_RULES
  2. Test that the rule produces valid MemoryRecord fields
  3. Document the rule in v2.1-memory-governance.md
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from memory.memory_record import MemoryRecord
from memory.memory_manager import MemoryManager


# ── Promotion Rule Definitions ───────────────────────────────
# Each rule defines:
#   - source: What kind of artifact this rule promotes from
#   - confidence: Fixed confidence for promoted memories (advisory)
#   - tags_from: How to derive tags from the artifact
#   - summary_from: How to derive semantic_summary from the artifact
#   - scope_from: How to derive project_scope from the artifact
#   - description: Human-readable rule description

PROMOTION_RULES = {
    "task_completion_insight": {
        "source": "subagent_output",
        "confidence": 0.7,
        "tags_from": "extract_from_task_tags",
        "summary_from": "task_summary_field",
        "scope_from": "task_domain",
        "description": (
            "Promotes key insights from completed OverCR task records. "
            "Only triggers when a task reaches 'completed' state with "
            "response_packet.summary present."
        ),
    },
    "operator_observation": {
        "source": "operator_direct",
        "confidence": 0.9,
        "tags_from": "operator_specified",
        "summary_from": "operator_text",
        "scope_from": "operator_specified",
        "description": (
            "Promotes a direct operator observation into semantic memory. "
            "Requires explicit operator_id and manually-provided summary/tags/scope."
        ),
    },
    "filesystem_artifact_promotion": {
        "source": "filesystem_artifact",
        "confidence": 0.6,
        "tags_from": "artifact_path_keywords",
        "summary_from": "artifact_first_line",
        "scope_from": "artifact_directory",
        "description": (
            "Promotes observations from filesystem artifacts (e.g., doctrine files, "
            "audit logs). Confidence is deliberately low (0.6) because filesystem "
            "state may be canonical — semantic memory must not compete."
        ),
    },
    "validation_lesson": {
        "source": "promotion_rule",
        "confidence": 0.8,
        "tags_from": "validation_error_keywords",
        "summary_from": "validation_lesson_text",
        "scope_from": "task_domain",
        "description": (
            "Promotes lessons learned from L1-L6 validation failures. "
            "Only triggers when a task enters 'validation_failed' state and "
            "the validation result contains specific error patterns."
        ),
    },
}

VALID_PROMOTION_RULES = set(PROMOTION_RULES.keys())


class PromotionError(Exception):
    """Raised when a promotion attempt violates governance constraints."""
    pass


class MemoryPromoter:
    """
    Governed promotion of operational artifacts into semantic memory.

    Every promotion is:
      - Rule-gated (must match a defined PROMOTION_RULE)
      - Provenance-tracked (provenance.rule names the exact rule)
      - Advisory (promoted memory does not override canonical state)
      - Auditable (the promotion rule, confidence, and source are recorded)
    """

    def __init__(self, manager: MemoryManager):
        """
        Args:
            manager: A MemoryManager instance for persisting promoted records.
        """
        self.manager = manager

    def promote(
        self,
        rule_name: str,
        summary: str,
        tags: list[str],
        project_scope: str,
        operator_id: Optional[str] = None,
        task_id: Optional[str] = None,
        artifact_path: Optional[str] = None,
        supporting_artifacts: Optional[list[dict]] = None,
        canonical_state_refs: Optional[list[dict]] = None,
        source_override: Optional[str] = None,
        confidence_override: Optional[float] = None,
    ) -> MemoryRecord:
        """
        Promote an artifact into semantic memory using a defined promotion rule.

        Args:
            rule_name: Must be a key in PROMOTION_RULES.
            summary: The semantic summary (human-readable).
            tags: Searchable tags for retrieval.
            project_scope: Project domain this memory belongs to.
            operator_id: Who requested this promotion (if applicable).
            task_id: OverCR task ID (if promoting from task output).
            artifact_path: Source artifact path (if promoting from file).
            supporting_artifacts: Optional supporting evidence.
            canonical_state_refs: Optional refs to canonical state files.
            source_override: Override the rule's default source field.
            confidence_override: Override the rule's default confidence.
                                  Must be 0.0–1.0 if provided.

        Returns:
            The created MemoryRecord.

        Raises:
            PromotionError: If the rule doesn't exist or violates constraints.
            ValueError: If field validation fails.
        """
        # ── Governance Gate 1: Rule must exist ──
        if rule_name not in VALID_PROMOTION_RULES:
            raise PromotionError(
                f"Unknown promotion rule: '{rule_name}'. "
                f"Valid rules: {sorted(VALID_PROMOTION_RULES)}. "
                f"No autonomous promotion from arbitrary model output."
            )

        rule = PROMOTION_RULES[rule_name]

        # ── Governance Gate 2: Confidence cannot be inflated ──
        confidence = confidence_override if confidence_override is not None else rule["confidence"]
        if confidence_override is not None:
            # Confidence override may only DECREASE, never increase above rule default
            if confidence_override > rule["confidence"]:
                raise PromotionError(
                    f"Confidence override {confidence_override} exceeds rule default "
                    f"{rule['confidence']} for rule '{rule_name}'. "
                    f"Promoted memory confidence must not exceed its rule's ceiling."
                )

        source = source_override or rule["source"]

        # ── Governance Gate 3: operator_direct requires operator_id ──
        if source == "operator_direct" and not operator_id:
            raise PromotionError(
                f"Rule '{rule_name}' produces operator_direct provenance but "
                f"no operator_id was provided. Every operator direct memory "
                f"must identify its author."
            )

        # ── Create the memory record ──
        record = self.manager.create_memory(
            source=source,
            provenance_type=rule["source"],
            provenance_rule=rule_name,
            confidence=confidence,
            tags=tags,
            project_scope=project_scope,
            semantic_summary=summary,
            operator_id=operator_id,
            task_id=task_id,
            artifact_path=artifact_path,
            supporting_artifacts=supporting_artifacts,
            canonical_state_refs=canonical_state_refs,
        )

        return record

    def list_rules(self) -> dict:
        """
        Return all defined promotion rules with their metadata.

        Returns:
            Dict of rule_name -> rule_definition.
        """
        return dict(PROMOTION_RULES)

    def get_rule(self, rule_name: str) -> Optional[dict]:
        """Get a single promotion rule by name, or None if not found."""
        return PROMOTION_RULES.get(rule_name)