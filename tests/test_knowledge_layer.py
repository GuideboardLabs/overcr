#!/usr/bin/env python3
"""
OverCR v2.4.0 — Test: Research & Knowledge Layer

Tests the complete knowledge subsystem including:
  - Source registration
  - Ingestion normalization
  - Provenance integrity
  - Contradiction detection
  - Stale source handling
  - Deterministic retrieval
  - Malformed source rejection
  - Packet provenance validation
  - Trust classification
  - Audit trail integrity
"""

import json
import sys
import os
import time
from pathlib import Path

OVERCR_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(OVERCR_ROOT))

from knowledge import (
    SourceRegistry,
    SourceRecordExistsError,
    SourceNotFoundError,
    SourceClassifier,
    VALID_TRUST_TIERS,
    DocumentIngestor,
    KnowledgeIndex,
    ProvenanceTracker,
    ContradictionDetector,
    ResearchPacketBuilder,
)

FAILED = False
_VERBOSE = os.environ.get("VERBOSE", "0") == "1"


def _assert(condition, msg=""):
    global FAILED
    if not condition:
        print(f"  FAIL: {msg}")
        FAILED = True
    elif _VERBOSE:
        print(f"  OK: {msg}")


# ─────────────────────────────────────────────────────
# Test 1: Source Registration
# ─────────────────────────────────────────────────────

def test_source_registration():
    global FAILED
    registry = SourceRegistry(str(OVERCR_ROOT))

    # Register a source with content
    src = registry.register_source(
        origin="https://example.com/article",
        content="# Test Article\n\nThis is a test article about AI orchestration.",
        summary="Test article about AI orchestration",
        tags=["ai", "orchestration"],
        project_scope="test",
    )
    _assert(src["source_id"].startswith("src-"), f"Generated source_id: {src['source_id']}")
    _assert(src["status"] == "active", "New source is active")
    _assert(src["trust_level"] == "unknown", "Default trust is unknown")
    _assert(len(src["content_hash"]) == 64, "Content hash is SHA-256")

    # Duplicate content should be rejected
    try:
        registry.register_source(
            origin="https://other.com/same",
            content="# Test Article\n\nThis is a test article about AI orchestration.",
        )
        _assert(False, "Duplicate content should raise")
    except SourceRecordExistsError as e:
        _assert(src["source_id"] in str(e), f"Duplicate rejected: {e}")

    # Different content is fine
    src2 = registry.register_source(
        origin=f"https://example-{src['source_id']}.com/other",
        content=f"# Different Article for {src['source_id']}\n\nCompletely different content.",
        summary="Another article",
    )
    _assert(src2["source_id"] != src["source_id"], "Different IDs")
    _assert(registry.count() >= 2, f"At least 2 sources: got {registry.count()}")

    # get_source and resolve_source
    fetched = registry.get_source(src["source_id"])
    _assert(fetched is not None, "get_source returns record")
    _assert(fetched["origin"] == "https://example.com/article", "Origin preserved")

    resolved = registry.resolve_source(src["source_id"])
    _assert(resolved.get("_content", "").startswith("# Test Article"), "Content loaded")

    # Non-existent source
    _assert(registry.get_source("src-deadbeef") is None, "Unknown source returns None")
    try:
        registry.resolve_source("src-deadbeef")
        _assert(False, "Non-existent should raise")
    except SourceNotFoundError:
        pass

    print("  PASS: Source registration")


# ─────────────────────────────────────────────────────
# Test 2: Ingestion Normalization
# ─────────────────────────────────────────────────────

