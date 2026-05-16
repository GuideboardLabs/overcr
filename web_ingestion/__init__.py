"""
OverCR v2.5.0 — Controlled Web Ingestion Gateway

An operator-auditable single-page web ingestion gateway for research
and knowledge workflows. Every fetch is operator-initiated, validated
against governance rules, normalized, scanned for prompt injection
risks, and registered as a provenance-aware knowledge source.

This is NOT autonomous crawling. No recursive link following, no
browser automation, no background daemons. Every URL is explicitly
provided by the operator with a stated purpose.

Exports:
  - URLRequest: typed, auditable fetch request
  - FetchGateway: governed single-page HTTP fetcher
  - FetchResult: fetch outcome with metadata
  - ContentNormalizer: HTML/text to markdown normalization
  - RobotsPolicy: robots.txt advisory check
  - PromptInjectionScanner: injection pattern detection
  - WebSourceBuilder: fetch-to-knowledge-source bridge
"""

from web_ingestion.url_request import URLRequest
from web_ingestion.fetch_gateway import FetchGateway, FetchResult
from web_ingestion.content_normalizer import ContentNormalizer
from web_ingestion.robots_policy import RobotsPolicy, RobotsPolicyResult
from web_ingestion.prompt_injection_scanner import PromptInjectionScanner, InjectionReport, InjectionFlag
from web_ingestion.web_source_builder import WebSourceBuilder

__all__ = [
    "URLRequest",
    "FetchGateway",
    "FetchResult",
    "ContentNormalizer",
    "RobotsPolicy",
    "RobotsPolicyResult",
    "PromptInjectionScanner",
    "InjectionReport",
    "InjectionFlag",
    "WebSourceBuilder",
]

__version__ = "2.5.0"
