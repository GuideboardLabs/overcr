"""
OverCR v2.5.0 — Content Normalizer

Normalizes fetched web content into a consistent markdown/text
format suitable for the knowledge subsystem. Extracts structure
but never follows links or executes scripts.

What this does:
  - Extract meaningful text from HTML
  - Preserve document title
  - Preserve canonical URL if declared
  - Preserve heading structure
  - Capture outbound links as metadata only
  - Normalize whitespace and line endings

What this does NOT do:
  - Does not follow links
  - Does not execute JavaScript
  - Does not render CSS
  - Does not attempt to preserve layout
"""

import re
import html
from html.parser import HTMLParser
from typing import Optional


def _clean_text(text: str) -> str:
    """Clean and normalize text content."""
    # Decode HTML entities
    text = html.unescape(text)
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


class ContentNormalizer(HTMLParser):
    """
    HTML-to-markdown normalizer.

    Produces clean, structured markdown from HTML page content.
    Headings are preserved, links are captured as metadata,
    and boilerplate (script, style, nav, footer) is stripped.
    """

    # Elements to skip entirely (no content extraction)
    SKIP_TAGS = {"script", "style", "noscript", "iframe", "svg", "canvas",
                 "nav", "footer", "header", "aside"}

    # Block-level elements that force a newline
    BLOCK_TAGS = {"div", "p", "section", "article", "main", "li", "br",
                  "hr", "blockquote", "pre", "table", "tr", "form"}

    def __init__(self):
        super().__init__()
        self._output: list[str] = []
        self._skip_depth = 0
        self._title = ""
        self._canonical_url = ""
        self._links: list[dict] = []
        self._headings: list[str] = []
        self._in_title = False
        self._in_link = False
        self._link_href = ""
        self._link_text = ""
        self._current_heading_level = 0
        self._line_buffer = ""
        self._metadata_extracted = False

    # ── Accessors ─────────────────────────────────────

    @property
    def markdown(self) -> str:
        """The normalized markdown output."""
        parts = []

        if self._title:
            parts.append(f"# {self._title}\n")

        if self._canonical_url:
            parts.append(f"> Canonical URL: {self._canonical_url}\n")

        parts.append("\n".join(self._output))
        return "\n".join(parts)

    @property
    def title(self) -> str:
        return self._title

    @property
    def extracted_links(self) -> list[dict]:
        """Outbound links captured as metadata (never followed)."""
        return self._links

    # ── Normalization entry point ─────────────────────

    @classmethod
    def normalize_html(cls, html_content: str) -> tuple[str, str, list[dict]]:
        """
        Normalize HTML content to markdown.

        Args:
            html_content: Raw HTML string.

        Returns:
            (markdown_text, title, links_list)
        """
        normalizer = cls()
        normalizer.feed(html_content)
        normalizer.close()
        return normalizer.markdown, normalizer.title, normalizer.extracted_links

    @classmethod
    def normalize_text(cls, text_content: str) -> str:
        """
        Normalize plain text content.

        Strips excess whitespace, normalizes line endings.
        """
        lines = text_content.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        cleaned = []
        for line in lines:
            stripped = line.strip()
            if stripped:
                cleaned.append(stripped)
        return "\n\n".join(cleaned)

    # ── HTML parsing ──────────────────────────────────

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)

        # Metadata extraction (once)
        if not self._metadata_extracted:
            if tag == "title":
                self._in_title = True
            elif tag == "link" and attrs_dict.get("rel") == "canonical":
                self._canonical_url = attrs_dict.get("href", "")
                self._metadata_extracted = True
            elif tag == "meta" and attrs_dict.get("property") == "og:title":
                self._title = attrs_dict.get("content", "")
            elif tag == "meta" and attrs_dict.get("name") == "description":
                pass  # description is useful but we don't capture it here

        # Skip tags
        if tag in self.SKIP_TAGS:
            self._skip_depth += 1
            return

        if self._skip_depth > 0:
            return

        # Headings
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._current_heading_level = int(tag[1])
            self._flush_line()

        # Links — capture but never follow
        if tag == "a":
            self._flush_line()
            self._in_link = True
            self._link_href = attrs_dict.get("href", "")
            self._link_text = ""

        # Block elements start a new line
        if tag in self.BLOCK_TAGS:
            self._flush_line()

        # List items
        if tag == "li":
            self._line_buffer += "- "

    def handle_endtag(self, tag):
        if tag in self.SKIP_TAGS:
            if self._skip_depth > 0:
                self._skip_depth -= 1
            return

        if self._skip_depth > 0:
            return

        if tag == "title":
            self._in_title = False
            self._metadata_extracted = True

        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._flush_heading(self._current_heading_level)
            self._current_heading_level = 0

        if tag == "a":
            if self._link_href:
                self._links.append({
                    "href": self._link_href,
                    "text": self._link_text[:200],
                })
            self._in_link = False

        if tag in self.BLOCK_TAGS:
            self._flush_line()

    def handle_data(self, data):
        if self._skip_depth > 0:
            return

        if self._in_title:
            self._title = self._title + data if self._title else data
            return

        text = data.strip()
        if not text:
            return

        if self._in_link:
            if self._link_text:
                self._link_text += " " + text
            else:
                self._link_text = text
            self._line_buffer += text
        else:
            self._line_buffer += text

    def _flush_line(self):
        """Flush the current line buffer to output."""
        line = self._line_buffer.strip()
        if line:
            self._output.append(line)
        self._line_buffer = ""

    def _flush_heading(self, level: int):
        """Flush as a heading line."""
        text = self._line_buffer.strip()
        if text:
            prefix = "#" * level
            self._output.append(f"{prefix} {text}")
            self._headings.append(text)
        self._line_buffer = ""
