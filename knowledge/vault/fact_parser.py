"""
OverCR Vault — Fact Parser

Parses gbrain/cammander/overcr facts fences from markdown notes.
Matches the established fence format:

    ## Facts (optional header)

    <!--- {prefix}:facts:begin -->
    | # | claim | kind | confidence | value | unit | source | context |
    |---|---|---|---|---|---|---|---|
    | 1 | Some claim | fact | 0.9 | 42 | tokens | codebase | backend |
    <!--- {prefix}:facts:end -->

Supports all three prefixes simultaneously for backward compatibility.
Ignores malformed or incomplete fence blocks.
"""

import re
from pathlib import Path
from typing import Any

# Fence patterns: one for each supported prefix
FENCE_PATTERNS = {
    "gbrain": re.compile(
        r"<!---\s*gbrain:facts:begin\s*-->\s*\n"
        r"(.*?)"
        r"<!---\s*gbrain:facts:end\s*-->",
        re.DOTALL,
    ),
    "cammander": re.compile(
        r"<!---\s*cammander:facts:begin\s*-->\s*\n"
        r"(.*?)"
        r"<!---\s*cammander:facts:end\s*-->",
        re.DOTALL,
    ),
    "overcr": re.compile(
        r"<!---\s*overcr:facts:begin\s*-->\s*\n"
        r"(.*?)"
        r"<!---\s*overcr:facts:end\s*-->",
        re.DOTALL,
    ),
    "brand": re.compile(
        r"<!---\s*brand:facts:begin\s*-->\s*\n"
        r"(.*?)"
        r"<!---\s*brand:facts:end\s*-->",
        re.DOTALL,
    ),
    "social": re.compile(
        r"<!---\s*social:facts:begin\s*-->\s*\n"
        r"(.*?)"
        r"<!---\s*social:facts:end\s*-->",
        re.DOTALL,
    ),
}

# Table row regex: | col1 | col2 | col3 | col4 | col5 | col6 | col7 | col8 |
TABLE_ROW = re.compile(
    r"^\|\s*(\d+)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|$"
)

# Bullet row regex: - [domain::key] claim
BULLET_ROW = re.compile(
    r"^\-\s*\[([^\]]+)\]\s*(.*)$"
)
HEADER_LINE = re.compile(r"^\|.*#\s*\|.*claim\s*\|", re.IGNORECASE)
SEPARATOR_LINE = re.compile(r"^\|[-:\s]+\|[-:\s]+\|")


def parse_file(path: str | Path) -> list[dict[str, Any]]:
    """Parse all facts fences from a single markdown file.

    Args:
        path: Path to a .md file.

    Returns:
        A list of fact dicts with keys:
          claim, kind, confidence, value, unit, source, context, line
        Each dict also carries the source prefix and the file path.
    """
    path = Path(path)
    if not path.exists():
        return []
    if path.suffix != ".md":
        return []

    text = path.read_text(encoding="utf-8", errors="replace")
    return _parse_text(text, str(path))


def parse_text(text: str, source_path: str = "<string>") -> list[dict[str, Any]]:
    """Parse facts fences from raw markdown text."""
    return _parse_text(text, source_path)


def _parse_text(text: str, source_path: str) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []

    for prefix, pattern in FENCE_PATTERNS.items():
        for match in pattern.finditer(text):
            fence_body = match.group(1).strip()
            rows = _parse_fence_body(fence_body)
            for row in rows:
                row["prefix"] = prefix
                row["source_file"] = source_path
            facts.extend(rows)

    return facts


def _parse_fence_body(body: str) -> list[dict[str, Any]]:
    """Parse the inner content of a facts fence (pipe table or bullet list)."""
    facts: list[dict[str, Any]] = []
    lines = body.split("\n")

    for i, line in enumerate(lines):
        original_line = line
        line = line.strip()

        # Skip empty lines, header rows, separator rows
        if not line or HEADER_LINE.match(line) or SEPARATOR_LINE.match(line):
            continue

        m = TABLE_ROW.match(line)
        if m:
            try:
                fact = {
                    "line": int(m.group(1)),
                    "claim": m.group(2).strip(),
                    "kind": m.group(3).strip(),
                    "confidence": _parse_float(m.group(4)),
                    "value": m.group(5).strip(),
                    "unit": m.group(6).strip(),
                    "source": m.group(7).strip(),
                    "context": m.group(8).strip(),
                }
                facts.append(fact)
            except (ValueError, IndexError):
                continue
        else:
            # Try bullet format: - [domain::key] claim
            b = BULLET_ROW.match(line)
            if b:
                raw_key = b.group(1).strip()
                raw_claim = b.group(2).strip()

                # Parse optional kind: prefix from claim
                kind = "n/a"
                claim = raw_claim
                kind_match = re.match(r"^kind:(\w+)\s+(.*)", raw_claim)
                if kind_match:
                    kind = kind_match.group(1).strip()
                    claim = kind_match.group(2).strip()

                # Check if claim ends with backslash for line continuation
                if claim.rstrip().endswith("\\"):
                    # Start accumulating multi-line claim
                    accumulated_claim = claim.rstrip().rstrip("\\")
                    start_idx = i + 1
                    while start_idx < len(lines):
                        next_line = lines[start_idx].strip()
                        if not next_line:
                            # Empty line ends continuation
                            break
                        # Check if next line is a new bullet (starts with -)
                        if next_line.startswith("-"):
                            # New bullet, stop accumulation
                            break
                        # Append to accumulated claim
                        accumulated_claim += " " + next_line
                        start_idx += 1
                    # Use accumulated claim
                    claim = accumulated_claim
                    i = start_idx - 1  # Skip processed continuation lines

                facts.append({
                    "line": 0,
                    "claim": f"[{raw_key}] {claim}",
                    "kind": kind,
                    "confidence": None,
                    "value": "",
                    "unit": "",
                    "source": "",
                    "context": "",
                    "fact_key": raw_key,
                })

            elif not line.startswith("-"):
                # Non-bullet, non-empty line: skip silently
                pass

        i += 1

    return facts


def _parse_float(val: str) -> float | None:
    val = val.strip()
    if not val:
        return None
    try:
        return float(val)
    except ValueError:
        return None