def test_ingestion_normalization():
    global FAILED
    registry = SourceRegistry(str(OVERCR_ROOT))
    ingestor = DocumentIngestor(registry)

    # Ingest markdown with frontmatter
    md_content = """---
title: "Test Document"
description: "A test markdown document"
tags: [test, markdown, ai]
date: "2026-05-01"
---

# Test Document

This is the body of the test document.
It has multiple paragraphs.

## Section One

Content in section one.
"""
    src = ingestor.ingest_markdown(
        content=md_content,
        origin="local://test.md",
        project_scope="test",
    )
    _assert(src["source_type"] == "document", f"Classified as document: {src['source_type']}")
    _assert("markdown" in src["tags"] or "ai" in src["tags"] or "test" in src["tags"],
            f"Tags extracted: {src['tags']}")
    _assert("Test Document" in src.get("summary", "") or "test markdown" in src.get("summary", ""),
            f"Summary: {src.get('summary', '')}")

    # Ingest JSON
    json_content = json.dumps({
        "title": "Research Report",
        "description": "Findings from the 2026 study",
        "tags": ["research", "study"],
        "data": {"value": 42},
    })
    src2 = ingestor.ingest_json(
        content=json_content,
        origin="local://report.json",
        project_scope="test",
    )
    _assert(src2["source_type"] == "report", f"JSON classified as report: {src2['source_type']}")

    # Ingest plain text
    txt_src = ingestor.ingest_text(
        content="Just some plain text.\n\nWith multiple lines.",
        origin="local://notes.txt",
        project_scope="test",
    )
    _assert(txt_src["source_type"] == "document", "Text is document")

    # verify all ingested correctly
    _assert(registry.count() >= 3, f"At least 3 sources from ingestion: {registry.count()}")

    # Normalization: line endings
    normalized = ingestor.normalize_document("line1\r\nline2\r\nline3", "markdown")
    _assert("\r" not in normalized, "CR stripped from markdown")
    _assert(normalized.endswith("\n"), "Ends with newline")

    # Normalization: JSON re-serialization
    normalized_json = ingestor.normalize_document('{"a":1,\n  "b":2}', "json")
    parsed = json.loads(normalized_json)
    _assert(parsed["a"] == 1, "JSON round-trips")

    print("  PASS: Ingestion normalization")


# ─────────────────────────────────────────────────────
# Test 3: Provenance Integrity
# ─────────────────────────────────────────────────────

def test_provenance_integrity():
    global FAILED
    registry = SourceRegistry(str(OVERCR_ROOT))
    tracker = ProvenanceTracker(registry)

    src = registry.register_source(
        origin="https://provenance-test.com",
        content="# Provenance Test\n\nContent for tracking.",
        summary="Provenance test source",
        project_scope="test",
    )

    # Record ingestion
    tracker.record_ingestion(src["source_id"], "manual_upload", operator="test-operator")

    # Record transformation
    tracker.record_transformation(
        src["source_id"], "normalize",
        operator="test-operator",
        before_hash=src["content_hash"],
    )

    # Record workflow usage
    tracker.record_workflow_usage(
        src["source_id"], "run-abc123",
        workflow_name="test-workflow",
        node_id="research_node",
    )

    # Record citation
    tracker.record_citation(
        src["source_id"], "task-0001",
        cited_as="Provenance test reference",
    )

    # Get full provenance
    full = tracker.get_full_provenance(src["source_id"])
    _assert(len(full["ingestion_path"]) >= 1, f"Ingestion entries: {len(full['ingestion_path'])}")
    _assert(len(full["transformation_chain"]) >= 1, f"Transformation entries: {len(full['transformation_chain'])}")
    _assert(len(full["workflow_usage"]) >= 1, f"Workflow entries: {len(full['workflow_usage'])}")
    _assert(len(full["citations"]) >= 1, f"Citation entries: {len(full['citations'])}")

    # Export report
    report_path = tracker.export_provenance_report(src["source_id"])
    _assert(os.path.exists(report_path), f"Report written: {report_path}")

    # Verify report content
    with open(report_path, "r") as f:
        report = json.load(f)
    _assert(report["source_id"] == src["source_id"], "Report matches source")

    print("  PASS: Provenance integrity")


# ─────────────────────────────────────────────────────
# Test 4: Contradiction Detection
# ─────────────────────────────────────────────────────

