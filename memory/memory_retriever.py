"""
OverCR Semantic Memory — Memory Retriever v2.1.0

Retrieves semantic memory records by keyword, tag, project scope, and status.

Design principles:
  1. Filesystem-first — all reads come from disk, no in-memory cache
  2. Deterministic fallback — if structured filters return nothing, broaden
     the search progressively until results are found
  3. No embeddings required — retrieval is keyword/tag-based
  4. No RAG pipeline — this is a lookup service, not a generation service
  5. Auditable — every retrieval is traceable to specific file reads

Retrieval order (narrowest to broadest):
  1. Exact tag + project_scope + status=active
  2. Any tag match + project_scope + status=active
  3. project_scope + status=active (no tag filter)
  4. project_scope + any status
  5. text_query across all records (last resort)
"""

from pathlib import Path
from typing import Optional

from memory.memory_manager import MemoryManager
from memory.memory_record import MemoryRecord


class MemoryRetriever:
    """
    Keyword/tag-based retrieval for semantic memory with deterministic fallback.

    All retrieval hits disk. No embedding vectors. No similarity scoring.
    Retrieval results include canonical_state_refs to maintain the advisory
    nature of semantic memory — the consumer must verify against filesystem truth.
    """

    def __init__(self, manager: MemoryManager):
        """
        Args:
            manager: A MemoryManager instance for disk reads.
        """
        self.manager = manager

    def retrieve(
        self,
        tags: Optional[list[str]] = None,
        project_scope: Optional[str] = None,
        status: Optional[str] = None,
        source: Optional[str] = None,
        text_query: Optional[str] = None,
        deterministic_fallback: bool = True,
    ) -> list[MemoryRecord]:
        """
        Retrieve memory records with progressive fallback.

        If deterministic_fallback=True and no results are found with the
        given filters, the retriever progressively relaxes constraints
        following the defined order until results are found.

        Args:
            tags: Tags to filter by (AND — record must have ALL listed tags).
            project_scope: Exact match on project_scope.
            status: Filter by status. Default None = no status filter.
            source: Case-insensitive substring match on source.
            text_query: Case-insensitive substring match on semantic_summary.
            deterministic_fallback: If True, relax filters progressively.

        Returns:
            List of matching MemoryRecords, sorted by updated_at descending.
        """
        if not deterministic_fallback:
            return self.manager.search_memory(
                tags=tags,
                project_scope=project_scope,
                status=status,
                source=source,
                text_query=text_query,
            )

        # ── Deterministic fallback cascade ──

        # Level 1: All filters, active only
        results = self.manager.search_memory(
            tags=tags, project_scope=project_scope,
            status="active", source=source, text_query=text_query,
        )
        if results:
            return results

        # Level 2: Any tag match (OR) within scope, active only
        if tags:
            for tag in tags:
                results = self.manager.search_memory(
                    tags=[tag], project_scope=project_scope,
                    status="active", source=source,
                )
                if results:
                    return results

        # Level 3: Scope only, active
        if project_scope:
            results = self.manager.search_memory(
                project_scope=project_scope, status="active",
            )
            if results:
                return results

        # Level 4: Scope only, any status
        if project_scope:
            results = self.manager.search_memory(
                project_scope=project_scope,
            )
            if results:
                return results

        # Level 5: Text query across all (last resort)
        if text_query:
            results = self.manager.search_memory(text_query=text_query)
            if results:
                return results

        # Level 6: Broadest — all active
        results = self.manager.search_memory(status="active")
        return results

    def retrieve_by_id(self, memory_id: str) -> Optional[MemoryRecord]:
        """
        Retrieve a single memory record by ID.

        Returns:
            The MemoryRecord, or None if not found.
        """
        try:
            return self.manager.load_memory(memory_id)
        except FileNotFoundError:
            return None

    def retrieve_active_for_project(
        self,
        project_scope: str,
        tags: Optional[list[str]] = None,
    ) -> list[MemoryRecord]:
        """
        Convenience: retrieve all active memories for a project scope.

        Args:
            project_scope: The project to filter by.
            tags: Optional additional tag filter.

        Returns:
            List of active MemoryRecords for this project.
        """
        return self.manager.search_memory(
            project_scope=project_scope,
            status="active",
            tags=tags,
        )

    def retrieve_with_state_refs(
        self,
        project_scope: str,
        canonical_path: str,
    ) -> list[MemoryRecord]:
        """
        Retrieve memories that reference a specific canonical state file.

        This is the filesystem-first retrieval path: find memories whose
        canonical_state_refs point to a given path. The consumer MUST verify
        these refs against actual filesystem state before acting on them.

        Args:
            project_scope: The project scope to search within.
            canonical_path: The filesystem path to match against.

        Returns:
            List of MemoryRecords with canonical_state_refs matching the path.
        """
        candidates = self.manager.search_memory(
            project_scope=project_scope,
            status="active",
        )
        results = []
        for record in candidates:
            for ref in record.canonical_state_refs:
                if ref.get("path") == canonical_path:
                    results.append(record)
                    break
        return results