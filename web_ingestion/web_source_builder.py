"""
OverCR v2.5.0 — Web Source Builder

Converts a fetched web page into a v2.4 SourceRegistry record with
full provenance chain, fetch metadata, robots policy result, and
prompt injection risk report.

This is the bridge between the web ingestion gateway and the
knowledge subsystem. Every web source record is fully auditable,
provenance-aware, and operator-reviewable.

Governance:
  - Default trust tier is "unknown" unless explicitly classified lower
  - Fetched content is advisory — never canonical truth
  - No trust auto-escalation
  - No memory promotion without explicit route
  - Every record cites URL, fetch timestamp, content hash, and normalization chain
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from knowledge.source_registry import SourceRegistry, SourceRecordExistsError
from knowledge.provenance_tracker import ProvenanceTracker
from knowledge.source_classifier import SourceClassifier

from web_ingestion.fetch_gateway import FetchResult
from web_ingestion.url_request import URLRequest
from web_ingestion.content_normalizer import ContentNormalizer
from web_ingestion.robots_policy import RobotsPolicyResult
from web_ingestion.prompt_injection_scanner import PromptInjectionScanner, InjectionReport


class WebSourceBuilder:
    """
    Converts a FetchResult into a registered knowledge source.

    Normalizes content, scans for injection risks, attaches
    provenance, and registers with the v2.4 SourceRegistry.
    """

    def __init__(
        self,
        registry: SourceRegistry,
        tracker: ProvenanceTracker,
    ):
        """
        Args:
            registry: v2.4 SourceRegistry for registration
            tracker: v2.4 ProvenanceTracker for lineage
        """
        self.registry = registry
        self.tracker = tracker
        self.normalizer = ContentNormalizer()
        self.scanner = PromptInjectionScanner()
        self.classifier = SourceClassifier()

    # ── Build source from fetch ──────────────────────────

    def build_from_fetch(
        self,
        fetch_result: FetchResult,
        request: URLRequest,
        operator: str = "",
    ) -> dict:
        """
        Build a complete web source record from a fetch result.

        1. Normalize content
        2. Scan for prompt injection risks
        3. Build provenance chain
        4. Register as a knowledge source
        5. Record in provenance tracker

        Args:
            fetch_result: The FetchResult from FetchGateway
            request: The original URLRequest
            operator: Operator identity override

        Returns:
            dict with:
              - success: bool
              - source_id: str (if successful)
              - normalized_content: str
              - injection_report: dict
              - error: str (if failed)
        """
        if not fetch_result.success:
            return {
                "success": False,
                "source_id": "",
                "normalized_content": "",
                "injection_report": None,
                "error": f"Fetch failed: {fetch_result.error}",
            }

        op = operator or request.requested_by
        now = datetime.now(timezone.utc).isoformat()

        # 1. Normalize content
        if fetch_result.content_type and "html" in fetch_result.content_type.lower():
            markdown, title, links = self.normalizer.normalize_html(
                fetch_result.content
            )
            normalized = markdown
        else:
            normalized = ContentNormalizer.normalize_text(fetch_result.content)
            title = ""
            links = []

        # 2. Scan for prompt injection risks
        injection_report = self.scanner.scan(
            fetch_result.content,
            url=request.url,
        )

        # 3. Determine trust tier
        default_trust = "unknown"

        # If injection risk is critical or high, default to suspicious
        if injection_report.risk_level in ("critical", "high"):
            default_trust = "suspicious"

        # 4. Build provenance
        provenance = {
            "ingestion_path": [
                "web_fetch",
                "normalize",
                "prompt_injection_scan",
                "knowledge_registration",
            ],
            "transformation_chain": [
                {
                    "step": "web_fetch",
                    "timestamp": request.requested_at,
                    "operator": op,
                    "details": f"Fetched from {request.url} (purpose: {request.purpose})",
                },
                {
                    "step": "content_normalization",
                    "timestamp": now,
                    "operator": op,
                    "details": f"Normalized {'HTML' if 'html' in fetch_result.content_type.lower() else 'text'} to markdown/text",
                },
                {
                    "step": "prompt_injection_scan",
                    "timestamp": now,
                    "operator": op,
                    "details": f"Prompt injection scan: risk_level={injection_report.risk_level}, flags={len(injection_report.flags)}",
                },
            ],
            "canonical_refs": [request.url, fetch_result.final_url],
            "workflow_usage": [],
            "citation_count": 0,
        }

        # 5. Attempt to register with knowledge layer
        try:
            source = self.registry.register_source(
                origin=request.url,
                source_type="website",
                content=normalized,
                summary=title or f"Web source: {request.url}",
                tags=self.classifier.infer_tags(
                    content_snippet=normalized[:500],
                    origin=request.url,
                    existing_tags=["web-fetched"],
                ),
                project_scope=request.project_scope,
                trust_level=default_trust,
                canonical_refs=[request.url, fetch_result.final_url],
            )
        except SourceRecordExistsError:
            return {
                "success": False,
                "source_id": "",
                "normalized_content": normalized,
                "injection_report": injection_report.to_dict(),
                "error": "Source with this content already exists in the knowledge registry",
            }

        # 6. Augment with web-specific metadata
        source["_web_metadata"] = {
            "url": request.url,
            "final_url": fetch_result.final_url,
            "fetched_at": now,
            "fetch_status": fetch_result.status,
            "fetch_metadata": {
                "response_code": fetch_result.status_code,
                "content_type": fetch_result.content_type,
                "response_size_bytes": fetch_result.response_size_bytes,
                "elapsed_s": fetch_result.elapsed_s,
                "redirect_chain": fetch_result.redirect_chain,
            },
            "robots_policy_result": fetch_result.robots_policy.to_dict()
                if fetch_result.robots_policy else {},
            "prompt_injection_report": injection_report.to_dict(),
            "outbound_links_captured": len(links),
            "provenance": provenance,
        }

        # 7. Persist augmented record
        self.registry._write_record(source)

        # 8. Record in provenance tracker
        self.tracker.record_ingestion(
            source["source_id"],
            method="web_fetch",
            ingestor_version="2.5.0",
            operator=op,
        )
        self.tracker.record_origin(
            source["source_id"],
            request.url,
            origin_type="web",
        )

        # Record transformations
        self.tracker.record_transformation(
            source["source_id"],
            "content_normalization",
            operator=op,
        )
        self.tracker.record_transformation(
            source["source_id"],
            "prompt_injection_scan",
            operator=op,
        )

        # If injection risks found, record them
        if injection_report.flags:
            for flag in injection_report.flags:
                self.tracker.record_transformation(
                    source["source_id"],
                    f"injection_flag:{flag.pattern}",
                    operator=op,
                )

        return {
            "success": True,
            "source_id": source["source_id"],
            "normalized_content": normalized,
            "injection_report": injection_report.to_dict(),
            "error": None,
        }

    # ── Build failure record ──────────────────────────────

    def build_failure_record(
        self,
        request: URLRequest,
        error: str,
        status: str = "fetch_failed",
    ) -> dict:
        """
        Create an auditable failure record when a fetch cannot complete.

        Even failed fetches get provenance. The attempt is recorded.
        """
        now = datetime.now(timezone.utc).isoformat()

        record = {
            "type": "web_fetch_failure",
            "url": request.url,
            "requested_by": request.requested_by,
            "requested_at": request.requested_at,
            "purpose": request.purpose,
            "project_scope": request.project_scope,
            "failure_at": now,
            "failure_status": status,
            "error": error,
            "provenance": {
                "attempted": True,
                "completed": False,
                "operator": request.requested_by,
            },
        }

        # Write failure record to reports
        reports_dir = self.registry.root / "knowledge" / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)

        filename = f"fetch_failure_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}.json"
        with open(reports_dir / filename, "w") as f:
            json.dump(record, f, indent=2)

        return record