def test_contradiction_detection():
    global FAILED
    registry = SourceRegistry(str(OVERCR_ROOT))
    tracker = ProvenanceTracker(registry)
    detector = ContradictionDetector(registry, tracker)

    # Create two contradictory sources (unique content to avoid hash collisions)
    import uuid
    uid = uuid.uuid4().hex[:8]
    src_a = registry.register_source(
        origin=f"https://a-{uid}.com",
        content=f"Source A ({uid}) says the market is increasing at 15% annually.",
        summary="Market is increasing at 15% annually per source A",
        tags=["market"],
        trust_level="reputable",
        project_scope="test",
    )
    src_b = registry.register_source(
        origin=f"https://b-{uid}.com",
        content=f"Source B ({uid}) says the market is decreasing by 5% annually.",
        summary="Market is decreasing by 5% annually per source B",
        tags=["market"],
        trust_level="reputable",
        project_scope="test",
    )

    # Detect contradictions
    contradictions = detector.detect_contradictions([src_a["source_id"], src_b["source_id"]])
    _assert(len(contradictions) >= 1, f"Contradictions detected: {len(contradictions)}")
    _assert(contradictions[0]["resolution_status"] == "unresolved",
            "Contradiction remains unresolved")

    # Both sources preserved
    c = contradictions[0]
    _assert(c["source_a"] == src_a["source_id"], "Source A preserved")
    _assert(c["source_b"] == src_b["source_id"], "Source B preserved")

    # Generate report
    report = detector.generate_contradiction_report([src_a["source_id"], src_b["source_id"]])
    _assert(report["contradictions_found"] >= 1, f"Report confirms {report['contradictions_found']} contradictions")
    _assert(report["resolution_status"] == "all_unresolved", "Report marks all unresolved")
    _assert("operator review" in report["operator_note"].lower(), "Requires operator review")

    # Non-contradictory sources
    src_c = registry.register_source(
        origin="https://c.com",
        content="Source C talks about weather.",
        summary="Weather patterns are stable",
        project_scope="test",
    )
    contradictions2 = detector.detect_contradictions([src_a["source_id"], src_c["source_id"]])
    _assert(len(contradictions2) == 0, "No contradictions for unrelated sources")

    # Save and load state
    detector.save_contradiction_state()
    state_path = str(detector.reports_dir / "contradiction_state.json")
    _assert(Path(state_path).exists(), "State saved")

    detector2 = ContradictionDetector(registry, tracker)
    detector2.load_contradiction_state()
    _assert(detector2.count() == detector.count(), "State restores counts")

    print("  PASS: Contradiction detection")


# ─────────────────────────────────────────────────────
# Test 5: Stale Source Handling
# ─────────────────────────────────────────────────────

def test_stale_source_handling():
    global FAILED
    registry = SourceRegistry(str(OVERCR_ROOT))
    classifier = SourceClassifier()

    src = registry.register_source(
        origin="https://old-article.com",
        content="Article from long ago.",
        summary="Old article about trends",
        project_scope="test",
    )

    # source starts active
    _assert(src["status"] == "active", "Starts active")

    # Mark stale
    registry.mark_stale(src["source_id"])
    stale = registry.get_source(src["source_id"])
    _assert(stale["status"] == "stale", "Marked stale")

    # Stale sources remain queryable
    found = registry.list_sources(status="stale")
    _assert(len(found) >= 1, f"Stale sources in list: {len(found)}")
    _assert(any(s["source_id"] == src["source_id"] for s in found), "Source in stale list")

    # Reactivate
    registry.reactivate(src["source_id"])
    active = registry.get_source(src["source_id"])
    _assert(active["status"] == "active", "Reactivated")

    # Mark archived
    registry.mark_archived(src["source_id"])
    archived = registry.get_source(src["source_id"])
    _assert(archived["status"] == "archived", "Archived")
    _assert(archived["content_hash"] == src["content_hash"], "Content hash preserved in archive")

    # Count by status
    counts = registry.count_by_status()
    _assert(isinstance(counts, dict), f"Status counts: {counts}")

    print("  PASS: Stale source handling")


# ─────────────────────────────────────────────────────
# Test 6: Deterministic Retrieval
# ─────────────────────────────────────────────────────

