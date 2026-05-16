"""
OverCR v2.5.0 — Robots Policy

Inspects robots.txt for a given URL domain. Records the result
but never treats it as silent approval. If robots.txt is
unavailable, records "unknown" status. Policy uncertainty is
always visible in the audit record.

This is advisory governance, not automated enforcement.
"""

import re
from urllib.parse import urlparse, urljoin
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict


@dataclass
class RobotsPolicyResult:
    """Result of a robots.txt check for a URL."""
    checked: bool = False
    allowed: bool = True  # Default allowed when unchecked
    policy_url: str = ""
    status: str = "unknown"  # allowed | disallowed | unknown | error
    checked_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    details: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class RobotsPolicy:
    """
    Inspects robots.txt for URL fetch governance.

    Rules:
      - If robots.txt is available and explicitly disallows, record disallowed
      - If robots.txt is unavailable, record unknown
      - Never hides policy uncertainty
      - The operator decides whether to proceed; this is advisory only
    """

    # Common user-agent names (we use a simple, honest agent string)
    USER_AGENT = "OverCR-WebIngestion/2.5"

    @staticmethod
    def _robots_txt_url(url: str) -> str:
        """Extract the robots.txt URL for a given URL's domain."""
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}/robots.txt"

    @staticmethod
    def check(url: str, robots_txt_content: str = "") -> RobotsPolicyResult:
        """
        Check robots.txt policy for a URL.

        Args:
            url: The target URL
            robots_txt_content: Content of robots.txt (empty if unavailable).

        Returns:
            RobotsPolicyResult with status and details.
        """
        result = RobotsPolicyResult(
            checked=True,
            policy_url=RobotsPolicy._robots_txt_url(url),
        )

        if not robots_txt_content:
            result.checked = False
            result.status = "unknown"
            result.allowed = True  # Default allow when unknown
            result.details = "robots.txt unavailable — policy unknown"
            return result

        # Parse path from URL
        parsed = urlparse(url)
        path = parsed.path or "/"

        # Simple robots.txt parsing: find applicable rules
        # This is intentionally simple — we're not implementing a full parser
        # The operator reviews the result; we just record what we found
        lines = robots_txt_content.split("\n")
        current_agent = ""
        rules = {"*": []}  # Default agent rules

        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            if ":" in line:
                key, _, value = line.partition(":")
                key = key.strip().lower()
                value = value.strip()

                if key == "user-agent":
                    current_agent = value.lower()
                    if current_agent not in rules:
                        rules[current_agent] = []
                elif key in ("disallow", "allow") and current_agent:
                    rules[current_agent].append((key, value))

        # Check against our user-agent, then fall back to *
        applicable = rules.get(RobotsPolicy.USER_AGENT.lower(), []) or rules.get("*", [])

        for directive, pattern in applicable:
            if directive == "disallow" and pattern:
                # Check if path matches the disallow pattern
                if pattern == "/" or path.startswith(pattern):
                    result.status = "disallowed"
                    result.allowed = False
                    result.details = f"Disallowed by robots.txt rule: Disallow: {pattern}"
                    return result

        result.status = "allowed"
        result.allowed = True
        result.details = "No disallow rule matched in robots.txt"
        return result

    @staticmethod
    def check_simple(url: str = "") -> RobotsPolicyResult:
        """
        Check robots.txt without actual content (for offline/no-network tests).

        Returns unknown status — the safe default when we can't verify.
        """
        return RobotsPolicyResult(
            checked=False,
            allowed=True,
            status="unknown",
            details="robots.txt not fetched (offline/no-network mode)",
        )
