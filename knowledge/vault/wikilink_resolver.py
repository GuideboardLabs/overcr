"""
OverCR Vault — Wikilink Resolver

Resolves Obsidian-style [[wikilinks]] to filesystem paths within the vault.
Builds an adjacency list for graph walking.

Supports:
  - [[Note Name]] -> find Note Name.md
  - [[note-name]] -> find note-name.md (kebab-case)
  - [[path/to/note]] -> resolve relative to vault root
  - [[Note|Display Text]] -> strip display text, resolve Note
  - #tag references

All resolution is filesystem-native. No database.
"""

import re
from pathlib import Path
from typing import Optional

WIKILINK_PATTERN = re.compile(r"\[\[([^\[\]]+?)(?:\|([^\[\]]*?))?\]\]")
TAG_PATTERN = re.compile(r"(?<!\w)#([a-zA-Z][a-zA-Z0-9_-]*)")


class WikilinkResolver:
    """Resolves [[wikilinks]] to filesystem paths within a vault.

    Args:
        vault_root: Absolute path to the Obsidian vault root directory.
    """

    def __init__(self, vault_root: str | Path):
        self.vault_root = Path(vault_root).resolve(strict=True)

    # ── Extraction ────────────────────────────────────────────

    def extract_wikilinks(self, text: str) -> list[dict]:
        """Extract all [[wikilinks]] from a text string.

        Returns:
            List of dicts: {raw, target, display, resolved_path}
        """
        links = []
        for m in WIKILINK_PATTERN.finditer(text):
            target = m.group(1).strip()
            display = m.group(2).strip() if m.group(2) else None
            link = {
                "raw": m.group(0),
                "target": target,
                "display": display,
                "resolved_path": self.resolve(target),
            }
            links.append(link)
        return links

    def extract_wikilinks_from_file(self, path: str | Path) -> list[dict]:
        """Extract all [[wikilinks]] from a markdown file."""
        path = Path(path)
        if not path.exists():
            return []
        text = path.read_text(encoding="utf-8", errors="replace")
        return self.extract_wikilinks(text)

    def extract_tags(self, text: str) -> list[str]:
        """Extract all #tags from text (inline tags, not frontmatter)."""
        return [m.group(1) for m in TAG_PATTERN.finditer(text)]

    def extract_tags_from_file(self, path: str | Path) -> list[str]:
        """Extract all #tags from a markdown file."""
        path = Path(path)
        if not path.exists():
            return []
        text = path.read_text(encoding="utf-8", errors="replace")
        return self.extract_tags(text)

    # ── Resolution ────────────────────────────────────────────

    def resolve(self, target: str) -> Optional[str]:
        """Resolve a [[wikilink]] target to a filesystem path.

        Search order:
          1. Exact filename match (with or without .md)
          2. Case-insensitive filename match
          3. Path-relative match (target as subpath of vault_root)

        Returns an absolute path string, or None if not found.
        """
        # Strip display text
        target = target.split("|")[0].strip()

        # If target already ends in .md, treat as exact
        if target.endswith(".md"):
            path = Path(self.vault_root / target)
            if path.exists() and path.is_file():
                return str(path.resolve())

        # Try with .md extension
        path = self.vault_root / f"{target}.md"
        if path.exists() and path.is_file():
            return str(path.resolve())

        # Try as path relative to vault root
        path = self.vault_root / target
        if path.exists() and path.is_file():
            return str(path.resolve())

        # Try case-insensitive search (one level wildcard)
        target_lower = target.lower()
        if not target_lower.endswith(".md"):
            target_lower = f"{target_lower}.md"

        # Depth-limited recursive search (skip symlinks to avoid recursion)
        for md_file in self.vault_root.rglob("*.md"):
            if md_file.is_symlink():
                continue
            if md_file.name.lower() == target_lower:
                return str(md_file.resolve())

        return None

    def resolve_all(self, targets: list[str]) -> dict[str, Optional[str]]:
        """Resolve multiple wikilink targets at once.

        Returns a dict of target -> resolved_path (None if not found).
        """
        return {t: self.resolve(t) for t in targets}

    # ── Graph Building ────────────────────────────────────────

    def build_adjacency_list(
        self, file_paths: list[str | Path]
    ) -> dict[str, list[str]]:
        """Build an adjacency list of wikilink connections.

        Args:
            file_paths: List of markdown file paths to analyze.

        Returns:
            Dict of file_path -> [linked_file_path, ...]
            Only includes links that resolve to another file in the set.
        """
        path_set: set[str] = set()
        for p in file_paths:
            p_obj = Path(p)
            if p_obj.is_symlink():
                continue
            path_set.add(str(p_obj.resolve()))
        adj: dict[str, list[str]] = {}

        for path_str in file_paths:
            path = Path(path_str).resolve()
            if not path.exists():
                continue

            links = self.extract_wikilinks_from_file(path)
            resolved: list[str] = []
            for link in links:
                rp = link["resolved_path"]
                if rp and rp in path_set and rp != str(path):
                    resolved.append(rp)

            adj[str(path)] = resolved

        return adj

    def walk(
        self,
        start_paths: list[str | Path],
        max_hops: int = 2,
    ) -> list[str]:
        """Walk the wikilink graph from start paths, returning connected paths.

        Args:
            start_paths: Starting file paths.
            max_hops: Maximum number of graph hops (0 = flat, 1 = direct links, 2 = links of links).

        Returns:
            Ordered list of file paths reached (start paths first, then by hop distance).
        """
        visited: set[str] = set()
        queue: list[tuple[str, int]] = []

        for p in start_paths:
            resolved = str(Path(p).resolve())
            if resolved not in visited:
                visited.add(resolved)
                queue.append((resolved, 0))

        result: list[str] = []
        all_files: list[str | Path] = [str(f) for f in self.vault_root.rglob("*.md")]
        adj = self.build_adjacency_list(all_files)

        while queue:
            current, depth = queue.pop(0)
            result.append(current)

            if depth < max_hops:
                for neighbor in adj.get(current, []):
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append((neighbor, depth + 1))

        return result