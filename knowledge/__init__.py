"""
OverCR v2.4.0 — Research & Knowledge Layer

A governed research and knowledge subsystem capable of document
ingestion, source tracking, provenance-aware analysis, contradiction
detection, and structured research packet generation.

This release is about trusted knowledge operations, not unrestricted
web crawling or autonomous intelligence gathering. Every output is
attributable, auditable, replayable, provenance-aware, and
operator-reviewable.

Exports:
  - SourceRegistry: source registration, classification, trust management
  - SourceClassifier: trust tier and type classification
  - DocumentIngestor: markdown, JSON, text ingestion
  - KnowledgeIndex: keyword, tag, and source-link indexing
  - ProvenanceTracker: full lineage tracking
  - ContradictionDetector: conflict detection (never auto-resolves)
  - ResearchPacketBuilder: structured packet generation with provenance
"""

from knowledge.source_registry import SourceRegistry, SourceRecordExistsError, SourceNotFoundError
from knowledge.source_classifier import SourceClassifier, VALID_TRUST_TIERS
from knowledge.document_ingestor import DocumentIngestor
from knowledge.knowledge_index import KnowledgeIndex
from knowledge.provenance_tracker import ProvenanceTracker
from knowledge.contradiction_detector import ContradictionDetector
from knowledge.research_packet_builder import ResearchPacketBuilder

__all__ = [
    "SourceRegistry",
    "SourceRecordExistsError",
    "SourceNotFoundError",
    "SourceClassifier",
    "VALID_TRUST_TIERS",
    "DocumentIngestor",
    "KnowledgeIndex",
    "ProvenanceTracker",
    "ContradictionDetector",
    "ResearchPacketBuilder",
]

__version__ = "2.4.0"
