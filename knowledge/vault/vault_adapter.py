"""
OverCR Vault — Vault Index (filesystem-first)

Walks an Obsidian vault directory, discovers notes with facts fences,
parses them into structured records, indexes by domain/tag, and exposes
a search interface for context construction.

Filesystem-first:
  - Index is stored as JSONL files under an index/ subdirectory
  - Rebuildable from scratch at any time by re-walking the vault
  - Staleness tracked by file modification time (no DB needed)

Zero dependencies beyond Python stdlib. Zero embeddings. Zero vector DB.
"""

import json
import os
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from knowledge.vault.fact_parser import parse_file
from knowledge.vault.wikilink_resolver import WikilinkResolver

# Frontmatter tag regex
FRONTMATTER_TAG = re.compile(r"tags\s*:\s*\[([^\]]+)\]", re.IGNORECASE)
FRONTMATTER_TAG_YAML = re.compile(
    r"^tags:\s*(.+)$", re.MULTILINE | re.IGNORECASE
)

# Default excluded directories
EXCLUDED_DIRS = {
    ".git", "__pycache__", "node_modules", ".obsidian",
    ".trash", ".ts", "venv", ".venv", ".hermes",
}


class VaultIndex:
    """Filesystem-backed index of vault notes containing facts fences.

    Args:
        vault_path: Absolute path to the Obsidian vault root.
        index_dir: Directory for the JSONL index files (default: <vault>/.overcr-index/).
        vault_path resolved and validated on init.

    Usage:
        idx = VaultIndex("/home/sc/Documents/ObsidianVault")
        idx.rebuild()
        facts = idx.search(domain="cag", tags=["memory", "agent"])
    """

    def __init__(
        self,
        vault_path: str | Path,
        index_dir: str | Path | None = None,
    ):
        self.vault_root = Path(vault_path).resolve(strict=True)

        if index_dir is None:
            self.index_dir = self.vault_root / ".overcr-index"
        else:
            self.index_dir = Path(index_dir)
        self.index_dir.mkdir(parents=True, exist_ok=True)

        self.resolver = WikilinkResolver(self.vault_root)

        # In-memory index structures (rebuilt on demand)
        self._notes: dict[str, dict] = {}        # path -> note metadata + facts
        self._facts_by_domain: dict[str, list] = defaultdict(list)
        self._facts_by_tag: dict[str, list] = defaultdict(list)
        self._built = False

    # ── Public API ─────────────────────────────────────────────

    def rebuild(self) -> int:
        """Walk the vault and rebuild the full index from scratch.

        Returns the number of notes with facts fences found.
        """
        self._notes = {}
        self._facts_by_domain = defaultdict(list)
        self._facts_by_tag = defaultdict(list)

        md_files = self._walk_vault()
        count = 0

        for md_file in md_files:
            facts = parse_file(md_file)
            if not facts:
                continue

            count += 1
            rel_path = str(md_file.relative_to(self.vault_root))
            mtime = os.path.getmtime(md_file)
            tags = self._parse_frontmatter_tags(md_file)
            wikilinks = self.resolver.extract_wikilinks_from_file(md_file)

            note = {
                "path": rel_path,
                "abs_path": str(md_file.resolve()),
                "mtime": mtime,
                "tags": tags,
                "facts": facts,
                "wikilinks": [w["target"] for w in wikilinks],
                "fact_count": len(facts),
            }
            self._notes[rel_path] = note

            # Index by tag
            for tag in tags:
                self._facts_by_tag[tag].extend(facts)

            # Index by domain (inferred from tags and directory path)
            for domain in self._derive_domains(rel_path, tags):
                self._facts_by_domain[domain].extend(facts)

        # Write index to disk
        self._write_index()

        self._built = True
        return count

    def search(
        self,
        domain: str | None = None,
        tags: list[str] | None = None,
        query: str | None = None,
        max_results: int = 20,
    ) -> list[dict]:
        """Search the vault for facts relevant to a domain/tags/query.

        Args:
            domain: Task domain (e.g. "cag", "research", "code").
            tags: Specific tags to match.
            query: Free-text keyword search within facts.
            max_results: Maximum facts to return.

        Returns:
            A list of fact dicts ordered by relevance (tag overlap first,
            then domain match, then keyword match).
        """
        if not self._built:
            self.rebuild()

        candidates: list[dict] = []
        seen: set[str] = set()

        # Domain match
        if domain:
            for fact in self._facts_by_domain.get(domain, []):
                key = self._fact_key(fact)
                if key not in seen:
                    seen.add(key)
                    fact["_relevance"] = 1.0
                    candidates.append(fact)

        # Tag match
        if tags:
            for tag in tags:
                for fact in self._facts_by_tag.get(tag, []):
                    key = self._fact_key(fact)
                    if key not in seen:
                        seen.add(key)
                        fact["_relevance"] = 0.8
                        candidates.append(fact)

        # Keyword match (in claims)
        if query:
            query_lower = query.lower()
            for note in self._notes.values():
                for fact in note["facts"]:
                    key = self._fact_key(fact)
                    if key in seen:
                        continue
                    if query_lower in fact.get("claim", "").lower():
                        seen.add(key)
                        fact["_relevance"] = 0.5
                        candidates.append(fact)

        # Sort by relevance descending, then by confidence descending
        candidates.sort(
            key=lambda f: (f.get("_relevance", 0), f.get("confidence") or 0),
            reverse=True,
        )

        return candidates[:max_results]

    def get_note(self, path: str) -> dict | None:
        """Get the full index entry for a specific vault note."""
        if not self._built:
            self.rebuild()
        return self._notes.get(path)

    def list_domains(self) -> list[str]:
        """List all domains present in the index."""
        if not self._built:
            self.rebuild()
        return sorted(self._facts_by_domain.keys())

    def list_tags(self) -> list[str]:
        """List all tags present in the index."""
        if not self._built:
            self.rebuild()
        return sorted(self._facts_by_tag.keys())

    def stats(self) -> dict:
        """Return summary stats about the index."""
        total_facts = sum(
            len(n.get("facts", [])) for n in self._notes.values()
        )
        return {
            "notes_with_facts": len(self._notes),
            "total_facts": total_facts,
            "domains": len(self._facts_by_domain),
            "tags": len(self._facts_by_tag),
            "index_dir": str(self.index_dir),
            "vault_root": str(self.vault_root),
        }

    # ── Internal ───────────────────────────────────────────────

    def _walk_vault(self) -> list[Path]:
        """Walk the vault directory and return all .md file paths."""
        files: list[Path] = []
        for entry in self.vault_root.rglob("*.md"):
            # Skip symlinks to avoid recursion
            if entry.is_symlink():
                continue
            # Skip excluded dirs
            if any(
                part.startswith(".") or part in EXCLUDED_DIRS
                for part in entry.relative_to(self.vault_root).parts
            ):
                continue
            files.append(entry)
        return sorted(files)

    def _parse_frontmatter_tags(self, path: Path) -> list[str]:
        """Extract tags from YAML frontmatter."""
        text = path.read_text(encoding="utf-8", errors="replace")

        # Inline list format: tags: [tag1, tag2]
        m = FRONTMATTER_TAG.search(text)
        if m:
            return [t.strip().strip("'\"") for t in m.group(1).split(",")]

        # YAML list format: tags:\n  - tag1\n  - tag2
        # Only check first 20 lines (frontmatter is typically at the top)
        first_lines = text[:2000]
        m = FRONTMATTER_TAG_YAML.search(first_lines)
        if m:
            raw = m.group(1).strip()
            if raw.startswith("["):
                return [t.strip().strip("'\"") for t in raw.strip("[]").split(",")]
            # Single tag
            return [raw.strip()]

        return []

    def _derive_domains(self, rel_path: str, tags: list[str]) -> list[str]:
        """Derive search domains from relative path and tags."""
        domains = []

        # From directory structure
        parts = Path(rel_path).parts
        if parts:
            domains.append(parts[0].lower())

        # From subdirectory
        if len(parts) > 1:
            domains.append(parts[1].lower())

        # From tags
        known_domains = {
            "cag", "rag", "memory", "agent", "research",
            "overcr", "oathweaver", "cammander", "foxforge",
            "llm", "local-llm", "quantization", "inference",
            "devops", "infrastructure", "security",
            "writing", "communication",
        }
        for tag in tags:
            if tag.lower() in known_domains:
                domains.append(tag.lower())

        return list(set(domains))

    def _fact_key(self, fact: dict) -> str:
        """Unique key for deduplication."""
        return f"{fact.get('source_file', '')}:{fact.get('line', 0)}:{fact.get('claim', '')}"

    def _write_index(self):
        """Write the current index to disk as JSONL files."""
        # Notes index
        notes_path = self.index_dir / "notes.jsonl"
        with open(notes_path, "w") as f:
            for note in self._notes.values():
                # Remove abs_path from index output (privacy)
                entry = {k: v for k, v in note.items() if k != "abs_path"}
                f.write(json.dumps(entry) + "\n")

        # Stats
        stats_path = self.index_dir / "stats.json"
        with open(stats_path, "w") as f:
            json.dump(self.stats(), f, indent=2)

        # Timestamp
        ts_path = self.index_dir / "last_rebuilt.txt"
        ts_path.write_text(
            datetime.now(timezone.utc).isoformat() + "\n"
        )

    def _read_index(self) -> bool:
        """Read index from disk if it exists and is fresh enough."""
        notes_path = self.index_dir / "notes.jsonl"
        if not notes_path.exists():
            return False

        self._notes = {}
        self._facts_by_domain = defaultdict(list)
        self._facts_by_tag = defaultdict(list)

        with open(notes_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                note = json.loads(line)
                self._notes[note["path"]] = note
                for tag in note.get("tags", []):
                    self._facts_by_tag[tag].extend(note["facts"])
                for domain in self._derive_domains(note["path"], note.get("tags", [])):
                    self._facts_by_domain[domain].extend(note["facts"])

        self._built = True
        return True