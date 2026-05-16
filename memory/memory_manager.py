"""
OverCR Semantic Memory — Memory Manager v2.1.0

Filesystem-backed CRUD operations for semantic memory records.

Storage layout:
  <root>/memory/
    index.jsonl          — append-only index of all memory records
    records/
      mem-<id>.json      — one file per record (canonical)
    conflicts/
      conflict-<id>.json — contradiction review artifacts
    schema/
      memory_record.schema.json

Key invariants:
  - Filesystem is canonical truth (same as TaskStore pattern)
  - Every mutation writes to disk immediately
  - Rejected memories are NEVER deleted
  - Stale memories remain recoverable
  - No in-memory cache — all reads come from disk
  - Audit traceability: every create/update appends to index
"""

import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from memory.memory_record import MemoryRecord, VALID_STATUSES, MEMORY_ID_PATTERN


class MemoryManager:
    """
    Filesystem-backed manager for semantic memory records.

    All operations write to disk immediately. No task state lives only in memory.
    """

    def __init__(self, root: str):
        """
        Args:
            root: Path to the OverCR core directory (contains memory/).
        """
        self.root = Path(root)
        self.memory_dir = self.root / "memory"
        self.records_dir = self.memory_dir / "records"
        self.conflicts_dir = self.memory_dir / "conflicts"
        self.index_path = self.memory_dir / "index.jsonl"
        self.schema_dir = self.memory_dir / "schema"
        self._ensure_dirs()

    def _ensure_dirs(self):
        """Create directory structure if it doesn't exist."""
        self.records_dir.mkdir(parents=True, exist_ok=True)
        self.conflicts_dir.mkdir(parents=True, exist_ok=True)
        self.schema_dir.mkdir(parents=True, exist_ok=True)

    # ── Create ────────────────────────────────────────────────

    def create_memory(
        self,
        source: str,
        provenance_type: str,
        provenance_rule: str,
        confidence: float,
        tags: list[str],
        project_scope: str,
        semantic_summary: str,
        operator_id: Optional[str] = None,
        task_id: Optional[str] = None,
        artifact_path: Optional[str] = None,
        supporting_artifacts: Optional[list[dict]] = None,
        canonical_state_refs: Optional[list[dict]] = None,
    ) -> MemoryRecord:
        """
        Create a new semantic memory record and persist it to disk.

        Returns:
            The created MemoryRecord (already written to disk).
        """
        record = MemoryRecord.create(
            source=source,
            provenance_type=provenance_type,
            provenance_rule=provenance_rule,
            confidence=confidence,
            tags=tags,
            project_scope=project_scope,
            semantic_summary=semantic_summary,
            operator_id=operator_id,
            task_id=task_id,
            artifact_path=artifact_path,
            supporting_artifacts=supporting_artifacts,
            canonical_state_refs=canonical_state_refs,
        )

        self._write_record(record)
        self._append_index(record, action="created")
        return record

    # ── Load ──────────────────────────────────────────────────

    def load_memory(self, memory_id: str) -> MemoryRecord:
        """
        Load a memory record from disk by memory_id.

        Args:
            memory_id: The memory ID (format: mem-XXXXXXXX).

        Returns:
            The MemoryRecord.

        Raises:
            FileNotFoundError: If the record doesn't exist.
        """
        self._validate_memory_id(memory_id)
        path = self.records_dir / f"{memory_id}.json"
        if not path.exists():
            raise FileNotFoundError(f"Memory record not found: {path}")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return MemoryRecord.from_dict(data)

    # ── Search ────────────────────────────────────────────────

    def search_memory(
        self,
        tags: Optional[list[str]] = None,
        project_scope: Optional[str] = None,
        status: Optional[str] = None,
        source: Optional[str] = None,
        text_query: Optional[str] = None,
    ) -> list[MemoryRecord]:
        """
        Search memory records by structured criteria.

        All criteria are AND-combined. Each is optional; omit all to list everything.

        Args:
            tags: Match records that have ALL of these tags.
            project_scope: Exact match on project_scope.
            status: Exact match on status (active, stale, rejected, superseded).
            source: Case-insensitive substring match on source.
            text_query: Case-insensitive substring match on semantic_summary.

        Returns:
            List of matching MemoryRecord objects, sorted by updated_at descending.
        """
        results = []
        for path in sorted(self.records_dir.glob("mem-*.json")):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                record = MemoryRecord.from_dict(data)
            except (json.JSONDecodeError, ValueError):
                # Skip corrupt records — don't crash search
                continue

            # Filter criteria (all AND)
            if tags and not all(t in record.tags for t in tags):
                continue
            if project_scope and record.project_scope != project_scope:
                continue
            if status and record.status != status:
                continue
            if source and source.lower() not in record.source.lower():
                continue
            if text_query and text_query.lower() not in record.semantic_summary.lower():
                continue

            results.append(record)

        # Sort by updated_at descending (most recent first)
        results.sort(key=lambda r: r.updated_at, reverse=True)
        return results

    # ── Update Status ─────────────────────────────────────────

    def update_memory_status(
        self,
        memory_id: str,
        new_status: str,
        reason: Optional[str] = None,
    ) -> MemoryRecord:
        """
        Transition a memory record to a new status.

        Persists the updated record to disk immediately.

        Args:
            memory_id: The record to update.
            new_status: Target status from VALID_STATUSES.
            reason: Optional reason (required context for stale).

        Returns:
            The updated MemoryRecord.

        Raises:
            FileNotFoundError: If the record doesn't exist.
            ValueError: If the transition is invalid.
        """
        self._validate_memory_id(memory_id)
        record = self.load_memory(memory_id)
        old_status = record.status
        record.update_status(new_status, reason=reason)
        self._write_record(record)
        self._append_index(record, action=f"status_change:{old_status}->{new_status}")
        return record

    # ── List Project Memory ───────────────────────────────────

    def list_project_memory(
        self,
        project_scope: str,
        status: Optional[str] = None,
    ) -> list[MemoryRecord]:
        """
        List all memory records for a given project scope.

        Args:
            project_scope: The project to filter by.
            status: Optional status filter.

        Returns:
            List of matching MemoryRecords.
        """
        return self.search_memory(project_scope=project_scope, status=status)

    # ── Supersede ─────────────────────────────────────────────

    def supersede_memory(
        self,
        old_id: str,
        new_id: str,
        reason: Optional[str] = None,
    ) -> MemoryRecord:
        """
        Mark an old memory as superseded by a new one.

        Both records must exist. The old record transitions to 'superseded' status.

        Args:
            old_id: The memory being superseded.
            new_id: The memory replacing it.
            reason: Optional explanation.

        Returns:
            The updated (old) MemoryRecord.
        """
        self._validate_memory_id(old_id)
        self._validate_memory_id(new_id)

        # Verify the new record exists
        new_record = self.load_memory(new_id)

        old_record = self.load_memory(old_id)
        old_record.supersede(new_id, reason=reason)
        self._write_record(old_record)
        self._append_index(old_record, action=f"superseded_by:{new_id}")
        return old_record

    # ── Internal ──────────────────────────────────────────────

    def _write_record(self, record: MemoryRecord):
        """Write a memory record to its canonical file on disk."""
        path = self.records_dir / f"{record.memory_id}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(record.to_dict(), f, indent=2, ensure_ascii=False)

    def _append_index(self, record: MemoryRecord, action: str):
        """Append an index entry to the append-only index log."""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "memory_id": record.memory_id,
            "action": action,
            "status": record.status,
            "project_scope": record.project_scope,
        }
        with open(self.index_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    @staticmethod
    def _validate_memory_id(memory_id: str):
        """Validate memory_id format."""
        if not MEMORY_ID_PATTERN.match(memory_id):
            raise ValueError(f"Invalid memory_id format: {memory_id}. Expected: mem-XXXXXXXX")