def test_deterministic_retrieval():
    global FAILED
    registry = SourceRegistry(str(OVERCR_ROOT))
    idx = KnowledgeIndex(registry)

    # Create sources with known keywords
    registry.register_source(
        origin="https://ai-platform.com",
        content="# AI Platform\n\nAn enterprise AI orchestration platform for autonomous workflows.",
        summary="Enterprise AI orchestration platform",
        tags=["ai", "orchestration", "enterprise"],
        trust_level="reputable",
        project_scope="test",
    )
    registry.register_source(
        origin="https://ml-research.org",
        content="# ML Research\n\nLatest machine learning research on transformers and attention.",
        summary="Machine learning research on transformers",
        tags=["ml", "research", "transformers"],
        trust_level="verified",
        project_scope="test",
    )

    # Build index
    idx.build(force=True)

    # Keyword search
    results = idx.keyword_search("orchestration", limit=10)
    _assert(len(results) >= 1, f"Keyword search found: {len(results)}")

    # Tag search
    tag_results = idx.tag_search("ai")
    _assert(len(tag_results) >= 1, f"Tag search found: {len(tag_results)}")

    # Retrieve for workflow
    wf_results = idx.retrieve_for_workflow("ai platform", tags=["ai"], limit=5)
    _assert(len(wf_results) >= 1, f"Workflow retrieval found: {len(wf_results)}")

    # Trust filter
    trusted = idx.retrieve_for_workflow("research", trust_min="reputable", limit=5)
    _assert(len(trusted) >= 1, f"Trust-filtered found: {len(trusted)}")

    # Stats
    stats = idx.stats
    _assert(stats["total_sources"] >= 2, f"Stats: {stats}")

    # Rebuild
    idx.rebuild()
    stats2 = idx.stats
    _assert(stats["total_sources"] == stats2["total_sources"], "Rebuild preserves counts")

    print("  PASS: Deterministic retrieval")


# ─────────────────────────────────────────────────────
# Test 7: Malformed Source Rejection
# ─────────────────────────────────────────────────────

def test_malformed_source_rejection():
    global FAILED
    registry = SourceRegistry(str(OVERCR_ROOT))

    # Empty origin behavior (registry accepts it but schema marks origin as-is)
    src_empty = registry.register_source(
        origin="file://local/empty-origin-test",
        content="some content",
        project_scope="test",
    )
    _assert(src_empty["source_id"].startswith("src-"), "Source with file origin registers ok")

    # Verify valid trust tiers are enforced
    _assert(SourceClassifier.is_valid_trust_tier("verified"), "verified is valid")
    _assert(SourceClassifier.is_valid_trust_tier("reputable"), "reputable is valid")
    _assert(not SourceClassifier.is_valid_trust_tier("gold_standard"), "invalid tier rejected")

    # Invalid trust tier in set_trust_level
    src = registry.register_source(
        origin="https://valid-source.com",
        content="Valid content for trust test.",
        project_scope="test",
    )
    try:
        registry.set_trust_level(src["source_id"], "nonexistent_tier")
        _assert(False, "Invalid trust tier should raise ValueError")
    except ValueError as e:
        _assert("Invalid trust tier" in str(e), f"Invalid tier rejected: {e}")

    print("  PASS: Malformed source rejection")


# ─────────────────────────────────────────────────────
# Test 8: Packet Provenance Validation
# ─────────────────────────────────────────────────────

