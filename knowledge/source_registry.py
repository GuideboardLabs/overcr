"""
OverCR v2.4.0 — Source Registry

Central registry for all knowledge sources. Every source must be
registered here before it can be cited, indexed, or referenced in
research packets.

Properties:
  - Filesystem-first: sources live as JSON records in knowledge/sources/
  - Sources are immutable once registered (content_hash verifies integrity)
  - Staleness is a status flag, never a deletion
  - Trust tiers escalate only with explicit operator action
  - Every source has a full provenance record
"""

import json
import hashlib
import uuid
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from knowledge.source_classifier import SourceClassifier, VALID_TRUST_TIERS, VALID_STATUSES


class SourceRecordExistsError(Exception):
    """Raised when attempting to register a duplicate source."""
    pass


class SourceNotFoundError(Exception):
    """Raised when a source cannot be found."""
    pass


class SourceRegistry:
    """
    Registers, lists, retrieves, and manages source records.

    All sources are filesystem-backed JSON records. No database.
    Sources can go stale but are never deleted.
    """

    def __init__(self, root: str):
        """
        Args:
            root: OverCR root directory (contains knowledge/)
        """
        self.root = Path(root)
        self.sources_dir = self.root / "knowledge" / "sources"
        self.documents_dir = self.root / "knowledge" / "documents"
        self.sources_dir.mkdir(parents=True, exist_ok=True)
        self.documents_dir.mkdir(parents=True, exist_ok=True)

        self._classifier = SourceClassifier()

        # In-memory cache (loaded from disk on demand)
        self._cache: dict[str, dict] = {}

    # ── Registration ────────────────────────────────────

    def register_source(
        self,
        origin: str,
        source_type: str = "",
        trust_level: str = "unknown",
        tags: Optional[list] = None,
        project_scope: str = "default",
        content: str = "",
        summary: str = "",
        canonical_refs: Optional[list] = None,
    ) -> dict:
        """
        Register a new knowledge source.

        Generates a unique source_id, computes content hash,
        classifies source type, and writes the record to disk.

        Args:
            origin: Where this source came from (URL, path, citation)
            source_type: Hint or explicit type. If empty, auto-classified.
            trust_level: Operator-assigned trust tier (never auto-escalated)
            tags: Searchable tags
            project_scope: Which project/workload this belongs to
            content: The source content (stored as a document file)
            summary: Human-readable summary
            canonical_refs: Stable references (DOI, permalink, etc.)

        Returns:
            The complete source record dict.

        Raises:
            SourceRecordExistsError: If content_hash matches an existing source.
        """
        now = datetime.now(timezone.utc).isoformat()

        # Compute content hash
        content_hash = hashlib.sha256(
            content.encode("utf-8") if content else uuid.uuid4().bytes
        ).hexdigest()

        # Check for duplicate by hash
        existing = self._find_by_hash(content_hash)
        if existing:
            raise SourceRecordExistsError(
                f"Source with content hash {content_hash[:12]}... already exists "
                f"as '{existing['source_id']}'"
            )

        # Generate source_id
        source_id = "src-" + uuid.uuid4().hex[:8]

        # Classify source type if not provided
        if not source_type or not self._classifier.is_valid_source_type(source_type):
            source_type = self._classifier.classify_source_type(
                hint=origin,
                file_extension=Path(origin).suffix if "/" not in origin else "",
            )

        # Infer tags if none provided
        tag_list = list(tags or [])
        if not tag_list:
            tag_list = self._classifier.infer_tags(
                content_snippet=content[:500] if content else "",
                origin=origin,
            )

        # Store content as document
        content_path = ""
        if content:
            doc_path = self.documents_dir / f"{source_id}.md"
            with open(doc_path, "w") as f:
                f.write(content)
            content_path = f"documents/{source_id}.md"

        # Build record
        record = {
            "source_id": source_id,
            "source_type": source_type,
            "origin": origin,
            "created_at": now,
            "updated_at": now,
            "trust_level": trust_level,
            "provenance": {
                "ingestion_path": ["register_source"],
                "transformation_chain": [{
                    "step": "register_source",
                    "timestamp": now,
                    "operator": "system",
                    "details": f"Source registered from {origin}",
                }],
                "canonical_refs": canonical_refs or [origin],
                "workflow_usage": [],
                "citation_count": 0,
            },
            "tags": tag_list,
            "project_scope": project_scope,
            "status": "active",
            "content_hash": content_hash,
            "summary": summary,
            "content_path": content_path,
        }

        # Write to disk
        self._write_record(record)

        # Cache
        self._cache[source_id] = record

        return record

    def _write_record(self, record: dict):
        """Write a source record to the filesystem."""
        path = self.sources_dir / f"{record['source_id']}.json"
        with open(path, "w") as f:
            json.dump(record, f, indent=2)

    def _find_by_hash(self, content_hash: str) -> Optional[dict]:
        """Search existing sources for a matching content hash."""
        for fpath in self.sources_dir.glob("*.json"):
            try:
                with open(fpath, "r") as f:
                    rec = json.load(f)
                if rec.get("content_hash") == content_hash:
                    return rec
            except (json.JSONDecodeError, KeyError):
                continue
        return None

    # ── Retrieval ──────────────────────────────────────

    def get_source(self, source_id: str) -> Optional[dict]:
        """Retrieve a source record by ID."""
        if source_id in self._cache:
            return dict(self._cache[source_id])

        path = self.sources_dir / f"{source_id}.json"
        if path.exists():
            with open(path, "r") as f:
                record = json.load(f)
            self._cache[source_id] = record
            return dict(record)

        return None

    def resolve_source(self, source_id: str) -> dict:
        """
        Resolve a source by ID. Raises if not found.

        Returns the full record including content from documents/.
        """
        record = self.get_source(source_id)
        if not record:
            raise SourceNotFoundError(f"Source '{source_id}' not found")

        # Attach content if path exists
        if record.get("content_path"):
            content_path = self.root / "knowledge" / record["content_path"]
            if content_path.exists():
                with open(content_path, "r") as f:
                    record["_content"] = f.read()

        return record

    def list_sources(
        self,
        status: Optional[str] = None,
        trust_level: Optional[str] = None,
        project_scope: Optional[str] = None,
        tag: Optional[str] = None,
    ) -> list[dict]:
        """
        List sources with optional filters.

        Args:
            status: Filter by status (active, stale, archived)
            trust_level: Filter by trust tier
            project_scope: Filter by project
            tag: Filter by tag

        Returns:
            List of source summary dicts.
        """
        results = []

        for fpath in sorted(self.sources_dir.glob("*.json")):
            try:
                with open(fpath, "r") as f:
                    rec = json.load(f)
            except json.JSONDecodeError:
                continue

            # Apply filters
            if status and rec.get("status") != status:
                continue
            if trust_level and rec.get("trust_level") != trust_level:
                continue
            if project_scope and rec.get("project_scope") != project_scope:
                continue
            if tag and tag not in rec.get("tags", []):
                continue

            results.append({
                "source_id": rec["source_id"],
                "source_type": rec.get("source_type", ""),
                "origin": rec.get("origin", ""),
                "trust_level": rec.get("trust_level", ""),
                "status": rec.get("status", ""),
                "tags": rec.get("tags", []),
                "project_scope": rec.get("project_scope", ""),
                "summary": rec.get("summary", ""),
            })

        return results

    def load_all(self):
        """Pre-load all source records into cache."""
        for fpath in sorted(self.sources_dir.glob("*.json")):
            try:
                with open(fpath, "r") as f:
                    rec = json.load(f)
                self._cache[rec["source_id"]] = rec
            except (json.JSONDecodeError, KeyError):
                continue

    # ── Classification ─────────────────────────────────

    def classify_source(self, source_id: str) -> dict:
        """
        Re-classify a source. Updates type and tags.

        Trust tier is NEVER auto-changed by this method.
        """
        record = self.get_source(source_id)
        if not record:
            raise SourceNotFoundError(f"Source '{source_id}' not found")

        # Re-classify type
        record["source_type"] = self._classifier.classify_source_type(
            hint=record["origin"],
        )

        # Re-infer tags (preserving existing)
        existing = set(record.get("tags", []))
        new_tags = self._classifier.infer_tags(
            content_snippet=record.get("summary", ""),
            origin=record["origin"],
            existing_tags=list(existing),
        )
        record["tags"] = sorted(set(existing) | set(new_tags))

        # Update timestamp
        now = datetime.now(timezone.utc).isoformat()
        record["updated_at"] = now
        record["provenance"]["transformation_chain"].append({
            "step": "classify_source",
            "timestamp": now,
            "operator": "system",
            "details": "Source re-classified",
        })

        self._write_record(record)
        self._cache[source_id] = record
        return record

    # ── Status management ──────────────────────────────

    def mark_stale(self, source_id: str) -> dict:
        """Mark a source as stale. Never deletes — status is advisory."""
        return self._update_status(source_id, "stale")

    def mark_archived(self, source_id: str) -> dict:
        """Mark a source as archived. Content retained indefinitely."""
        return self._update_status(source_id, "archived")

    def reactivate(self, source_id: str) -> dict:
        """Reactivate a stale or archived source."""
        return self._update_status(source_id, "active")

    def _update_status(self, source_id: str, new_status: str) -> dict:
        """Update a source's status with audit trail."""
        record = self.get_source(source_id)
        if not record:
            raise SourceNotFoundError(f"Source '{source_id}' not found")

        old_status = record.get("status", "")
        record["status"] = new_status
        record["updated_at"] = datetime.now(timezone.utc).isoformat()

        record["provenance"]["transformation_chain"].append({
            "step": f"status_change",
            "timestamp": record["updated_at"],
            "operator": "system",
            "details": f"Status changed: {old_status} -> {new_status}",
        })

        self._write_record(record)
        self._cache[source_id] = record
        return record

    # ── Trust tier management ─────────────────────────

    def set_trust_level(self, source_id: str, new_tier: str, operator: str = "operator") -> dict:
        """
        Change a source's trust tier. MUST be an explicit operator action.

        Trust tiers never auto-escalate. This is the only path to change.
        """
        if new_tier not in VALID_TRUST_TIERS:
            raise ValueError(f"Invalid trust tier: '{new_tier}'. Must be one of {VALID_TRUST_TIERS}")

        record = self.get_source(source_id)
        if not record:
            raise SourceNotFoundError(f"Source '{source_id}' not found")

        old_tier = record.get("trust_level", "")
        record["trust_level"] = new_tier
        record["updated_at"] = datetime.now(timezone.utc).isoformat()

        record["provenance"]["transformation_chain"].append({
            "step": "trust_level_change",
            "timestamp": record["updated_at"],
            "operator": operator,
            "details": f"Trust level changed: {old_tier} -> {new_tier} by {operator}",
        })

        self._write_record(record)
        self._cache[source_id] = record
        return record

    # ── Usage tracking ────────────────────────────────

    def record_citation(self, source_id: str, workflow_run_id: str = ""):
        """Record that a source was cited in a workflow."""
        record = self.get_source(source_id)
        if not record:
            return

        record["provenance"]["citation_count"] = record["provenance"].get("citation_count", 0) + 1

        if workflow_run_id and workflow_run_id not in record["provenance"].get("workflow_usage", []):
            record["provenance"]["workflow_usage"].append(workflow_run_id)

        record["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._write_record(record)
        self._cache[source_id] = record

    # ── Stats ─────────────────────────────────────────

    def count(self) -> int:
        """Total number of registered sources."""
        return len(list(self.sources_dir.glob("*.json")))

    def count_by_trust(self) -> dict[str, int]:
        """Count sources by trust tier."""
        counts = {t: 0 for t in VALID_TRUST_TIERS}
        for fpath in self.sources_dir.glob("*.json"):
            try:
                with open(fpath, "r") as f:
                    rec = json.load(f)
                tier = rec.get("trust_level", "unknown")
                if tier in counts:
                    counts[tier] += 1
            except json.JSONDecodeError:
                continue
        return counts

    def count_by_status(self) -> dict[str, int]:
        """Count sources by status."""
        counts = {s: 0 for s in VALID_STATUSES}
        for fpath in self.sources_dir.glob("*.json"):
            try:
                with open(fpath, "r") as f:
                    rec = json.load(f)
                status = rec.get("status", "active")
                if status in counts:
                    counts[status] += 1
            except json.JSONDecodeError:
                continue
        return counts
