"""
OverCR v2.4.0 — Research Packet Builder

Builds structured research packets that pass L1-L6 validation.
Every packet carries:
  - Full provenance chain (where the data came from)
  - Citation references (which sources support each claim)
  - Confidence scoring (how reliable the conclusions are)
  - Contradiction indicators (what conflicts exist)
  - Audit metadata (who built it, when, in what mode)

Packet types produced:
  - claim_review packets
  - research_brief packets
  - contradiction_summary packets
  - source_quality packets

All packets route through OverCR's 6-level validator before
advancement. No packet is delivered without validation.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from knowledge.source_registry import SourceRegistry
from knowledge.provenance_tracker import ProvenanceTracker
from knowledge.contradiction_detector import ContradictionDetector
from knowledge.source_classifier import SourceClassifier


class ResearchPacketBuilder:
    """
    Builds validated research packets with full provenance.

    Every packet includes provenance_chain, citation_refs,
    confidence_scoring, and audit_metadata.
    """

    def __init__(
        self,
        registry: SourceRegistry,
        tracker: ProvenanceTracker,
        detector: ContradictionDetector,
        task_counter_start: int = 0,
    ):
        self.registry = registry
        self.tracker = tracker
        self.detector = detector
        self.classifier = SourceClassifier()
        self._task_counter = task_counter_start

    # ── Packet envelope (shared across all types) ──────

    def _build_envelope(
        self,
        packet_type: str,
        summary: str,
        source_ids: list[str],
        approval_required: bool = False,
    ) -> dict:
        """Build the common packet envelope."""
        self._task_counter += 1
        task_id = f"task-{self._task_counter:04d}"

        now = datetime.now(timezone.utc).isoformat()

        # Build provenance chain from source records
        provenance_chain = []
        for sid in source_ids:
            rec = self.registry.get_source(sid)
            if rec:
                provenance_chain.append({
                    "step": "source_reference",
                    "timestamp": now,
                    "operator": "ResearchPacketBuilder",
                    "source_ids": [sid],
                    "description": f"Referenced source: {rec.get('origin', sid)}",
                })

        # Build citation references
        citation_refs = []
        for sid in source_ids:
            rec = self.registry.get_source(sid)
            if rec:
                citation_refs.append({
                    "source_id": sid,
                    "cited_as": rec.get("origin", sid),
                    "confidence_contribution": self._trust_to_confidence(
                        rec.get("trust_level", "unknown")
                    ),
                    "excerpt": rec.get("summary", "")[:200],
                })

        # Detect contradictions among sources
        contradictions = []
        if len(source_ids) >= 2:
            contra_report = self.detector.detect_contradictions(source_ids)
            contradictions = [
                {
                    "claim_a": c.get("claim_a", ""),
                    "claim_b": c.get("claim_b", ""),
                    "source_a": c.get("source_a", ""),
                    "source_b": c.get("source_b", ""),
                    "severity": c.get("severity", "partial"),
                    "resolution_status": "unresolved",
                }
                for c in contra_report
            ]

        # Confidence scoring
        confidence = self._compute_confidence(source_ids)

        # Supporting sources
        supporting = [sid for sid in source_ids
                      if self._get_trust_tier(sid) not in ("suspicious", "rejected")]

        # Trust tiers represented
        trust_tiers = set()
        for sid in source_ids:
            rec = self.registry.get_source(sid)
            if rec:
                trust_tiers.add(rec.get("trust_level", "unknown"))

        return {
            "packet_type": packet_type,
            "version": "1.0",
            "timestamp": now,
            "source": "knower",
            "target": "overcr",
            "task_id": task_id,
            "summary": summary,
            "provenance_chain": provenance_chain,
            "citation_refs": citation_refs,
            "contradiction_indicators": contradictions,
            "confidence_scoring": confidence,
            "supporting_sources": supporting,
            "audit_metadata": {
                "builder_version": "2.4.0",
                "generated_at": now,
                "deterministic_mode": True,
                "sources_consulted_count": len(source_ids),
                "contradictions_found": len(contradictions),
                "stale_sources_flagged": self._count_stale(source_ids),
                "trust_tiers_represented": sorted(trust_tiers),
            },
            "approval_required": approval_required,
        }

    # ── Claim Review Packet ────────────────────────────

    def build_claim_review(
        self,
        claims: list[str],
        source_ids: list[str],
        topic: str = "",
        operator: str = "operator",
    ) -> dict:
        """
        Build a knower_claim_review packet.

        Classifies each claim against the registered sources.

        Args:
            claims: List of claim strings to review
            source_ids: Sources to check claims against
            topic: Topic context
            operator: Operator identifier

        Returns:
            Validated claim_review packet dict.
        """
        packet = self._build_envelope(
            packet_type="knower_claim_review",
            summary=f"Claim review for: {topic or 'unspecified topic'} ({len(claims)} claims)",
            source_ids=source_ids,
            approval_required=False,
        )

        # Classify each claim against sources
        classified = []
        for claim_text in claims:
            result = self._classify_claim(claim_text, source_ids)
            classified.append(result)

        # Build operator brief
        fact_count = sum(1 for c in classified if c.get("classification") == "fact")
        inference_count = sum(1 for c in classified if c.get("classification") == "inference")
        assumption_count = sum(1 for c in classified if c.get("classification") == "assumption")
        rumor_count = sum(1 for c in classified if c.get("classification") == "rumor")

        operator_brief = (
            f"Of {len(classified)} claim(s) reviewed against {len(source_ids)} source(s): "
            f"{fact_count} fact(s), {inference_count} inference(s), "
            f"{assumption_count} assumption(s), {rumor_count} rumor(s). "
            f"Sources span trust tiers: {', '.join(packet['audit_metadata']['trust_tiers_represented'])}. "
            f"High-confidence classifications require primary source verification."
        )

        packet["claim_review_data"] = {
            "topic": topic or "unspecified topic",
            "claims": classified,
            "operator_brief": operator_brief,
        }

        # Record citations
        for sid in source_ids:
            self.tracker.record_citation(
                sid, packet["task_id"],
                cited_as=f"Claim review for '{topic}'",
                context=topic[:200],
            )

        return packet

    def _classify_claim(self, claim_text: str, source_ids: list[str]) -> dict:
        """Classify a single claim against available sources."""
        claim_lower = claim_text.lower()
        evidence = []
        unknowns = []

        # Check each source for supporting evidence
        for sid in source_ids:
            rec = self.registry.get_source(sid)
            if not rec:
                continue

            # Simple heuristic: does the source content mention this claim?
            resolved = self.registry.resolve_source(sid)
            content = resolved.get("_content", "").lower()
            if content and claim_text.lower()[:50] in content:
                evidence.append(
                    f"Source {sid} ({rec.get('source_type', '?')}): claim text found in content"
                )

        # Heuristic classification
        if evidence:
            classification = "fact"
            confidence = 3
            source_quality = "secondary"
        elif any(w in claim_lower for w in ["will", "expected", "projected", "should result"]):
            classification = "inference"
            confidence = 2
            source_quality = "secondary"
        elif any(w in claim_lower for w in ["believe", "assume", "likely", "probably"]):
            classification = "assumption"
            confidence = 1
            source_quality = "tertiary"
        elif any(w in claim_lower for w in ["rumor", "supposedly", "they say", "heard"]):
            classification = "rumor"
            confidence = 1
            source_quality = "unverified"
        else:
            classification = "inference"
            confidence = 2
            source_quality = "secondary"

        if not evidence:
            unknowns.append("No source in knowledge index directly supports this claim")

        return {
            "text": claim_text,
            "classification": classification,
            "confidence": confidence,
            "source_quality": source_quality,
            "evidence": evidence,
            "unknowns": unknowns,
        }

    # ── Research Brief Packet ───────────────────────────

    def build_research_brief(
        self,
        query: str,
        source_ids: list[str],
        operator: str = "operator",
    ) -> dict:
        """
        Build a research_brief packet.

        Summarizes findings across multiple sources for a research query.

        Args:
            query: Research question or topic
            source_ids: Relevant sources
            operator: Operator identifier

        Returns:
            Research brief packet dict.
        """
        packet = self._build_envelope(
            packet_type="knower_research",
            summary=f"Research brief for: {query}",
            source_ids=source_ids,
            approval_required=False,
        )

        # Build findings from sources
        findings = []
        for sid in source_ids:
            rec = self.registry.get_source(sid)
            if not rec:
                continue
            findings.append({
                "claim": rec.get("summary", f"Source {sid}"),
                "confidence": self._trust_to_confidence_rating(
                    rec.get("trust_level", "unknown")
                ),
                "sources": [{
                    "title": rec.get("origin", sid),
                    "type": rec.get("source_type", "other"),
                    "quality": rec.get("trust_level", "unknown"),
                }],
                "gaps": [
                    "Verification against primary sources recommended",
                    "Cross-reference with independent sources pending",
                ],
            })

        if not findings:
            findings.append({
                "claim": f"No sources found for: {query}",
                "confidence": 1,
                "sources": [],
                "gaps": ["No registered sources matched the query"],
            })

        packet["research_data"] = {
            "topic": query,
            "findings": findings,
        }
        packet["audit_trail"] = {
            "worker_version": "2.4.0",
            "execution_timestamp": packet["timestamp"],
            "sources_consulted": [
                {"reference": self.registry.get_source(sid).get("origin", sid)
                 if self.registry.get_source(sid) else sid,
                 "reliability": self.registry.get_source(sid).get("trust_level", "unknown")
                 if self.registry.get_source(sid) else "unknown"}
                for sid in source_ids
            ],
            "methodology_notes": "Analysis based on registered knowledge sources. No external action taken.",
        }

        # Record citations
        for sid in source_ids:
            self.tracker.record_citation(
                sid, packet["task_id"],
                cited_as=f"Research brief for '{query}'",
                context=query[:200],
            )

        return packet

    # ── Contradiction Summary Packet ───────────────────

    def build_contradiction_summary(
        self,
        source_ids: list[str],
        topic: str = "",
        operator: str = "operator",
    ) -> dict:
        """
        Build a contradiction_summary packet.

        Lists all contradictions found between sources with
        both sides preserved. Never resolves.

        Args:
            source_ids: Sources to analyze for contradictions
            topic: Topic context
            operator: Operator identifier

        Returns:
            Contradiction summary packet dict.
        """
        contradictions = self.detector.detect_contradictions(source_ids)

        packet = self._build_envelope(
            packet_type="contradiction_summary",
            summary=f"Contradiction analysis: {topic or 'multi-source'} "
                    f"({len(contradictions)} contradiction(s) found)",
            source_ids=source_ids,
            approval_required=True,  # Contradiction packets always require review
        )

        # Map to valid KnowER packet type (contradiction_summary maps to knower_claim_review
        # envelope since that's the closest valid L1-L6 type)
        packet["packet_type"] = "knower_claim_review"

        # Build claim review data from contradictions
        claims_data = []
        for i, c in enumerate(contradictions):
            claims_data.append({
                "text": f"Contradiction {i+1}: {c.get('claim_a', '')[:100]} vs {c.get('claim_b', '')[:100]}",
                "classification": "inference",
                "confidence": 2,
                "source_quality": "secondary",
                "evidence": [
                    f"Source A ({c.get('source_a', '?')}, trust={c.get('trust_a', '?')}): {c.get('claim_a', '')[:100]}",
                    f"Source B ({c.get('source_b', '?')}, trust={c.get('trust_b', '?')}): {c.get('claim_b', '')[:100]}",
                ],
                "unknowns": [
                    f"Contradiction severity: {c.get('severity', 'unknown')}",
                    "Operator review required to resolve or acknowledge",
                ],
            })

        operator_brief = (
            f"Contradiction analysis across {len(source_ids)} source(s) found "
            f"{len(contradictions)} contradiction(s). "
            f"ALL contradictions remain unresolved. "
            f"Both sides of every contradiction are preserved. "
            f"Operator must review and decide: acknowledge, investigate, or discard."
        )

        packet["claim_review_data"] = {
            "topic": topic or "Contradiction analysis",
            "claims": claims_data,
            "operator_brief": operator_brief,
        }

        packet["approval_required"] = True

        return packet

    # ── Source Quality Packet ───────────────────────────

    def build_source_quality(
        self,
        source_ids: list[str],
        operator: str = "operator",
    ) -> dict:
        """
        Build a source_quality packet.

        Assesses quality metrics for a set of sources: trust tiers,
        staleness, citation counts, and provenance integrity.

        Args:
            source_ids: Sources to assess
            operator: Operator identifier

        Returns:
            Source quality packet dict.
        """
        assessments = []
        for sid in source_ids:
            rec = self.registry.get_source(sid)
            if not rec:
                assessments.append({
                    "source_id": sid,
                    "status": "not_found",
                    "assessment": "Source not in registry",
                })
                continue

            full = self.tracker.get_full_provenance(sid)

            # Compute quality score (simple weighted average)
            trust_scores = {"verified": 4, "reputable": 3, "unknown": 2, "suspicious": 1, "rejected": 0}
            trust_score = trust_scores.get(rec.get("trust_level", "unknown"), 2)
            citation_weight = min(rec.get("provenance", {}).get("citation_count", 0) * 0.1, 1.0)
            staleness = self.classifier.should_mark_stale(
                source_age_days=0,  # Unknown age if not tracked
                trust_tier=rec.get("trust_level", "unknown"),
            )
            staleness_penalty = -0.5 if staleness else 0.0
            quality_score = (trust_score / 4.0 * 0.6) + (citation_weight * 0.3) + max(0, 0.1 + staleness_penalty)
            quality_score = round(max(0.0, min(1.0, quality_score)), 2)

            assessments.append({
                "source_id": sid,
                "status": "assessed",
                "trust_level": rec.get("trust_level", "unknown"),
                "source_type": rec.get("source_type", "other"),
                "quality_score": quality_score,
                "citation_count": rec.get("provenance", {}).get("citation_count", 0),
                "transformation_count": len(full.get("transformation_chain", [])),
                "staleness_flagged": staleness,
                "contradictions_involving": len(full.get("contradictions", [])),
                "recommendation": self._quality_recommendation(quality_score, staleness),
            })

        packet = self._build_envelope(
            packet_type="knower_claim_review",  # Valid L1-L6 envelope type
            summary=f"Source quality assessment for {len(source_ids)} source(s)",
            source_ids=source_ids,
            approval_required=False,
        )

        # Build claim review form for quality assessments
        claims_data = []
        for a in assessments:
            claims_data.append({
                "text": f"Source {a['source_id']}: quality={a['quality_score']:.2f}, trust={a['trust_level']}",
                "classification": "fact" if a.get("quality_score", 0) >= 0.6 else "inference",
                "confidence": min(4, max(1, int(a.get("quality_score", 0.5) * 4 + 1))),
                "source_quality": "primary" if a.get("trust_level") == "verified" else "secondary",
                "evidence": [
                    f"Trust tier: {a.get('trust_level', '?')}",
                    f"Citations: {a.get('citation_count', 0)}",
                    f"Quality score: {a['quality_score']:.2f}",
                ],
                "unknowns": [
                    f"Recommendation: {a.get('recommendation', 'review')}",
                ] if a.get("recommendation") else [],
            })

        operator_brief = (
            f"Assessed {len(assessments)} source(s). "
            f"Quality scores range from {min(a['quality_score'] for a in assessments):.2f} "
            f"to {max(a['quality_score'] for a in assessments):.2f}. "
            f"Trust tiers: {', '.join(sorted(set(a['trust_level'] for a in assessments)))}. "
            f"Sources flagged stale: {sum(1 for a in assessments if a.get('staleness_flagged'))}."
        )

        packet["claim_review_data"] = {
            "topic": "Source Quality Assessment",
            "claims": claims_data,
            "operator_brief": operator_brief,
        }

        # Attach raw quality data
        packet["_source_quality_data"] = assessments

        return packet

    # ── Helpers ──────────────────────────────────────────

    def _trust_to_confidence(self, trust_tier: str) -> float:
        """Map trust tier to a 0-1 confidence contribution."""
        return {
            "verified": 0.9,
            "reputable": 0.7,
            "unknown": 0.4,
            "suspicious": 0.2,
            "rejected": 0.0,
        }.get(trust_tier, 0.4)

    def _trust_to_confidence_rating(self, trust_tier: str) -> int:
        """Map trust tier to a 1-4 confidence rating."""
        return {
            "verified": 4,
            "reputable": 3,
            "unknown": 2,
            "suspicious": 1,
            "rejected": 1,
        }.get(trust_tier, 2)

    def _get_trust_tier(self, source_id: str) -> str:
        """Get a source's trust tier."""
        rec = self.registry.get_source(source_id)
        if rec:
            return rec.get("trust_level", "unknown")
        return "unknown"

    def _compute_confidence(self, source_ids: list[str]) -> dict:
        """Compute overall confidence score from sources."""
        if not source_ids:
            return {"overall": 1, "source_quality_weight": 0.0,
                    "corroboration_factor": 0.0, "contradiction_penalty": 0.0}

        contribs = [self._trust_to_confidence(self._get_trust_tier(sid))
                    for sid in source_ids]
        avg_trust = sum(contribs) / len(contribs)
        corroboration = min(1.0, 0.2 * (len(source_ids) - 1))  # Bonus for multiple sources

        return {
            "overall": max(1, min(4, int(avg_trust * 4 + corroboration * 2))),
            "source_quality_weight": round(avg_trust, 2),
            "corroboration_factor": round(corroboration, 2),
            "contradiction_penalty": 0.0,
        }

    def _count_stale(self, source_ids: list[str]) -> int:
        """Count how many sources are flagged stale."""
        count = 0
        for sid in source_ids:
            rec = self.registry.get_source(sid)
            if rec and rec.get("status") == "stale":
                count += 1
        return count

    def _quality_recommendation(self, score: float, staleness: bool) -> str:
        """Generate a quality recommendation string."""
        if staleness:
            return "REVIEW: source may be stale — verify timeliness"
        if score >= 0.8:
            return "TRUST: high-quality source with strong provenance"
        elif score >= 0.5:
            return "USE_WITH_CAUTION: moderate quality — verify key claims"
        else:
            return "AVOID: low quality or insufficient provenance"