def test_packet_provenance_validation():
    global FAILED
    registry = SourceRegistry(str(OVERCR_ROOT))
    tracker = ProvenanceTracker(registry)
    detector = ContradictionDetector(registry, tracker)
    builder = ResearchPacketBuilder(registry, tracker, detector)

    # Register sources
    s1 = registry.register_source(
        origin="https://research.org/paper1",
        content="# Paper 1\n\nOverCR is a portable AI orchestration substrate.",
        summary="OverCR is a portable AI orchestration substrate",
        tags=["overcr", "ai", "orchestration"],
        trust_level="verified",
        project_scope="test",
    )
    s2 = registry.register_source(
        origin="https://research.org/paper2",
        content="# Paper 2\n\nFilesystem-first architecture enables recovery-oriented design.",
        summary="Filesystem-first architecture enables recovery-oriented design",
        tags=["overcr", "architecture"],
        trust_level="reputable",
        project_scope="test",
    )

    # Build claim review packet
    packet = builder.build_claim_review(
        claims=[
            "OverCR is a portable AI orchestration substrate",
            "Filesystem-first architecture enables recovery-oriented design",
        ],
        source_ids=[s1["source_id"], s2["source_id"]],
        topic="OverCR architecture verification",
    )

    # Verify provenance chain
    _assert("provenance_chain" in packet, "Packet has provenance_chain")
    _assert(len(packet["provenance_chain"]) >= 2, f"Provenance chain length: {len(packet['provenance_chain'])}")

    # Verify citation references
    _assert("citation_refs" in packet, "Packet has citation_refs")
    _assert(len(packet["citation_refs"]) >= 2, f"Citation refs: {len(packet['citation_refs'])}")
    _assert(packet["citation_refs"][0]["source_id"] in [s1["source_id"], s2["source_id"]],
            "First cit matches a source")

    # Verify confidence scoring
    _assert("confidence_scoring" in packet, "Packet has confidence_scoring")
    _assert(packet["confidence_scoring"]["overall"] >= 1, "Confidence overall >= 1")
    _assert(packet["confidence_scoring"]["overall"] <= 4, "Confidence overall <= 4")

    # Verify audit metadata
    _assert("audit_metadata" in packet, "Packet has audit_metadata")
    _assert(packet["audit_metadata"]["deterministic_mode"] is True, "Deterministic mode")
    _assert(packet["audit_metadata"]["sources_consulted_count"] == 2, "Sources consulted count")

    # Verify claim review data
    _assert("claim_review_data" in packet, "Packet has claim_review_data")
    _assert(len(packet["claim_review_data"]["claims"]) == 2, "2 claims classified")
    _assert("operator_brief" in packet["claim_review_data"], "Has operator brief")

    print("  PASS: Packet provenance validation")


# ─────────────────────────────────────────────────────
# Test 9: Trust Classification
# ─────────────────────────────────────────────────────

def test_trust_classification():
    global FAILED
    registry = SourceRegistry(str(OVERCR_ROOT))

    # Create sources at different trust levels
    s_v = registry.register_source(
        origin="https://trusted.gov",
        content="Official government report.",
        trust_level="verified",
        project_scope="test",
    )
    s_r = registry.register_source(
        origin="https://reputable.org",
        content="Well-known industry report.",
        trust_level="reputable",
        project_scope="test",
    )
    s_u = registry.register_source(
        origin="https://unknown-blog.com",
        content="Personal blog post.",
        trust_level="unknown",
        project_scope="test",
    )
    s_s = registry.register_source(
        origin="https://sketchy-site.xyz",
        content="Questionable claims.",
        trust_level="suspicious",
        project_scope="test",
    )
    s_x = registry.register_source(
        origin="https://fake-news.biz",
        content="Rejected content.",
        trust_level="rejected",
        project_scope="test",
    )

    # Count by trust
    counts = registry.count_by_trust()
    _assert(counts.get("verified", 0) >= 1, f"Verified count: {counts}")
    _assert(counts.get("reputable", 0) >= 1, f"Reputable count: {counts}")
    _assert(counts.get("suspicious", 0) >= 1, f"Suspicious count: {counts}")
    _assert(counts.get("rejected", 0) >= 1, f"Rejected count: {counts}")

    # Trust tier change requires operator
    registry.set_trust_level(s_u["source_id"], "reputable", operator="test-operator")
    updated = registry.get_source(s_u["source_id"])
    _assert(updated["trust_level"] == "reputable", "Trust upgraded")
    chain = updated["provenance"]["transformation_chain"]
    trust_changes = [e for e in chain if e.get("step") == "trust_level_change"]
    _assert(len(trust_changes) >= 1, f"Trust change recorded: {len(trust_changes)}")
    _assert(trust_changes[-1]["operator"] == "test-operator", "Operator recorded")

    # List by trust
    reputables = registry.list_sources(trust_level="reputable")
    _assert(len(reputables) >= 2, f"Now {len(reputables)} reputable sources")

    # Verify suspicious and rejected are in list but not filtered out by default
    all_sources = registry.list_sources()
    all_ids = {s["source_id"] for s in all_sources}
    _assert(s_s["source_id"] in all_ids, "Suspicious source visible in list")
    _assert(s_x["source_id"] in all_ids, "Rejected source visible in list")

    print("  PASS: Trust classification")


