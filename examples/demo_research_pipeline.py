#!/usr/bin/env python3
"""
OverCR v2.4.0 — Demo: Research & Knowledge Pipeline

Demonstrates the complete knowledge subsystem pipeline:
  1. Ingest documents (markdown with frontmatter, JSON, plain text)
  2. Register and classify sources
  3. Build keyword/tag indexes
  4. Track provenance across all operations
  5. Detect contradictions between sources
  6. Generate claim review, research brief, contradiction summary, and quality packets
"""

import json
import sys
from pathlib import Path

OVERCR_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(OVERCR_ROOT))

from knowledge import (
    SourceRegistry,
    SourceClassifier,
    DocumentIngestor,
    KnowledgeIndex,
    ProvenanceTracker,
    ContradictionDetector,
    ResearchPacketBuilder,
)


def print_section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def main():
    registry = SourceRegistry(str(OVERCR_ROOT))
    ingestor = DocumentIngestor(registry)
    classifier = SourceClassifier()
    tracker = ProvenanceTracker(registry)
    detector = ContradictionDetector(registry, tracker)
    builder = ResearchPacketBuilder(registry, tracker, detector)

    # ── Step 1: Ingest Documents ────────────────────────
    print_section("Step 1: Ingesting Documents")

    # Markdown with frontmatter
    md_src = ingestor.ingest_markdown(
        content="""---
title: "OverCR Architecture Overview"
description: "A description of the OverCR portable AI orchestration substrate"
tags: [overcr, architecture, ai, orchestration]
author: "OverCR Team"
date: "2026-05-01"
---

# OverCR Architecture

OverCR is a portable AI orchestration substrate designed for persistent
contextual continuity. It uses a filesystem-first architecture that enables
recovery-oriented design and cold-start reconstruction.

## Key Features

- CAG (Context Accumulation Generation) for persistent state
- Filesystem-first state management
- Recovery-oriented architecture
- Subagent governance model
""",
        origin="research://overcr-architecture.md",
        project_scope="overcr",
        trust_level="verified",
    )
    print(f"  Markdown ingested: {md_src['source_id']:15s} — {md_src.get('summary', '')[:60]}")

    # JSON document
    json_src = ingestor.ingest_json(
        content=json.dumps({
            "title": "Market Analysis 2026",
            "description": "Analysis of AI orchestration market in 2026",
            "tags": ["market", "ai", "2026"],
            "findings": {
                "market_size": "12.5B",
                "growth_rate": "24% CAGR",
                "key_players": ["OverCR", "CompetitorA", "CompetitorB"],
            },
        }),
        origin="research://market-analysis-2026.json",
        project_scope="overcr",
        trust_level="reputable",
    )
    print(f"  JSON ingested:    {json_src['source_id']:15s} — {json_src.get('summary', '')[:60]}")

    # Plain text
    txt_src = ingestor.ingest_text(
        content="""Competitor Analysis Notes

CompetitorA focuses on cloud-only deployments with proprietary APIs.
This locks customers into their ecosystem and prevents migration.

OverCR offers filesystem-first portable deployment that can run
on any hardware including local appliances. No lock-in.

CompetitorB is also cloud-only but offers an API compatibility layer.
Still requires an internet connection for basic operations.""",
        origin="research://competitor-analysis.txt",
        project_scope="overcr",
        trust_level="reputable",
    )
    print(f"  Text ingested:    {txt_src['source_id']:15s} — {txt_src.get('summary', '')[:60]}")

    # ── Step 2: Source Classification ──────────────────
    print_section("Step 2: Source Classification & Trust Tiers")

    counts = registry.count_by_trust()
    print(f"  Sources by trust tier:")
    for tier, count in counts.items():
        if count > 0:
            print(f"    {tier:15s}: {count}")

    status_counts = registry.count_by_status()
    print(f"  Sources by status:")
    for st, count in status_counts.items():
        if count > 0:
            print(f"    {st:15s}: {count}")

    # ── Step 3: Build Index ────────────────────────────
    print_section("Step 3: Building Knowledge Index")

    idx = KnowledgeIndex(registry)
    idx.build(force=True)

    stats = idx.stats
    print(f"  Keyword terms indexed: {stats['keyword_terms']}")
    print(f"  Tags indexed:          {stats['tags']}")
    print(f"  Total sources:         {stats['total_sources']}")

    # Keyword search
    results = idx.keyword_search("orchestration architecture", limit=5)
    print(f"  Search 'orchestration architecture': {len(results)} result(s)")
    for r in results[:3]:
        rec = registry.get_source(r)
        if rec:
            print(f"    {r}: {rec.get('summary', '')[:50]}")

    # ── Step 4: Provenance Tracking ───────────────────
    print_section("Step 4: Provenance Tracking")

    tracker.record_transformation(
        md_src["source_id"], "re_tagged",
        operator="demo-operator",
    )
    tracker.record_workflow_usage(
        md_src["source_id"], "demo-run-001",
        workflow_name="knowledge-demo",
        node_id="research-ingest",
    )

    full_prov = tracker.get_full_provenance(md_src["source_id"])
    print(f"  Provenance entries for {md_src['source_id']}:")
    print(f"    Origins:             {len(full_prov['origin'])}")
    print(f"    Ingestion path:      {len(full_prov['ingestion_path'])}")
    print(f"    Transformations:     {len(full_prov['transformation_chain'])}")
    print(f"    Workflow usage:      {len(full_prov['workflow_usage'])}")
    print(f"    Citations:           {len(full_prov['citations'])}")

    # ── Step 5: Contradiction Detection ────────────────
    print_section("Step 5: Contradiction Detection")

    # Create two contradictory sources
    src_a = registry.register_source(
        origin="https://analyst-a.com/report",
        content="AI orchestration market is growing at 30% CAGR.",
        summary="AI orchestration market growing at 30% CAGR",
        tags=["market", "ai", "growth"],
        trust_level="reputable",
        project_scope="overcr",
    )
    src_b = registry.register_source(
        origin="https://analyst-b.com/report",
        content="AI orchestration market is shrinking by 5% annually.",
        summary="AI orchestration market is shrinking",
        tags=["market", "ai", "decline"],
        trust_level="suspicious",
        project_scope="overcr",
    )

    contradictions = detector.detect_contradictions([src_a["source_id"], src_b["source_id"]])
    print(f"  Contradictions found: {len(contradictions)}")
    for c in contradictions:
        print(f"    {c['severity']:10s}: {c['source_a']} vs {c['source_b']}")
        print(f"      A: {c['claim_a'][:80]}...")
        print(f"      B: {c['claim_b'][:80]}...")

    # ── Step 6: Generate Research Packets ──────────────
    print_section("Step 6: Research Packet Generation")

    # Claim review
    claim_pkt = builder.build_claim_review(
        claims=["OverCR is a portable AI orchestration substrate"],
        source_ids=[md_src["source_id"]],
        topic="OverCR architecture verification",
    )
    print(f"  Claim Review Packet:")
    print(f"    Type: {claim_pkt['packet_type']}")
    print(f"    Citations: {len(claim_pkt['citation_refs'])}")
    print(f"    Confidence: {claim_pkt['confidence_scoring']['overall']}/4")

    # Research brief
    brief = builder.build_research_brief(
        query="AI orchestration market trends",
        source_ids=[json_src["source_id"], txt_src["source_id"]],
    )
    print(f"  Research Brief Packet:")
    print(f"    Findings: {len(brief['research_data']['findings'])}")

    # Contradiction summary
    contra = builder.build_contradiction_summary(
        source_ids=[src_a["source_id"], src_b["source_id"]],
        topic="Market growth contradiction",
    )
    print(f"  Contradiction Summary:")
    print(f"    Requires approval: {contra['approval_required']}")
    print(f"    Contradictions: {contra['audit_metadata']['contradictions_found']}")

    # Source quality
    quality = builder.build_source_quality(
        source_ids=[md_src["source_id"], json_src["source_id"], txt_src["source_id"]],
    )
    qdata = quality.get("_source_quality_data", [])
    print(f"  Source Quality Assessment:")
    for q in qdata:
        print(f"    {q['source_id']}: score={q['quality_score']:.2f}, "
              f"trust={q['trust_level']}, rec={q.get('recommendation', '?')}")

    # ── Step 7: Summary ───────────────────────────────
    print_section("Step 7: Summary")

    print(f"  Sources registered: {registry.count()}")
    print(f"  Trust tiers: {registry.count_by_trust()}")
    print(f"  Index keywords: {idx.stats['keyword_terms']}")
    print(f"  Contradictions tracked: {detector.count()}")
    print(f"  All packets generated with full provenance chains")

    return 0


if __name__ == "__main__":
    sys.exit(main())
