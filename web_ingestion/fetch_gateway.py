"""
OverCR v2.5.0 — Fetch Gateway

The single entry point for operator-auditable web page fetching.
Accepts a URLRequest, validates the URL against governance rules,
fetches exactly one page, and returns a FetchResult with the raw
response data and fetch metadata.

What this does:
  - Validate URL scheme (http/https only)
  - Block private IPs, localhost, file://
  - Block redirects to private IPs
  - Enforce max_bytes cap
  - Enforce timeout
  - Record complete fetch metadata

What this does NOT do:
  - No cookies
  - No auth headers
  - No JavaScript execution
  - No browser automation
  - No recursive link following
  - No form submission
  - No background daemon fetching
"""

import hashlib
import ipaddress
import re
import socket
import time
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Optional, Callable
from urllib.parse import urlparse

from web_ingestion.url_request import URLRequest
from web_ingestion.robots_policy import RobotsPolicy, RobotsPolicyResult


# ── Private network ranges ────────────────────────────

PRIVATE_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


def _is_private_ip(host: str) -> bool:
    """Check if a hostname resolves to a private IP, or is itself a private IP."""
    try:
        addr = ipaddress.ip_address(host)
        for net in PRIVATE_NETWORKS:
            if addr in net:
                return True
        return False
    except ValueError:
        # Not a literal IP — try DNS resolution (but NEVER in tests)
        try:
            resolved = socket.getaddrinfo(host, None)
            for _, _, _, _, sockaddr in resolved:
                ip = sockaddr[0]
                addr = ipaddress.ip_address(ip)
                for net in PRIVATE_NETWORKS:
                    if addr in net:
                        return True
        except (socket.gaierror, OSError):
            pass
        return False


# ── Fetch result ──────────────────────────────────────

@dataclass
class FetchResult:
    """Result of a single-page fetch."""
    success: bool
    url: str
    final_url: str = ""
    status: str = "unknown"
    status_code: int = 0
    content: str = ""
    content_type: str = ""
    response_size_bytes: int = 0
    elapsed_s: float = 0.0
    redirect_chain: list = field(default_factory=list)
    error: str = ""
    robots_policy: Optional[RobotsPolicyResult] = None

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "url": self.url,
            "final_url": self.final_url,
            "status": self.status,
            "status_code": self.status_code,
            "content": self.content,
            "content_type": self.content_type,
            "response_size_bytes": self.response_size_bytes,
            "elapsed_s": self.elapsed_s,
            "redirect_chain": self.redirect_chain,
            "error": self.error,
            "robots_policy": self.robots_policy.to_dict() if self.robots_policy else None,
        }


# ── Fetch gateway ─────────────────────────────────────

