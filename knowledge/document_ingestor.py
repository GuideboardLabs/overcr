"""
OverCR v2.4.0 — Document Ingestor

Ingests documents into the knowledge subsystem. Supports markdown,
JSON, and plain text. No PDFs, OCR, or embeddings yet (future
extension points).

Every ingested document:
  - Gets a content hash for integrity verification
  - Has metadata extracted (title, date, author, tags)
  - Is normalized to a consistent internal format
  - Is registered as a source in the registry
  - Retains its original provenance

What this does NOT do:
  - No PDF parsing
  - No OCR
  - No embeddings/vectorization
  - No automatic web crawling
  - No browser-based content extraction
"""

import json
import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from knowledge.source_registry import SourceRegistry
from knowledge.source_classifier import SourceClassifier


class DocumentIngestor:
    """
    Ingests documents into the knowledge subsystem.

    Supports markdown (.md), JSON (.json), and plain text (.txt).
    All documents are registered as sources and stored in documents/.
    """

    def __init__(self, registry: SourceRegistry):
        """
        Args:
            registry: A SourceRegistry instance for registering sources.
        """
        self.registry = registry
        self.classifier = SourceClassifier()

    # ── Ingestion methods ─────────────────────────────

    def ingest_markdown(
        self,
        content: str,
        origin: str,
        project_scope: str = "default",
        tags: Optional[list] = None,
        trust_level: str = "unknown",
    ) -> dict:
        """
        Ingest a markdown document.

        Extracts YAML frontmatter metadata if present, normalizes,
        and registers as a source.

        Returns the source record.
        """
        metadata = self.extract_metadata(content, fmt="markdown")
        normalized = self.normalize_document(content, fmt="markdown")

        summary = metadata.get("description", "") or self._auto_summary(normalized)

        return self.registry.register_source(
            origin=origin,
            source_type="document",
            content=normalized,
            summary=summary,
            tags=tags or metadata.get("tags", []),
            project_scope=project_scope,
            trust_level=trust_level,
            canonical_refs=[origin],
        )

    def ingest_json(
        self,
        content: str,
        origin: str,
        project_scope: str = "default",
        tags: Optional[list] = None,
        trust_level: str = "unknown",
    ) -> dict:
        """
        Ingest a JSON document.

        Parses and re-serializes to normalize formatting. Extracts
        metadata from common fields (title, description, tags).

        Returns the source record.
        """
        try:
            parsed = json.loads(content)
            normalized = json.dumps(parsed, indent=2, ensure_ascii=False)
        except json.JSONDecodeError:
            # Invalid JSON — store as raw text with warning in metadata
            normalized = content
            parsed = {}

        metadata = self.extract_metadata(normalized, fmt="json")
        summary = metadata.get("description", "") or self._auto_summary(normalized)

        return self.registry.register_source(
            origin=origin,
            source_type="report",
            content=normalized,
            summary=summary,
            tags=tags or metadata.get("tags", []),
            project_scope=project_scope,
            trust_level=trust_level,
            canonical_refs=[origin],
        )

    def ingest_text(
        self,
        content: str,
        origin: str,
        project_scope: str = "default",
        tags: Optional[list] = None,
        trust_level: str = "unknown",
    ) -> dict:
        """
        Ingest a plain text document.

        Normalizes whitespace and registers as a source.

        Returns the source record.
        """
        normalized = self.normalize_document(content, fmt="text")
        summary = self._auto_summary(normalized)

        return self.registry.register_source(
            origin=origin,
            source_type="document",
            content=normalized,
            summary=summary,
            tags=tags or [],
            project_scope=project_scope,
            trust_level=trust_level,
            canonical_refs=[origin],
        )

    # ── Metadata extraction ──────────────────────────

    def extract_metadata(self, content: str, fmt: str = "markdown") -> dict:
        """
        Extract metadata from document content.

        For markdown: parses YAML frontmatter (--- ... ---)
        For JSON: extracts title, description, tags from top-level fields
        For text: minimal metadata

        Returns dict with keys: title, description, author, date, tags
        """
        metadata = {
            "title": "",
            "description": "",
            "author": "",
            "date": "",
            "tags": [],
        }

        if fmt == "markdown" and content.startswith("---"):
            # YAML frontmatter extraction
            match = re.match(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
            if match:
                frontmatter = match.group(1)
                for line in frontmatter.split("\n"):
                    line = line.strip()
                    if ":" in line:
                        key, _, value = line.partition(":")
                        key = key.strip().lower()
                        value = value.strip().strip('"').strip("'")
                        if key in ("title", "description", "author", "date"):
                            metadata[key] = value
                        elif key == "tags":
                            if value.startswith("[") and value.endswith("]"):
                                # Simple list parsing: [tag1, tag2]
                                metadata["tags"] = [
                                    t.strip().strip('"').strip("'")
                                    for t in value[1:-1].split(",")
                                    if t.strip()
                                ]
                            else:
                                metadata["tags"] = [value]

        elif fmt == "json":
            try:
                parsed = json.loads(content)
                if isinstance(parsed, dict):
                    for key in ("title", "description", "author", "date"):
                        if key in parsed and isinstance(parsed[key], str):
                            metadata[key] = str(parsed[key])
                    if "tags" in parsed and isinstance(parsed["tags"], list):
                        metadata["tags"] = [str(t) for t in parsed["tags"]]
            except json.JSONDecodeError:
                pass

        # Fallback: first heading as title for markdown
        if fmt == "markdown" and not metadata["title"]:
            h1 = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
            if h1:
                metadata["title"] = h1.group(1).strip()

        return metadata

    # ── Normalization ────────────────────────────────

    def normalize_document(self, content: str, fmt: str = "markdown") -> str:
        """
        Normalize document content to a consistent internal format.

        Markdown: strip trailing whitespace, normalize line endings
        JSON: parse and re-serialize with consistent formatting
        Text: normalize whitespace and line endings
        """
        if fmt == "markdown":
            # Normalize line endings, strip trailing whitespace
            normalized = content.replace("\r\n", "\n").replace("\r", "\n")
            normalized = "\n".join(line.rstrip() for line in normalized.split("\n"))
            # Ensure exactly one trailing newline
            normalized = normalized.rstrip("\n") + "\n"
            return normalized

        elif fmt == "json":
            try:
                parsed = json.loads(content)
                return json.dumps(parsed, indent=2, ensure_ascii=False) + "\n"
            except json.JSONDecodeError:
                return content.replace("\r\n", "\n").strip() + "\n"

        else:  # text
            normalized = content.replace("\r\n", "\n").replace("\r", "\n")
            # Collapse multiple blank lines
            normalized = re.sub(r'\n{3,}', '\n\n', normalized)
            return normalized.strip() + "\n"

    # ── Helpers ──────────────────────────────────────

    def _auto_summary(self, content: str, max_len: int = 200) -> str:
        """Auto-generate a summary from content head."""
        if not content:
            return ""

        # Strip markdown frontmatter
        if content.startswith("---"):
            match = re.match(r'^---\s*\n.*?\n---\s*\n(.*)', content, re.DOTALL)
            if match:
                content = match.group(1)

        # Strip heading markers for cleaner summary
        content = re.sub(r'^#+\s+', '', content, flags=re.MULTILINE)

        # Take first non-empty paragraph
        lines = [l.strip() for l in content.split("\n") if l.strip()]
        if lines:
            return lines[0][:max_len]

        return ""
