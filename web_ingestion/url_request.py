"""
OverCR v2.5.0 — URL Request

A typed, auditable URL fetch request. Every field is recorded in
provenance. Nothing is auto-fetched — an operator must explicitly
provide the URL and purpose.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional


@dataclass
class URLRequest:
    """
    An operator-initiated URL fetch request.

    All fields are auditable. The request object is the audit record
    of what was asked for, by whom, and why.
    """

    url: str
    requested_by: str
    purpose: str
    project_scope: str = "default"

    requested_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    allowed_content_types: list = field(default_factory=lambda: [
        "text/html", "text/plain", "application/json",
    ])
    max_bytes: int = 524288  # 512KB default
    timeout_s: float = 30.0
    follow_redirects: bool = True
    approval_required: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "URLRequest":
        return cls(
            url=data.get("url", ""),
            requested_by=data.get("requested_by", ""),
            purpose=data.get("purpose", ""),
            project_scope=data.get("project_scope", "default"),
            requested_at=data.get("requested_at",
                                   datetime.now(timezone.utc).isoformat()),
            allowed_content_types=data.get("allowed_content_types",
                                            ["text/html", "text/plain", "application/json"]),
            max_bytes=data.get("max_bytes", 524288),
            timeout_s=data.get("timeout_s", 30.0),
            follow_redirects=data.get("follow_redirects", True),
            approval_required=data.get("approval_required", False),
        )
