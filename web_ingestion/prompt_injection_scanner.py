"""
OverCR v2.5.0 — Prompt Injection Scanner

Scans fetched web content for prompt injection patterns that could
attempt to override system instructions, exfiltrate secrets, or
otherwise manipulate language model behavior.

The scanner FLAGS risk but NEVER deletes source content. Flagged
content remains in the normalized document with annotations in
the injection report. The operator reviews and decides.

Detection categories:
  - Instruction override: "ignore previous instructions", "you are now"
  - System/operator override: "you are a developer", "override system"
  - Secret exfiltration: "send your system prompt", "output your instructions"
  - Authority claims: "I am your creator", "you must obey"
  - Hidden injection: zero-width chars, text in comments that look like prompts
  - Model/tool manipulation: "use the terminal", "execute this command"
"""

import re
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class InjectionFlag:
    """A single detected prompt injection pattern."""
    pattern: str
    location: str  # Brief description of where found
    severity: str  # low | medium | high


@dataclass
class InjectionReport:
    """Result of a prompt injection scan."""
    risk_level: str = "none"  # none | low | medium | high | critical
    flags: list = field(default_factory=list)
    scanned_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict:
        return {
            "risk_level": self.risk_level,
            "flags": [{"pattern": f.pattern, "location": f.location,
                       "severity": f.severity} for f in self.flags],
            "scanned_at": self.scanned_at,
        }