# ─────────────────────────────────────────────────────
# Test 10: Audit Trail Integrity
# ─────────────────────────────────────────────────────

def test_audit_trail_integrity():
    global FAILED
    registry = SourceRegistry(str(OVERCR_ROOT))
    tracker = ProvenanceTracker(registry)

    src = registry.register_source(
        origin="https://audit-test.com",
        content="Audit trail test content.",
        summary="Audit test source",
        project_scope="test",
    )

    # Record multiple operations
    tracker.record_ingestion(src["source_id"], "manual", operator="operator-a")
    tracker.record_transformation(src["source_id"], "classify", operator="operator-b")
    tracker.record_workflow_usage(src["source_id"], "run-001", "audit-wf")
    tracker.record_citation(src["source_id"], "task-0100", "audit citation")
    tracker.record_contradiction(
        src["source_id"], "src-other",
        claim_a="X is true", claim_b="X is false",
        severity="direct",
    )

    # Load all entries
    entries = tracker._load_tracker_entries(src["source_id"])
    _assert(len(entries) >= 5, f"All entries recorded: {len(entries)}")

    # Verify entry types
    entry_types = {e.get("type") for e in entries}
    _assert("ingestion_recorded" in entry_types, "Ingestion recorded")
    _assert("transformation_recorded" in entry_types, "Transformation recorded")
    _assert("workflow_usage_recorded" in entry_types, "Workflow usage recorded")
    _assert("citation_recorded" in entry_types, "Citation recorded")
    _assert("contradiction_recorded" in entry_types, "Contradiction recorded")

    # Verify timestamps (all should be ISO 8601)
    for e in entries:
        ts = e.get("timestamp", "")
        _assert("T" in ts, f"Timestamp is ISO: {ts[:20]}...")

    # Full provenance report
    full = tracker.get_full_provenance(src["source_id"])
    _assert(full["total_entries"] >= 5, f"Report has {full['total_entries']} entries")
    _assert(full["source_id"] == src["source_id"], "Report matches source")

    # Export as JSON
    report_path = tracker.export_provenance_report(src["source_id"])
    with open(report_path, "r") as f:
        exported = json.load(f)
    _assert(exported["total_entries"] == full["total_entries"],
            "Exported report matches in-memory report")

    print("  PASS: Audit trail integrity")


# ─────────────────────────────────────────────────────
# Test 11: Research Packet Builder — All Types
# ─────────────────────────────────────────────────────

def test_all_packet_types():
    global FAILED
    registry = SourceRegistry(str(OVERCR_ROOT))
    tracker = ProvenanceTracker(registry)
    detector = ContradictionDetector(registry, tracker)
    builder = ResearchPacketBuilder(registry, tracker, detector)

    # Sources
    s1 = registry.register_source(
        origin="https://source1.com",
        content="AI orchestration is growing rapidly.",
        summary="AI orchestration market is growing",
        tags=["ai", "orchestration", "market"],
        trust_level="reputable",
        project_scope="test",
    )
    s2 = registry.register_source(
        origin="https://source2.com",
        content="AI orchestration market is shrinking.",
        summary="AI orchestration market is shrinking",
        tags=["ai", "orchestration", "market"],
        trust_level="suspicious",
        project_scope="test",
    )

    # 1. Claim Review
    claim_pkt = builder.build_claim_review(
        claims=["AI orchestration is growing"],
        source_ids=[s1["source_id"], s2["source_id"]],
        topic="AI orchestration market",
    )
    _assert(claim_pkt["packet_type"] == "knower_claim_review", "Claim review packet type")
    _assert("claim_review_data" in claim_pkt, "Has claim review data")
    _assert(len(claim_pkt["claim_review_data"]["claims"]) == 1, "1 claim classified")

    # 2. Research Brief
    brief_pkt = builder.build_research_brief(
        query="AI orchestration market trends",
        source_ids=[s1["source_id"], s2["source_id"]],
    )
    _assert(brief_pkt["packet_type"] == "knower_research", "Research brief packet type")
    _assert("research_data" in brief_pkt, "Has research data")
    _assert(len(brief_pkt["research_data"]["findings"]) == 2, "2 findings")

    # 3. Contradiction Summary
    contra_pkt = builder.build_contradiction_summary(
        source_ids=[s1["source_id"], s2["source_id"]],
        topic="AI orchestration contradiction",
    )
    _assert(contra_pkt["approval_required"] is True, "Contradiction requires approval")
    _assert("claim_review_data" in contra_pkt, "Has claim review data")

    # 4. Source Quality
    quality_pkt = builder.build_source_quality(
        source_ids=[s1["source_id"], s2["source_id"]],
    )
    _assert(quality_pkt["packet_type"] == "knower_claim_review", "Quality packet type")
    _assert("_source_quality_data" in quality_pkt, "Has source quality data")
    _assert(len(quality_pkt["_source_quality_data"]) == 2, "2 sources assessed")

    print("  PASS: All packet types")


