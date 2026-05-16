"""
OverCR v2.4.0 — Source Classifier

Classifies sources into trust tiers, types, and categories. Trust
tiers are operator-assigned and NEVER auto-escalated. Classification
is advisory — routing and confidence use it, but it never becomes
authoritative truth automatically.

Trust tiers:
  - verified:   Confirmed by operator or trusted authority
  - reputable:  From a known-reliable source (secondary verification done)
  - unknown:    No provenance or cannot verify
  - suspicious: Indicators of bias, contradiction, or low quality
  - rejected:   Explicitly rejected by operator (still retained, never deleted)
"""

from datetime import datetime, timezone
from typing import Optional


VALID_TRUST_TIERS = ("verified", "reputable", "unknown", "suspicious", "rejected")
VALID_SOURCE_TYPES = (
    "document", "report", "article", "website", "dataset",
    "transcript", "memo", "reference", "manual", "legal",
    "patent", "standard", "other",
)
VALID_STATUSES = ("active", "stale", "archived")


class SourceClassifier:
    """
    Classifies sources but never escalates trust automatically.
    Trust tier changes require explicit operator action.
    """

    @staticmethod
    def classify_trust_tier(
        origin: str = "",
        content_snippet: str = "",
        operator_assignment: Optional[str] = None,
    ) -> str:
        """
        Determine initial trust tier for a new source.

        Args:
            origin: Where the source came from (URL, path, citation)
            content_snippet: First ~500 chars for heuristic analysis
            operator_assignment: If the operator explicitly set a tier

        Returns:
            One of: verified, reputable, unknown, suspicious, rejected
        """
        # Operator assignment always wins
        if operator_assignment and operator_assignment in VALID_TRUST_TIERS:
            return operator_assignment

        # Default: unknown (no provenance to establish trust)
        return "unknown"

    @staticmethod
    def classify_source_type(hint: str = "", file_extension: str = "") -> str:
        """
        Heuristic source type classification.

        Args:
            hint: Description or filename
            file_extension: File extension if available
        """
        ext = file_extension.lower().lstrip(".")
        hint_lower = hint.lower()

        if ext in ("md", "markdown", "txt"):
            return "document"
        if ext in ("pdf"):
            return "document"
        if ext in ("csv", "xlsx", "jsonl", "tsv"):
            return "dataset"
        if ext in ("json"):
            return "report"
        if "transcript" in hint_lower:
            return "transcript"
        if any(w in hint_lower for w in ("patent", "legal", "law")):
            return "patent"
        if any(w in hint_lower for w in ("standard", "iso ", "ieee", "rfc")):
            return "standard"
        if any(w in hint_lower for w in ("memo", "note", "internal")):
            return "memo"
        if any(w in hint_lower for w in ("report", "brief", "analysis")):
            return "report"
        if any(w in hint_lower for w in ("article", "blog", "news", "press")):
            return "article"
        if any(w in hint_lower for w in ("reference", "manual", "guide", "docs")):
            return "reference"

        return "other"

    @staticmethod
    def infer_tags(content_snippet: str = "", origin: str = "", existing_tags: Optional[list] = None) -> list[str]:
        """
        Heuristic tag inference from content.

        Never auto-tags from unverified content — tags are search hints,
        not authoritative classifications.
        """
        tags = existing_tags or []
        if not content_snippet:
            return tags

        content_lower = content_snippet.lower()

        # Simple keyword-based tag hints
        keyword_map = {
            "overcr": "overcr",
            "ai": "ai",
            "orchestration": "orchestration",
            "governance": "governance",
            "memory": "memory",
            "workflow": "workflow",
            "subagent": "subagent",
            "research": "research",
            "knowledge": "knowledge",
            "provenance": "provenance",
            "validation": "validation",
            "security": "security",
            "architecture": "architecture",
            "crm": "crm",
            "outreach": "outreach",
            "business": "business",
            "lead": "lead-generation",
        }

        for keyword, tag in keyword_map.items():
            if keyword in content_lower and tag not in tags:
                tags.append(tag)

        # Deduplicate and sort
        return sorted(set(tags))

    @staticmethod
    def should_mark_stale(
        source_age_days: float,
        trust_tier: str = "unknown",
        last_cited_days: float = 365,
    ) -> bool:
        """
        Determine if a source should be flagged as stale.

        Staleness is advisory — sources are never auto-archived.
        """
        # Sources older than 365 days with no recent citations
        if source_age_days > 365 and last_cited_days > 180:
            return True

        # Suspicious/rejected sources with no recent use
        if trust_tier in ("suspicious", "rejected") and last_cited_days > 90:
            return True

        return False

    @staticmethod
    def is_valid_trust_tier(tier: str) -> bool:
        return tier in VALID_TRUST_TIERS

    @staticmethod
    def is_valid_source_type(stype: str) -> bool:
        return stype in VALID_SOURCE_TYPES

    @staticmethod
    def is_valid_status(status: str) -> bool:
        return status in VALID_STATUSES
