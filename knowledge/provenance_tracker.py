"""
OverCR v2.4.0 — Provenance Tracker

Tracks the full lineage of every piece of information in the
knowledge subsystem: where it came from, how it was transformed,
which workflows used it, and which citations reference it.

Provenance is append-only and immutable. Once recorded, a
provenance entry is never rewritten or deleted. This is the
foundation of audit integrity for all knowledge operations.

Tracking dimensions:
  - Source origin: where the raw information came from
  - Ingestion path: how it entered the knowledge subsystem
  - Transformation chain: every normalization, classification, re-tagging
  - Workflow usage: which workflow executions cited this source
  - Citation references: which research packets cite this source
  - Contradiction lineage: which sources conflict with which others
"""

import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from knowledge.source_registry import SourceRegistry


class ProvenanceTracker:
    """
    Tracks the provenance of every knowledge artifact.

    Every tracking operation produces an append-only audit entry.
    Provenance is never rewritten — it accumulates.
    """

    def __init__(self, registry: SourceRegistry):
        self.registry = registry
        self.tracker_dir = self.registry.root / "knowledge" / "reports"
        self.tracker_dir.mkdir(parents=True, exist_ok=True)

    # ── Source origin tracking ───────────────────────

    def record_origin(self, source_id: str, origin_detail: str, origin_type: str = "document"):
        """
        Record additional origin detail for a source.

        The initial origin is captured at registration time.
        This adds supplementary origin information discovered later.
        """
        record = self.registry.get_source(source_id)
        if not record:
            return

        entry = {
            "type": "origin_recorded",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "origin_type": origin_type,
            "detail": origin_detail,
        }

        self._append_tracker_entry(source_id, entry)

    # ── Ingestion path tracking ──────────────────────

    def record_ingestion(
        self,
        source_id: str,
        method: str,
        ingestor_version: str = "2.4.0",
        operator: str = "system",
    ):
        """Record the ingestion method for a source."""
        entry = {
            "type": "ingestion_recorded",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "method": method,
            "ingestor_version": ingestor_version,
            "operator": operator,
        }

        self._append_tracker_entry(source_id, entry)

    def get_ingestion_path(self, source_id: str) -> list[dict]:
        """Get the full ingestion path for a source."""
        entries = self._load_tracker_entries(source_id)
        return [e for e in entries if e.get("type") == "ingestion_recorded"]

    # ── Transformation chain tracking ────────────────

    def record_transformation(
        self,
        source_id: str,
        transformation: str,
        operator: str = "system",
        before_hash: str = "",
        after_hash: str = "",
    ):
        """Record a transformation applied to a source."""
        entry = {
            "type": "transformation_recorded",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "transformation": transformation,
            "operator": operator,
            "before_content_hash": before_hash,
            "after_content_hash": after_hash,
        }

        # Also append to the source record's transformation chain
        record = self.registry.get_source(source_id)
        if record:
            chain = record.setdefault("provenance", {}).setdefault("transformation_chain", [])
            chain.append({
                "step": transformation,
                "timestamp": entry["timestamp"],
                "operator": operator,
                "details": f"Transformation: {transformation}",
            })
            self.registry._write_record(record)

        self._append_tracker_entry(source_id, entry)

    def get_transformation_chain(self, source_id: str) -> list[dict]:
        """Get the full transformation chain for a source."""
        entries = self._load_tracker_entries(source_id)
        return [e for e in entries if e.get("type") == "transformation_recorded"]

    # ── Workflow usage tracking ──────────────────────

    def record_workflow_usage(
        self,
        source_id: str,
        workflow_run_id: str,
        workflow_name: str = "",
        node_id: str = "",
    ):
        """Record that a workflow used this source."""
        entry = {
            "type": "workflow_usage_recorded",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "workflow_run_id": workflow_run_id,
            "workflow_name": workflow_name,
            "node_id": node_id,
        }

        # Update the source's provenance record
        self.registry.record_citation(source_id, workflow_run_id)

        self._append_tracker_entry(source_id, entry)

    def get_workflow_usage(self, source_id: str) -> list[dict]:
        """Get all workflow usages of a source."""
        entries = self._load_tracker_entries(source_id)
        return [e for e in entries if e.get("type") == "workflow_usage_recorded"]

    # ── Citation reference tracking ──────────────────

    def record_citation(
        self,
        source_id: str,
        cited_in_packet_id: str,
        cited_as: str = "",
        context: str = "",
    ):
        """Record that a source was cited in a research packet."""
        entry = {
            "type": "citation_recorded",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "cited_in_packet_id": cited_in_packet_id,
            "cited_as": cited_as,
            "context_snippet": context[:200] if context else "",
        }

        # Update citation count
        self.registry.record_citation(source_id)

        self._append_tracker_entry(source_id, entry)

    def get_citation_history(self, source_id: str) -> list[dict]:
        """Get all citation records for a source."""
        entries = self._load_tracker_entries(source_id)
        return [e for e in entries if e.get("type") == "citation_recorded"]

    # ── Contradiction lineage tracking ───────────────

    def record_contradiction(
        self,
        source_a: str,
        source_b: str,
        claim_a: str = "",
        claim_b: str = "",
        severity: str = "partial",
    ):
        """Record a contradiction between two sources."""
        entry = {
            "type": "contradiction_recorded",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source_a": source_a,
            "source_b": source_b,
            "claim_a": claim_a[:200] if claim_a else "",
            "claim_b": claim_b[:200] if claim_b else "",
            "severity": severity,
            "resolution_status": "unresolved",
        }

        self._append_tracker_entry(source_a, entry)

        # Also record on source_b for bidirectional tracking
        self._append_tracker_entry(source_b, entry)

    def get_contradiction_lineage(self, source_id: str) -> list[dict]:
        """Get all contradictions involving a source."""
        entries = self._load_tracker_entries(source_id)
        return [e for e in entries if e.get("type") == "contradiction_recorded"]

    # ── Full provenance report ───────────────────────

    def get_full_provenance(self, source_id: str) -> dict:
        """
        Generate a complete provenance report for a source.

        Includes: origin, ingestion path, transformation chain,
        workflow usage, citations, and contradictions.
        """
        entries = self._load_tracker_entries(source_id)
        record = self.registry.get_source(source_id)

        return {
            "source_id": source_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_record": record,
            "origin": [e for e in entries if e.get("type") == "origin_recorded"],
            "ingestion_path": [e for e in entries if e.get("type") == "ingestion_recorded"],
            "transformation_chain": [e for e in entries if e.get("type") == "transformation_recorded"],
            "workflow_usage": [e for e in entries if e.get("type") == "workflow_usage_recorded"],
            "citations": [e for e in entries if e.get("type") == "citation_recorded"],
            "contradictions": [e for e in entries if e.get("type") == "contradiction_recorded"],
            "total_entries": len(entries),
        }

    def export_provenance_report(self, source_id: str, output_path: Optional[str] = None) -> str:
        """
        Export a full provenance report to JSON.

        Args:
            source_id: The source to report on
            output_path: Optional path to write. If None, writes to reports/.

        Returns:
            Path to the written report.
        """
        report = self.get_full_provenance(source_id)

        if not output_path:
            output_path = str(self.tracker_dir / f"provenance_{source_id}.json")

        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w") as f:
            json.dump(report, f, indent=2)

        return str(out)

    # ── Storage ──────────────────────────────────────

    def _tracker_path(self, source_id: str) -> Path:
        """Get the tracker file path for a source."""
        return self.tracker_dir / f"tracker_{source_id}.jsonl"

    def _append_tracker_entry(self, source_id: str, entry: dict):
        """Append a tracker entry to the source's JSONL file."""
        path = self._tracker_path(source_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def _load_tracker_entries(self, source_id: str) -> list[dict]:
        """Load all tracker entries for a source."""
        path = self._tracker_path(source_id)
        if not path.exists():
            return []

        entries = []
        with open(path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

        return entries