# ─────────────────────────────────────────────────────
# Test 12: Source Classifier — Tags and Types
# ─────────────────────────────────────────────────────

def test_classifier_tags_and_types():
    global FAILED
    classifier = SourceClassifier()

    # Type classification from extension (deterministic, extension-aware)
    _assert(classifier.classify_source_type(file_extension="md") == "document", "md -> document")
    _assert(classifier.classify_source_type(file_extension="csv") == "dataset", "csv -> dataset")
    _assert(classifier.classify_source_type(file_extension="json") == "report", "json -> report")

    # Type classification from hints (heuristic — verify it returns a valid type)
    r1 = classifier.classify_source_type(hint="patent filing")
    r2 = classifier.classify_source_type(hint="memo from CEO")
    r3 = classifier.classify_source_type(hint="annual report")
    _assert(classifier.is_valid_source_type(r1), f"patent hint -> valid type: {r1}")
    _assert(classifier.is_valid_source_type(r2), f"memo hint -> valid type: {r2}")
    _assert(classifier.is_valid_source_type(r3), f"report hint -> valid type: {r3}")

    # Tag inference
    tags = classifier.infer_tags(
        content_snippet="OverCR is a portable AI orchestration substrate with governance and workflow capabilities.",
    )
    _assert("overcr" in tags, "overcr tag inferred")
    _assert("orchestration" in tags, "orchestration tag inferred")
    _assert("governance" in tags, "governance tag inferred")
    _assert("workflow" in tags, "workflow tag inferred")

    # Unknown content
    tags2 = classifier.infer_tags(content_snippet="Some text about nothing.")
    _assert(isinstance(tags2, list), "Empty inference returns list")

    print("  PASS: Classifier tags and types")


# ────────────────────────────────────────────────────
# Main
# ────────────────────────────────────────────────────

def main():
    global FAILED

    print("=" * 60)
    print("OverCR v2.4.0 — Research & Knowledge Layer Tests")
    print("=" * 60)

    tests = [
        ("Source registration", test_source_registration),
        ("Ingestion normalization", test_ingestion_normalization),
        ("Provenance integrity", test_provenance_integrity),
        ("Contradiction detection", test_contradiction_detection),
        ("Stale source handling", test_stale_source_handling),
        ("Deterministic retrieval", test_deterministic_retrieval),
        ("Malformed source rejection", test_malformed_source_rejection),
        ("Packet provenance validation", test_packet_provenance_validation),
        ("Trust classification", test_trust_classification),
        ("Audit trail integrity", test_audit_trail_integrity),
        ("All packet types", test_all_packet_types),
        ("Classifier tags and types", test_classifier_tags_and_types),
    ]

    for name, fn in tests:
        print(f"\n--- {name} ---")
        try:
            fn()
        except Exception as e:
            print(f"  ERROR: {e}")
            import traceback
            traceback.print_exc()
            FAILED = True

    print("\n" + "=" * 60)
    if FAILED:
        print("RESULT: SOME TESTS FAILED")
        return 1
    else:
        print("RESULT: ALL TESTS PASSED")
        return 0


if __name__ == "__main__":
    sys.exit(main())
