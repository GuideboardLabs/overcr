"""
OverCR Semantic Memory — Memory Conflict Resolver v2.1.0

Detects contradictions between semantic memory records and creates
review artifacts. Does NOT auto-resolve conflicts.

Governance constraints:
  - Conflict detection identifies contradictory records
  - Review artifacts are created for operator review only
  - No automatic resolution — operators decide
  - Rejected memories are never deleted
  - Contradiction refs link records bidirectionally

Detection methods (v2.1 — keyword-based, no embeddings):
  1. Same project_scope + overlapping tags + conflicting summaries
  2. Same canonical_state_ref paths pointing to different conclusions
  3. Explicit contradiction_refs between records

Each conflict detection run produces a conflict-<id>.json file in the
conflicts/ directory. The operator reviews and decides manually.
"""

import json
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from memory.memory_record import MemoryRecord
from memory.memory_manager import MemoryManager


CONFLICT_TYPES = {
    "factual_contradiction": "Two records assert mutually exclusive facts.",
    "temporal_contradiction": "Two records about the same topic at different times, with conflicting conclusions.",
    "scope_overlap": "Two records cover overlapping scopes with potentially conflicting implications.",
}


class ConflictReviewArtifact:
    """A conflict review artifact — created but never auto-resolved."""

    def __init__(self, data: dict):
        self._data = data

    @property
    def conflict_id(self) -> str:
        return self._data["conflict_id"]

    @property
    def detected_at(self) -> str:
        return self._data["detected_at"]

    @property
    def conflict_type(self) -> str:
        return self._data["conflict_type"]

    @property
    def records(self) -> list[dict]:
        return self._data["records"]

    @property
    def analysis(self) -> str:
        return self._data.get("analysis", "")

    @property
    def resolution(self) -> Optional[dict]:
        return self._data.get("resolution")

    def to_dict(self) -> dict:
        return json.loads(json.dumps(self._data))

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self._data, indent=indent, ensure_ascii=False)