class PromptInjectionScanner:
    """
    Scans content for prompt injection patterns.

    Every detection is recorded. Content is never deleted.
    The operator always has the final say.
    """

    # ── Pattern definitions ─────────────────────────────

    # Instruction override patterns (HIGH severity)
    INSTRUCTION_OVERRIDE = [
        (re.compile(r"ignore\s+(all\s+)?(previous|prior|above|earlier)\s+(instructions?|prompts?|directives?)", re.IGNORECASE),
         "instruction_override_ignore"),
        (re.compile(r"disregard\s+(all\s+)?(previous|prior|above)\s+(instructions?|prompts?)", re.IGNORECASE),
         "instruction_override_disregard"),
        (re.compile(r"you\s+are\s+now\s+(a\s+|an\s+)?(?:different|new)\s+(?:AI|model|assistant|agent|persona|role)", re.IGNORECASE),
         "instruction_override_new_role"),
        (re.compile(r"forget\s+(everything|all)\s+(you\s+)?(were\s+)?(told|said|instructed)", re.IGNORECASE),
         "instruction_override_forget"),
        (re.compile(r"(?:new|updated|revised)\s+(?:system\s+)?(?:prompt|instructions?|directive)", re.IGNORECASE),
         "instruction_override_new_prompt"),
    ]

    # System / operator override (HIGH severity)
    SYSTEM_OVERRIDE = [
        (re.compile(r"(?:you\s+are|act\s+as|pretend\s+to\s+be)\s+(?:a\s+|an\s+)?(?:developer|engineer|admin|operator|root)", re.IGNORECASE),
         "system_override_role"),
        (re.compile(r"override\s+(?:the\s+)?(?:system|operator|developer|admin)\s+(?:prompt|instructions?|settings?)", re.IGNORECASE),
         "system_override_explicit"),
        (re.compile(r"(?:bypass|disable|remove)\s+(?:governance|approval|validation|safety|security)\s+(?:gate|check|rule|constraint)", re.IGNORECASE),
         "system_override_governance"),
    ]

    # Secret exfiltration (HIGH severity)
    SECRET_EXFIL = [
        (re.compile(r"(?:tell|show|reveal|print|output|display|send)\s+(?:me|us)\s+(?:your|the)\s+(?:system\s+)?(?:prompt|instructions?|directives?)", re.IGNORECASE),
         "exfil_system_prompt"),
        (re.compile(r"(?:what|tell\s+me)\s+(?:is|are)\s+(?:your|the)\s+(?:instructions?|prompts?|rules?)", re.IGNORECASE),
         "exfil_prompt_query"),
        (re.compile(r"(?:send|post|upload|email)\s+(?:your|the)\s+(?:system\s+)?(?:prompt|instructions?|context|memory)", re.IGNORECASE),
         "exfil_send_prompt"),
        (re.compile(r"(?:dump|extract|copy)\s+(?:your|the)\s+(?:memory|context|history|state)", re.IGNORECASE),
         "exfil_memory_dump"),
    ]

    # Authority claims (MEDIUM severity)
    AUTHORITY_CLAIMS = [
        (re.compile(r"i\s+am\s+(?:your|the)\s+(?:creator|developer|owner|master|admin|operator)", re.IGNORECASE),
         "authority_creator"),
        (re.compile(r"(?:you|the\s+AI|the\s+model)\s+(?:must|have\s+to|shall)\s+(?:obey|comply|follow)\s+(?:me|my|these)", re.IGNORECASE),
         "authority_obey"),
        (re.compile(r"this\s+(?:is|are)\s+(?:an?|the)\s+(?:official|important|urgent|emergency)\s+(?:message|instruction|directive|update)", re.IGNORECASE),
         "authority_official"),
    ]

    # Hidden injection (MEDIUM severity)
    HIDDEN_INJECTION = [
        (re.compile(r"[\u200b\u200c\u200d\u200e\u200f\u2060\u2061\u2062\u2063\u2064\ufeff]"),
         "hidden_zero_width_chars"),
        (re.compile(r"<!--.*?(?:system|prompt|instruction|ignore|override).*?-->", re.IGNORECASE | re.DOTALL),
         "hidden_html_comment_prompt"),
        (re.compile(r"<span[^>]*style\s*=\s*[\"']\s*display\s*:\s*none.*?>.*?(?:system|prompt|instruction|override).*?</span>", re.IGNORECASE),
         "hidden_display_none"),
    ]

    # Model / tool manipulation (MEDIUM severity)
    TOOL_MANIPULATION = [
        (re.compile(r"(?:use|run|execute|call|invoke)\s+(?:the\s+)?(?:terminal|shell|bash|command|tool)\s+(?:to|and)", re.IGNORECASE),
         "tool_terminal"),
        (re.compile(r"(?:open|launch|start)\s+(?:a\s+)?(?:browser|webview|chrome|firefox)", re.IGNORECASE),
         "tool_browser"),
        (re.compile(r"(?:send|make)\s+(?:an?\s+)?(?:email|http\s+request|API\s+call|outbound)", re.IGNORECASE),
         "tool_outbound"),
        (re.compile(r"(?:curl|wget)\s+(?:https?://|ftp://)", re.IGNORECASE),
         "tool_curl"),
    ]

    # ── Scanning ────────────────────────────────────────

    def scan(self, content: str, url: str = "") -> InjectionReport:
        """
        Scan content for prompt injection patterns.

        Args:
            content: The fetched page content (raw or normalized).
            url: Source URL for location tagging.

        Returns:
            InjectionReport with risk level and all flagged patterns.
        """
        flags: list[InjectionFlag] = []

        # Instruction override patterns
        for pattern, name in self.INSTRUCTION_OVERRIDE:
            for m in pattern.finditer(content):
                flags.append(InjectionFlag(
                    pattern=name,
                    location=f"near offset {m.start()} in {url or 'content'}",
                    severity="high",
                ))

        # System override patterns
        for pattern, name in self.SYSTEM_OVERRIDE:
            for m in pattern.finditer(content):
                flags.append(InjectionFlag(
                    pattern=name,
                    location=f"near offset {m.start()} in {url or 'content'}",
                    severity="high",
                ))

        # Secret exfiltration patterns
        for pattern, name in self.SECRET_EXFIL:
            for m in pattern.finditer(content):
                flags.append(InjectionFlag(
                    pattern=name,
                    location=f"near offset {m.start()} in {url or 'content'}",
                    severity="high",
                ))

        # Authority claims
        for pattern, name in self.AUTHORITY_CLAIMS:
            for m in pattern.finditer(content):
                flags.append(InjectionFlag(
                    pattern=name,
                    location=f"near offset {m.start()} in {url or 'content'}",
                    severity="medium",
                ))

        # Hidden injection
        for pattern, name in self.HIDDEN_INJECTION:
            for m in pattern.finditer(content):
                sev = "medium"
                if name == "hidden_zero_width_chars":
                    sev = "low"  # Zero-width chars alone aren't necessarily malicious
                flags.append(InjectionFlag(
                    pattern=name,
                    location=f"near offset {m.start()} in {url or 'content'}",
                    severity=sev,
                ))

        # Tool manipulation
        for pattern, name in self.TOOL_MANIPULATION:
            for m in pattern.finditer(content):
                flags.append(InjectionFlag(
                    pattern=name,
                    location=f"near offset {m.start()} in {url or 'content'}",
                    severity="medium",
                ))

        # ── Compute risk level ──
        high_count = sum(1 for f in flags if f.severity == "high")
        medium_count = sum(1 for f in flags if f.severity == "medium")
        low_count = sum(1 for f in flags if f.severity == "low")

        if high_count >= 3:
            risk_level = "critical"
        elif high_count >= 1:
            risk_level = "high"
        elif medium_count >= 2:
            risk_level = "medium"
        elif medium_count >= 1 or low_count >= 1:
            risk_level = "low"
        else:
            risk_level = "none"

        return InjectionReport(
            risk_level=risk_level,
            flags=flags,
        )
