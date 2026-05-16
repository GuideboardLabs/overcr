"""
OverCR v2.4.0 — Knowledge Index

Deterministic, filesystem-first keyword and tag index for the
knowledge subsystem. No vector DB, no embeddings, no database
— just structured JSON indexes on disk.

Index types:
  - Keyword index: word → source_ids
  - Tag index: tag → source_ids
  - Source link index: source_id → linked sources
  - Canonical state index: tracks canonical links between sources

All indexes are rebuildable from source records. No stale data
can outlive its source.
"""

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Optional

from knowledge.source_registry import SourceRegistry


class KnowledgeIndex:
    """
    Keyword, tag, and link index backed by JSON files on disk.

    Deterministic: given the same source records, the same index is
    produced. Rebuildable from scratch at any time.
    """

    def __init__(self, registry: SourceRegistry):
        self.registry = registry
        self.index_dir = self.registry.root / "knowledge" / "reports"
        self.index_dir.mkdir(parents=True, exist_ok=True)

        # In-memory index structures
        self._keyword_index: dict[str, set[str]] = defaultdict(set)
        self._tag_index: dict[str, set[str]] = defaultdict(set)
        self._source_links: dict[str, set[str]] = defaultdict(set)
        self._canonical_links: dict[str, set[str]] = defaultdict(set)

        self._built = False

    # ── Build ──────────────────────────────────────────

    def build(self, force: bool = False):
        """
        Build all indexes from source records.

        Args:
            force: Rebuild even if already built.
        """
        if self._built and not force:
            return

        self.registry.load_all()

        # Clear existing
        self._keyword_index.clear()
        self._tag_index.clear()
        self._source_links.clear()
        self._canonical_links.clear()

        # Iterate all sources
        for fpath in sorted(self.registry.sources_dir.glob("*.json")):
            try:
                with open(fpath, "r") as f:
                    record = json.load(f)
            except json.JSONDecodeError:
                continue

            sid = record.get("source_id", "")
            if not sid:
                continue

            # Tag index
            for tag in record.get("tags", []):
                self._tag_index[tag.lower()].add(sid)

            # Keyword index from summary and origin
            text = (record.get("summary", "") + " " + record.get("origin", "")).lower()
            words = set(re.findall(r'[a-z][a-z0-9_-]{2,}', text))
            for word in words:
                self._keyword_index[word].add(sid)

            # Canonical links
            for ref in record.get("provenance", {}).get("canonical_refs", []):
                if ref.startswith("src-"):
                    self._canonical_links[sid].add(ref)
                    self._canonical_links[ref].add(sid)

        # Persist to disk
        self._persist_index("keyword_index.json", self._keyword_index)
        self._persist_index("tag_index.json", self._tag_index)

        self._built = True

    def _persist_index(self, filename: str, index: dict):
        """Write an index to disk as JSON."""
        path = self.index_dir / filename
        serialized = {k: sorted(v) for k, v in index.items()}
        with open(path, "w") as f:
            json.dump(serialized, f, indent=2)

    def _load_index(self, filename: str) -> dict:
        """Load an index from disk."""
        path = self.index_dir / filename
        if path.exists():
            with open(path, "r") as f:
                raw = json.load(f)
            return {k: set(v) for k, v in raw.items()}
        return {}

    # ── Keyword search ─────────────────────────────────

    def keyword_search(self, query: str, limit: int = 20) -> list[str]:
        """
        Search sources by keyword.

        Args:
            query: One or more space-separated keywords
            limit: Max results

        Returns:
            List of source_ids, ranked by match count.
        """
        if not self._built:
            self.build()

        keywords = [w.lower() for w in query.split() if len(w) >= 2]
        if not keywords:
            return []

        # Collect matching source_ids with scores
        scores: dict[str, int] = defaultdict(int)
        for kw in keywords:
            matched = self._keyword_index.get(kw, set())
            for sid in matched:
                scores[sid] += 1

        # Also search tags
        tag_query = query.lower().replace(" ", "-")
        for tag, sids in self._tag_index.items():
            if tag_query in tag or any(kw in tag for kw in keywords):
                for sid in sids:
                    scores[sid] += 2  # Tag matches weighted higher

        # Rank by score, then alphabetically
        ranked = sorted(scores.items(), key=lambda x: (-x[1], x[0]))
        return [sid for sid, _ in ranked[:limit]]

    def tag_search(self, tag: str) -> list[str]:
        """Find all sources with a given tag."""
        if not self._built:
            self.build()

        return sorted(self._tag_index.get(tag.lower(), set()))

    # ── Source linking ─────────────────────────────────

    def link_sources(self, source_a: str, source_b: str, link_type: str = "reference"):
        """
        Create a directional link between two sources.

        Links are advisory — they don't change trust tiers.
        """
        record_a = self.registry.get_source(source_a)
        record_b = self.registry.get_source(source_b)

        if not record_a or not record_b:
            return

        self._source_links[source_a].add(source_b)

        # Update the source record with the link
        chain = record_a.get("provenance", {}).get("transformation_chain", [])
        chain.append({
            "step": "source_link",
            "timestamp": __import__("datetime").datetime.now(
                __import__("datetime").timezone.utc
            ).isoformat(),
            "operator": "system",
            "details": f"Linked to {source_b} ({link_type})",
        })

        # Persist
        path = self.registry.sources_dir / f"{source_a}.json"
        with open(path, "w") as f:
            json.dump(record_a, f, indent=2)

    def get_linked_sources(self, source_id: str) -> list[str]:
        """Get sources linked from/to a given source."""
        if not self._built:
            self.build()

        return sorted(self._source_links.get(source_id, set()))

    def get_canonical_links(self, source_id: str) -> list[str]:
        """Get canonical (bidirectional) links."""
        if not self._built:
            self.build()

        return sorted(self._canonical_links.get(source_id, set()))

    # ── Deterministic retrieval ───────────────────────

    def retrieve_for_workflow(
        self,
        query: str,
        tags: Optional[list] = None,
        trust_min: str = "unknown",
        limit: int = 10,
    ) -> list[dict]:
        """
        Retrieve sources matching query, tags, and trust threshold.

        This is the primary retrieval entry point for workflow nodes.
        All results include source_id, summary, and trust_level.

        Args:
            query: Keyword search query
            tags: Optional tag filters (all must match)
            trust_min: Minimum trust tier to include
            limit: Max results

        Returns:
            List of source summary dicts.
        """
        # Get keyword matches
        source_ids = self.keyword_search(query, limit=limit * 2)

        # Filter by tags
        if tags:
            tag_matches = set()
            for tag in tags:
                tag_matches.update(self.tag_search(tag))
            source_ids = [s for s in source_ids if s in tag_matches]

        # Filter by trust tier
        trust_ranks = {"verified": 4, "reputable": 3, "unknown": 2, "suspicious": 1, "rejected": 0}
        min_rank = trust_ranks.get(trust_min, 0)

        results = []
        for sid in source_ids:
            rec = self.registry.get_source(sid)
            if not rec:
                continue
            tier = rec.get("trust_level", "unknown")
            if trust_ranks.get(tier, 0) >= min_rank:
                results.append({
                    "source_id": sid,
                    "summary": rec.get("summary", ""),
                    "trust_level": tier,
                    "source_type": rec.get("source_type", ""),
                    "tags": rec.get("tags", []),
                })

        return results[:limit]

    # ── Maintenance ───────────────────────────────────

    def rebuild(self):
        """Force-rebuild all indexes from scratch."""
        self.build(force=True)

    @property
    def stats(self) -> dict:
        """Return index statistics."""
        if not self._built:
            self.build()
        return {
            "keyword_terms": len(self._keyword_index),
            "tags": len(self._tag_index),
            "total_sources": self.registry.count(),
            "source_links": sum(len(v) for v in self._source_links.values()),
        }