class MemoryConflictResolver:
    """
    Detects contradictions in semantic memory records.

    Creates review artifacts ONLY — no automatic resolution.
    Rejected memories are retained (never silently disappear).
    """

    def __init__(self, manager: MemoryManager):
        """
        Args:
            manager: A MemoryManager instance for reading records and
                     writing conflict artifacts.
        """
        self.manager = manager
        self.conflicts_dir = manager.conflicts_dir

    def detect_conflicts(
        self,
        project_scope: Optional[str] = None,
    ) -> list[ConflictReviewArtifact]:
        """
        Scan active memory records for potential contradictions.

        Detection strategy (v2.1 — keyword/tag-based):
          1. Find records sharing project_scope + overlapping tags
          2. Check for conflicting summaries (negation words, opposing tags)
          3. Check for contradictory canonical_state_refs

        Args:
            project_scope: If provided, only scan records in this scope.
                           If None, scan all active records.

        Returns:
            List of ConflictReviewArtifact objects (written to disk).
        """
        # Get candidate records
        if project_scope:
            records = self.manager.search_memory(
                project_scope=project_scope, status="active",
            )
        else:
            records = self.manager.search_memory(status="active")

        conflicts = []

        # ── Strategy 1: Overlapping tags in same scope ──
        # Group by scope, then check pairs with shared tags
        scope_groups: dict[str, list[MemoryRecord]] = {}
        for r in records:
            scope_groups.setdefault(r.project_scope, []).append(r)

        for scope, group in scope_groups.items():
            for i in range(len(group)):
                for j in range(i + 1, len(group)):
                    a, b = group[i], group[j]
                    shared_tags = set(a.tags) & set(b.tags)
                    if not shared_tags:
                        continue

                    # Check for conflicting summaries
                    conflict_type = self._classify_conflict(a, b)
                    if conflict_type:
                        artifact = self._create_artifact(
                            conflict_type=conflict_type,
                            record_a=a,
                            record_b=b,
                            analysis=(
                                f"Records mem-{a.memory_id} and mem-{b.memory_id} "
                                f"share tags {shared_tags} in scope '{scope}'. "
                                f"Conflict classification: {conflict_type}."
                            ),
                        )
                        conflicts.append(artifact)

        # ── Strategy 2: Contradictory canonical_state_refs ──
        # Two active records pointing to the same canonical path with
        # different conclusions (different semantic summaries)
        path_to_records: dict[str, list[MemoryRecord]] = {}
        for r in records:
            for ref in r.canonical_state_refs:
                path = ref.get("path", "")
                if path:
                    path_to_records.setdefault(path, []).append(r)

        for path, path_records in path_to_records.items():
            if len(path_records) < 2:
                continue
            # Multiple records referencing the same canonical path
            # Check if summaries differ significantly
            summaries = {r.memory_id: r.semantic_summary for r in path_records}
            unique_summaries = set(summaries.values())
            if len(unique_summaries) > 1:
                # Create a conflict for each pair
                for i in range(len(path_records)):
                    for j in range(i + 1, len(path_records)):
                        a, b = path_records[i], path_records[j]
                        # Avoid duplicates with strategy 1
                        already_found = any(
                            c.records[0]["memory_id"] in (a.memory_id, b.memory_id)
                            and c.records[1]["memory_id"] in (a.memory_id, b.memory_id)
                            and c.conflict_type == "canonical_conflict"
                            for c in conflicts
                        )
                        if not already_found:
                            artifact = self._create_artifact(
                                conflict_type="factual_contradiction",
                                record_a=a,
                                record_b=b,
                                analysis=(
                                    f"Records {a.memory_id} and {b.memory_id} both "
                                    f"reference canonical path '{path}' but have "
                                    f"different semantic summaries."
                                ),
                            )
                            conflicts.append(artifact)

        # ── Link contradiction_refs on records ──
        for artifact in conflicts:
            recs = artifact.records
            mid_a = recs[0]["memory_id"]
            mid_b = recs[1]["memory_id"]
            try:
                record_a = self.manager.load_memory(mid_a)
                record_a.add_contradiction(
                    conflicting_id=mid_b,
                    conflict_type=artifact.conflict_type,
                    note=artifact.analysis,
                )
                self.manager._write_record(record_a)
            except (FileNotFoundError, ValueError):
                pass
            try:
                record_b = self.manager.load_memory(mid_b)
                record_b.add_contradiction(
                    conflicting_id=mid_a,
                    conflict_type=artifact.conflict_type,
                    note=artifact.analysis,
                )
                self.manager._write_record(record_b)
            except (FileNotFoundError, ValueError):
                pass

        return conflicts

    def load_conflict(self, conflict_id: str) -> Optional[ConflictReviewArtifact]:
        """
        Load a conflict review artifact from disk.

        Args:
            conflict_id: The conflict ID (format: conflict-XXXXXXXX).

        Returns:
            The ConflictReviewArtifact, or None if not found.
        """
        path = self.conflicts_dir / f"{conflict_id}.json"
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return ConflictReviewArtifact(data)

    def list_conflicts(self) -> list[ConflictReviewArtifact]:
        """List all conflict review artifacts."""
        artifacts = []
        for path in sorted(self.conflicts_dir.glob("conflict-*.json")):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                artifacts.append(ConflictReviewArtifact(data))
            except (json.JSONDecodeError, KeyError):
                continue
        return artifacts

    # ── Internal ──────────────────────────────────────────────

    @staticmethod
    def _classify_conflict(a: MemoryRecord, b: MemoryRecord) -> Optional[str]:
        """
        Heuristic classification of whether two records conflict.

        Returns a conflict_type string or None if no conflict detected.
        This is keyword-based (v2.1) — no embeddings.
        """
        # Negation detection — if one summary negates the other
        summary_a = a.semantic_summary.lower()
        summary_b = b.semantic_summary.lower()

        negation_words = {"not", "never", "no ", "don't", "doesn't", "isn't", "aren't", "cannot", "won't"}

        # Check if summaries are semantically opposed
        a_has_negation = any(w in summary_a for w in negation_words)
        b_has_negation = any(w in summary_b for w in negation_words)

        # If one has negation and the other doesn't, potential factual contradiction
        if a_has_negation != b_has_negation:
            # Check for shared significant words (beyond stop words)
            stop_words = {"the", "a", "an", "is", "are", "was", "were", "be", "been",
                          "being", "have", "has", "had", "do", "does", "did", "will",
                          "would", "shall", "should", "may", "might", "must", "can",
                          "could", "to", "of", "in", "for", "on", "with", "at", "by",
                          "from", "as", "into", "through", "during", "before", "after",
                          "above", "below", "between", "out", "off", "over", "under"}
            words_a = set(summary_a.split()) - stop_words
            words_b = set(summary_b.split()) - stop_words
            shared = words_a & words_b
            # Needs meaningful overlap (more than just a couple words)
            if len(shared) >= 3:
                return "factual_contradiction"

        # Temporal conflict — different timestamps, same scope/tags
        if a.created_at != b.created_at:
            # If created at different times with same scope, flag temporal
            if a.project_scope == b.project_scope:
                shared_tags = set(a.tags) & set(b.tags)
                if len(shared_tags) >= 2:
                    return "temporal_contradiction"

        # Scope overlap — same scope, very similar tags, possibly conflicting
        # (This is conservative — only flags obvious overlaps)
        if a.project_scope == b.project_scope:
            shared_tags = set(a.tags) & set(b.tags)
            if len(shared_tags) >= len(set(a.tags)) * 0.5:
                # More than half of tags overlap — potential scope conflict
                return "scope_overlap"

        return None

    def _create_artifact(
        self,
        conflict_type: str,
        record_a: MemoryRecord,
        record_b: MemoryRecord,
        analysis: str,
    ) -> ConflictReviewArtifact:
        """Create and persist a conflict review artifact."""
        conflict_id = f"conflict-{secrets.token_hex(4)}"
        now = datetime.now(timezone.utc).isoformat()

        data = {
            "conflict_id": conflict_id,
            "detected_at": now,
            "conflict_type": conflict_type,
            "records": [
                {
                    "memory_id": record_a.memory_id,
                    "source": record_a.source,
                    "project_scope": record_a.project_scope,
                    "tags": record_a.tags,
                    "semantic_summary": record_a.semantic_summary,
                    "confidence": record_a.confidence,
                    "status": record_a.status,
                },
                {
                    "memory_id": record_b.memory_id,
                    "source": record_b.source,
                    "project_scope": record_b.project_scope,
                    "tags": record_b.tags,
                    "semantic_summary": record_b.semantic_summary,
                    "confidence": record_b.confidence,
                    "status": record_b.status,
                },
            ],
            "analysis": analysis,
            "resolution": None,  # To be filled by operator
        }

        # Persist to disk
        path = self.conflicts_dir / f"{conflict_id}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        return ConflictReviewArtifact(data)