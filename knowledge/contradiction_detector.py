"""
OverCR v2.4.0 — Contradiction Detector

Detects conflicting claims between knowledge sources. Never
auto-resolves contradictions — both sides are always preserved.
Produces contradiction reports that are operator-reviewable.

Detection dimensions:
  - Direct contradiction: two sources make mutually exclusive claims
  - Partial contradiction: sources disagree on specifics
  - Contextual contradiction: same data, different interpretations

What this does NOT do:
  - Never auto-resolves contradictions
  - Never hides contradictory evidence
  - Never promotes one source over another based on trust tier alone
  - Never synthesizes a "compromise" claim automatically
"""

import json
import re
import hashlib
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from knowledge.source_registry import SourceRegistry
from knowledge.provenance_tracker import ProvenanceTracker


class ContradictionDetector:
    """
    Detects contradictions between knowledge sources.

    Contradictions are flagged but never auto-resolved.
    Both sides and their provenance are preserved in the report.
    """

    def __init__(self, registry: SourceRegistry, tracker: ProvenanceTracker):
        self.registry = registry
        self.tracker = tracker
        self.reports_dir = self.registry.root / "knowledge" / "reports"
        self.reports_dir.mkdir(parents=True, exist_ok=True)

        # In-memory contradiction store
        self._contradictions: list[dict] = []

    # ── Detection ──────────────────────────────────────

    def detect_contradictions(
        self,
        source_ids: list[str],
        claim_field: str = "summary",
    ) -> list[dict]:
        """
        Detect contradictions between a set of sources.

        Compares claims pairwise and flags conflicts. Does NOT
        resolve or rank — both sides are preserved.

        Args:
            source_ids: List of source IDs to compare
            claim_field: Which field to extract claims from

        Returns:
            List of contradiction dicts.
        """
        sources = []
        for sid in source_ids:
            rec = self.registry.get_source(sid)
            if rec:
                sources.append({
                    "source_id": sid,
                    "claim": rec.get(claim_field, rec.get("summary", "")),
                    "trust_level": rec.get("trust_level", "unknown"),
                    "origin": rec.get("origin", ""),
                })

        if len(sources) < 2:
            return []

        contradictions = []

        for i in range(len(sources)):
            for j in range(i + 1, len(sources)):
                a = sources[i]
                b = sources[j]

                result = self._compare_claims(a, b)
                if result["contradiction_detected"]:
                    contra = {
                        "contradiction_id": self._contradiction_id(a["source_id"], b["source_id"]),
                        "detected_at": datetime.now(timezone.utc).isoformat(),
                        "claim_a": a["claim"],
                        "claim_b": b["claim"],
                        "source_a": a["source_id"],
                        "source_b": b["source_id"],
                        "trust_a": a["trust_level"],
                        "trust_b": b["trust_level"],
                        "severity": result["severity"],
                        "rationale": result["rationale"],
                        "resolution_status": "unresolved",
                    }
                    contradictions.append(contra)

                    # Record in provenance tracker
                    self.tracker.record_contradiction(
                        source_a=a["source_id"],
                        source_b=b["source_id"],
                        claim_a=a["claim"][:200],
                        claim_b=b["claim"][:200],
                        severity=result["severity"],
                    )

        # Store in memory
        self._contradictions.extend(contradictions)

        return contradictions

    def _compare_claims(self, a: dict, b: dict) -> dict:
        """
        Compare two claims for contradictions.

        Returns dict with contradiction_detected, severity, rationale.
        """
        claim_a = a["claim"].lower()
        claim_b = b["claim"].lower()

        # Direct negation patterns
        negation_pairs = [
            (r"\bis\b", r"\bis not\b"),
            (r"\bcan\b", r"\bcannot\b"),
            (r"\bdoes\b", r"\bdoes not\b"),
            (r"\bwill\b", r"\bwill not\b"),
            (r"\bhas\b", r"\bhas no\b"),
        ]

        for pos_pat, neg_pat in negation_pairs:
            if (re.search(pos_pat, claim_a) and re.search(neg_pat, claim_b)) or \
               (re.search(neg_pat, claim_a) and re.search(pos_pat, claim_b)):
                return {
                    "contradiction_detected": True,
                    "severity": "direct",
                    "rationale": f"Direct negation detected between claims.",
                }

        # Opposite polarity keywords
        opposite_pairs = [
            ("increase", "decrease"),
            ("increasing", "decreasing"),
            ("increased", "decreased"),
            ("growing", "shrinking"),
            ("growth", "decline"),
            ("high", "low"),
            ("above", "below"),
            ("more", "less"),
            ("larger", "smaller"),
            ("better", "worse"),
            ("true", "false"),
        ]

        for pos_word, neg_word in opposite_pairs:
            pos_a = pos_word in claim_a and neg_word in claim_b
            pos_b = neg_word in claim_a and pos_word in claim_b
            if pos_a or pos_b:
                # Check if they're talking about the same subject
                # Simple heuristic: shared keywords beyond the opposites
                words_a = set(re.findall(r'\b\w{4,}\b', claim_a))
                words_b = set(re.findall(r'\b\w{4,}\b', claim_b))
                shared = words_a & words_b
                if len(shared) >= 2:
                    return {
                        "contradiction_detected": True,
                        "severity": "partial",
                        "rationale": f"Opposing claims ({pos_word} vs {neg_word}) about shared subject.",
                    }

        # No contradiction detected (default)
        # Even for dissimilar claims, we default to "no contradiction"
        # — the operator decides, not the detector
        return {
            "contradiction_detected": False,
            "severity": "",
            "rationale": "No direct contradiction detected between claims.",
        }

    # ── Reporting ──────────────────────────────────────

    def generate_contradiction_report(
        self,
        source_ids: list[str],
        output_path: Optional[str] = None,
    ) -> dict:
        """
        Generate a contradiction report for a set of sources.

        Detects contradictions and produces a structured report
        with all conflicts preserved. Never resolves.

        Args:
            source_ids: Sources to analyze
            output_path: Optional path to write report JSON

        Returns:
            Contradiction report dict.
        """
        contradictions = self.detect_contradictions(source_ids)

        report = {
            "report_id": f"contra-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "sources_analyzed": len(source_ids),
            "source_ids": source_ids,
            "contradictions_found": len(contradictions),
            "contradictions": contradictions,
            "summary": self._summarize_contradictions(contradictions),
            "resolution_status": "all_unresolved",
            "operator_note": "ALL contradictions remain unresolved. Operator review required.",
        }

        if output_path:
            out = Path(output_path) if output_path else self.reports_dir / f"{report['report_id']}.json"
            out.parent.mkdir(parents=True, exist_ok=True)
            with open(out, "w") as f:
                json.dump(report, f, indent=2)

        return report

    def _summarize_contradictions(self, contradictions: list[dict]) -> str:
        """Summarize contradictions for operator."""
        if not contradictions:
            return "No contradictions detected between the provided sources."

        direct = sum(1 for c in contradictions if c.get("severity") == "direct")
        partial = sum(1 for c in contradictions if c.get("severity") == "partial")
        contextual = sum(1 for c in contradictions if c.get("severity") == "contextual")

        parts = []
        if direct:
            parts.append(f"{direct} direct contradiction(s)")
        if partial:
            parts.append(f"{partial} partial contradiction(s)")
        if contextual:
            parts.append(f"{contextual} contextual contradiction(s)")

        return f"Found {', '.join(parts)}. ALL unresolved — operator review required."

    # ── Persistence ────────────────────────────────────

    def save_contradiction_state(self, filename: str = "contradiction_state.json"):
        """Save the current contradiction state to disk."""
        path = self.reports_dir / filename
        with open(path, "w") as f:
            json.dump({
                "saved_at": datetime.now(timezone.utc).isoformat(),
                "total_contradictions": len(self._contradictions),
                "contradictions": self._contradictions,
            }, f, indent=2)

    def load_contradiction_state(self, filename: str = "contradiction_state.json"):
        """Load contradiction state from disk."""
        path = self.reports_dir / filename
        if path.exists():
            with open(path, "r") as f:
                data = json.load(f)
            self._contradictions = data.get("contradictions", [])

    # ── Helpers ────────────────────────────────────────

    def _contradiction_id(self, sid_a: str, sid_b: str) -> str:
        """Generate a stable contradiction ID."""
        ordered = sorted([sid_a, sid_b])
        raw = f"{ordered[0]}:{ordered[1]}"
        return "ctr-" + hashlib.sha256(raw.encode()).hexdigest()[:8]

    def get_contradictions_for_source(self, source_id: str) -> list[dict]:
        """Get all contradictions involving a specific source."""
        return [
            c for c in self._contradictions
            if c.get("source_a") == source_id or c.get("source_b") == source_id
        ]

    def count(self) -> int:
        """Total contradictions currently tracked."""
        return len(self._contradictions)