class FetchGateway:
    """
    Governed single-page web fetcher.

    Every fetch goes through validation, robots policy check,
    and response-size enforcement. Nothing happens silently.
    """

    # Allowed schemes
    ALLOWED_SCHEMES = {"http", "https"}

    # Schemes explicitly blocked
    BLOCKED_SCHEMES = {"file", "ftp", "data", "javascript", "vbscript"}

    def __init__(self, http_fetcher: Optional[Callable] = None):
        """
        Args:
            http_fetcher: Optional callable(url, timeout, max_bytes, follow_redirects)
                          -> (status_code, content, content_type, final_url, redirect_chain).
                          If None, uses real requests library.
        """
        self._fetcher = http_fetcher
        self._robots = RobotsPolicy()

    def set_fetcher(self, fetcher: Callable):
        """Inject a custom HTTP fetcher (for mocking in tests)."""
        self._fetcher = fetcher

    # ── URL validation ──────────────────────────────

    def validate_url(self, url: str) -> tuple[bool, str]:
        """
        Validate a URL against governance rules.

        Returns: (valid, error_message)
        """
        if not url or not url.strip():
            return False, "URL is empty"

        try:
            parsed = urlparse(url)
        except Exception:
            return False, f"Malformed URL: {url}"

        # Scheme check
        scheme = parsed.scheme.lower()
        if scheme in self.BLOCKED_SCHEMES:
            return False, f"Blocked scheme: '{scheme}' — only http/https allowed"
        if scheme not in self.ALLOWED_SCHEMES:
            return False, f"Unsupported scheme: '{scheme}' — only http/https allowed"

        # Hostname check
        host = parsed.hostname
        if not host:
            return False, f"No hostname in URL: {url}"

        # Private IP check
        if self._is_private_host(host):
            return False, f"Blocked private IP/localhost: {host}"

        return True, ""

    def _is_private_host(self, host: str) -> bool:
        """Check if a hostname denotes a private/local address."""
        host_lower = host.lower()

        # Localhost variants
        if host_lower in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
            return True

        # Private IP ranges
        try:
            addr = ipaddress.ip_address(host)
            for net in PRIVATE_NETWORKS:
                if addr in net:
                    return True
        except ValueError:
            pass

        return False

    # ── Fetch ───────────────────────────────────────

    def fetch_url(self, request: URLRequest) -> FetchResult:
        """
        Fetch a single URL with full governance.

        Args:
            request: The validated URLRequest.

        Returns:
            FetchResult with content and metadata, or error details.
        """
        url = request.url
        start = time.time()

        # 1. Validate URL
        valid, error = self.validate_url(url)
        if not valid:
            return FetchResult(
                success=False,
                url=url,
                status="blocked_scheme" if "scheme" in error.lower() else "blocked",
                error=error,
                elapsed_s=round(time.time() - start, 3),
            )

        # 2. Robots policy check
        robots_result = self._robots.check_simple(request.url)

        # 3. Fetch
        fetcher = self._fetcher or self._real_fetch

        try:
            status_code, content, content_type, final_url, redirect_chain = fetcher(
                url,
                timeout=request.timeout_s,
                max_bytes=request.max_bytes,
                follow_redirects=request.follow_redirects,
            )
            elapsed = time.time() - start

        except TimeoutError:
            elapsed = time.time() - start
            return FetchResult(
                success=False,
                url=url,
                status="timeout",
                error=f"Fetch timed out after {request.timeout_s}s",
                elapsed_s=round(elapsed, 3),
                robots_policy=robots_result,
            )
        except Exception as e:
            elapsed = time.time() - start
            return FetchResult(
                success=False,
                url=url,
                status="network_error",
                error=str(e),
                elapsed_s=round(elapsed, 3),
                robots_policy=robots_result,
            )

        # 4. Check redirects didn't land on private IPs
        if redirect_chain:
            for redirected_url in redirect_chain:
                try:
                    parsed = urlparse(redirected_url)
                    if parsed.hostname and self._is_private_host(parsed.hostname):
                        return FetchResult(
                            success=False,
                            url=url,
                            final_url=redirected_url,
                            status="blocked_redirect",
                            error=f"Redirect to private IP blocked: {redirected_url}",
                            redirect_chain=redirect_chain,
                            elapsed_s=round(elapsed, 3),
                            robots_policy=robots_result,
                        )
                except Exception:
                    pass

        # 5. Enforce max_bytes (truncate if exceeded)
        raw_size = len(content.encode("utf-8")) if isinstance(content, str) else len(content)
        if raw_size > request.max_bytes:
            # Truncate but preserve the record
            if isinstance(content, str):
                content = content[:request.max_bytes]
            else:
                content = content[:request.max_bytes]

        response_size = len(content.encode("utf-8")) if isinstance(content, str) else len(content)

        # 6. Build result
        return FetchResult(
            success=True,
            url=url,
            final_url=final_url or url,
            status="success",
            status_code=status_code,
            content=content if isinstance(content, str) else content.decode("utf-8", errors="replace"),
            content_type=content_type,
            response_size_bytes=response_size,
            elapsed_s=round(elapsed, 3),
            redirect_chain=redirect_chain,
            robots_policy=robots_result,
        )

    # ── Real HTTP fetch (only used when no mock injected) ──

    @staticmethod
    def _real_fetch(url: str, timeout: float, max_bytes: int,
                    follow_redirects: bool) -> tuple:
        """
        Real HTTP fetch using the requests library.

        Only called when no mock fetcher is injected. Tests NEVER
        reach this path because they inject a mock.
        """
        import requests

        response = requests.get(
            url,
            timeout=timeout,
            allow_redirects=follow_redirects,
            headers={"User-Agent": "OverCR-WebIngestion/2.5"},
            stream=True,
        )

        # Read up to max_bytes + 1 to detect overflow
        content_chunks = []
        total = 0
        for chunk in response.iter_content(chunk_size=8192):
            total += len(chunk)
            if total > max_bytes:
                content_chunks.append(chunk[:max_bytes - (total - len(chunk))])
                break
            content_chunks.append(chunk)

        content = b"".join(content_chunks)
        content_type = response.headers.get("Content-Type", "text/html")
        final_url = response.url

        # Build redirect chain from response history
        redirect_chain = [r.url for r in response.history]

        return (
            response.status_code,
            content.decode("utf-8", errors="replace"),
            content_type,
            final_url,
            redirect_chain,
        )
