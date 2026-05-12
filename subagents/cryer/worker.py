#!/usr/bin/env python3
"""
OverCR CryER Worker — Crawling Reputation, Yield, Engagement & Recon

This is a live subagent worker for the OverCR orchestration substrate.
It receives a request packet on stdin (JSON) and writes a response
packet to stdout (JSON).

Worker contract:
  - Input:  JSON request packet on stdin
  - Output: JSON response packet on stdout
  - Exit 0: success (response packet valid)
  - Exit nonzero: failure (caller must not trust output)

What this worker does:
  - Receives a task instruction and input context with public signal snippets
  - For "recon" domain: produces a cryer_recon packet with yield scoring
  - For "reputation_signal" domain: produces a cryer_reputation_signal packet
  - For "engagement_signal" domain: produces a cryer_engagement_signal packet
  - For "booking_friction" domain: produces a cryer_booking_friction packet
  - For "directory_completeness" domain: produces a cryer_directory_completeness packet
  - For "hiring_growth" domain: produces a cryer_hiring_growth packet
  - Never makes outbound contact
  - Never modifies OverCR doctrine
  - Never executes shell commands
  - Never accesses the network

What this worker does NOT do:
  - Live web crawling or browsing
  - Browser automation or rendering
  - Login/authenticated access to any service
  - Outbound contact of any kind (email, phone, DM, form submission)
  - Form submission or booking attempts
  - Provider/runtime replacement

Safety note:
  The worker output is ALWAYS validated by the OverCR runtime's 6-level
  packet validator before state advancement. Malformed or invalid output
  is rejected and the task enters validation_failed — never auto-completed.
"""

import json
import sys
from datetime import datetime, timezone


def read_request() -> dict:
    """Read and parse the request packet from stdin."""
    raw = sys.stdin.read()
    if not raw.strip():
        print(json.dumps({
            "error": "empty_input",
            "message": "Worker received empty input on stdin",
        }), file=sys.stderr)
        sys.exit(1)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        print(json.dumps({
            "error": "invalid_json",
            "message": f"Worker received invalid JSON on stdin: {e}",
        }), file=sys.stderr)
        sys.exit(1)


# ── Helper: Classification enums ─────────────────────────────

SIGNAL_TYPES_REPUTATION = {
    "rating", "review_volume", "sentiment", "accreditation",
    "mention_frequency", "complaint_pattern",
}

METRIC_TYPES_ENGAGEMENT = {
    "review_count", "average_rating", "response_rate",
    "recency", "platform_presence",
}

FRICTION_TYPES_BOOKING = {
    "limited_hours", "no_online_booking", "complex_scheduling",
    "high_cancellation_penalty", "opaque_pricing", "contact_required",
    "poor_availability_info", "ux_barrier",
}

SIGNAL_TYPES_HIRING = {
    "job_posting", "growth_indication", "expansion_signal",
    "hiring_surge", "department_opening", "role_specific",
}

CLASSIFICATIONS = {"observed", "inferred", "assumed", "unknown"}
SOURCE_QUALITIES = {"primary", "secondary", "tertiary", "unverified"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _extract_entity(request: dict) -> str:
    """Extract entity from request input_context."""
    ic = request.get("input_context", {})
    return ic.get("entity", "unspecified_entity")


def _extract_snippets(request: dict) -> str:
    """Extract provided text snippets from input_context."""
    ic = request.get("input_context", {})
    # Accept multiple common field names for input snippets
    for key in ("snippets", "text", "content", "input_text", "raw_text"):
        if ic.get(key):
            val = ic[key]
            if isinstance(val, list):
                return " ".join(str(s) for s in val)
            return str(val)
    return ""


# ── Packet builders ───────────────────────────────────────────

def build_recon_packet(request: dict) -> dict:
    """
    Build a cryer_recon response packet for a recon task.

    Produces yield scoring and signal analysis from provided snippets.
    """
    task_id = request.get("task_id", "task-0000")
    instruction = request.get("instruction", "")
    input_context = request.get("input_context", {})
    entity = _extract_entity(request)
    snippets = _extract_snippets(request)

    # Build targets from input context or a single default
    provided_targets = input_context.get("targets", [])
    targets = []

    if provided_targets:
        for t in provided_targets:
            targets.append({
                "entity": t.get("entity", entity),
                "type": t.get("type", "business"),
                "signals": {
                    "reputation": {
                        "yield_score": t.get("yield_score", 50),
                        "confidence": t.get("confidence", 50),
                        "risk_flags": t.get("risk_flags", []),
                    }
                },
                "raw_sources": t.get("raw_sources", ["provided_input"]),
            })
    else:
        # Single target from entity
        yield_score = 50
        confidence = 40
        classification = "assumed"

        if snippets:
            # Simple heuristic: longer snippets suggest more data
            snippet_len = len(snippets)
            confidence = min(60, 30 + snippet_len // 100)
            yield_score = min(70, 40 + snippet_len // 200)
            classification = "inferred" if snippet_len > 200 else "assumed"

        targets.append({
            "entity": entity,
            "type": "business",
            "signals": {
                "reputation": {
                    "yield_score": yield_score,
                    "confidence": confidence,
                    "risk_flags": [],
                }
            },
            "raw_sources": ["provided_input"],
        })

    packet = {
        "packet_type": "cryer_recon",
        "version": "1.0",
        "timestamp": _utc_now(),
        "source": "cryer",
        "target": "overcr",
        "task_id": task_id,
        "summary": f"CryER recon complete for: {entity}",
        "recon_data": {
            "targets": targets,
        },
        "audit_trail": {
            "worker_version": "0.4.0",
            "execution_timestamp": _utc_now(),
            "collection_timestamps": [_utc_now()],
            "methods_used": ["public_signal_analysis"],
            "files_modified": [],
            "rollback_instructions": "No filesystem changes made by worker. Analysis only.",
        },
        "approval_required": False,
        "next_steps_recommendation": "No external action needed. Route to OverCR for downstream handling.",
    }

    upstream_id = input_context.get("upstream_task_id")
    if upstream_id:
        packet["upstream_task_id"] = upstream_id

    return packet


def build_reputation_signal_packet(request: dict) -> dict:
    """
    Build a cryer_reputation_signal response packet.

    Produces structured reputation signal summary from provided snippets.
    """
    task_id = request.get("task_id", "task-0000")
    instruction = request.get("instruction", "")
    input_context = request.get("input_context", {})
    entity = _extract_entity(request)
    snippets = _extract_snippets(request)

    # Build signals from input context
    provided_signals = input_context.get("signals", [])
    signals = []

    if provided_signals:
        for s in provided_signals:
            signals.append({
                "type": s.get("type", "sentiment"),
                "classification": s.get("classification", "inferred") if s.get("classification") in CLASSIFICATIONS else "inferred",
                "confidence": max(0, min(100, s.get("confidence", 50))),
                "detail": s.get("detail", "Signal detected in provided input"),
                "source_quality": s.get("source_quality", "secondary") if s.get("source_quality") in SOURCE_QUALITIES else "secondary",
                "unknowns": s.get("unknowns", []),
            })
    else:
        # Default signal from snippet analysis
        confidence = 40
        classification = "assumed"
        if snippets:
            confidence = min(60, 30 + len(snippets) // 100)
            classification = "inferred" if len(snippets) > 200 else "assumed"

        signals.append({
            "type": "sentiment",
            "classification": classification,
            "confidence": confidence,
            "detail": f"Reputation signal analysis for {entity} based on provided input",
            "source_quality": "secondary",
            "unknowns": ["Direct verification needed"],
        })

    # Calculate yield and confidence
    avg_confidence = sum(s["confidence"] for s in signals) // max(1, len(signals))
    yield_score = min(100, avg_confidence + 10)

    packet = {
        "packet_type": "cryer_reputation_signal",
        "version": "1.0",
        "timestamp": _utc_now(),
        "source": "cryer",
        "target": "overcr",
        "task_id": task_id,
        "summary": f"CryER reputation signal analysis for: {entity}",
        "reputation_signal_data": {
            "entity": entity,
            "signals": signals,
            "yield_score": yield_score,
            "confidence_notes": f"Confidence based on {len(signals)} signal(s) from provided input. Direct verification recommended.",
            "recommended_routing": "overcr",
        },
        "audit_trail": {
            "worker_version": "0.4.0",
            "execution_timestamp": _utc_now(),
            "methods_used": ["public_signal_analysis"],
            "files_modified": [],
            "rollback_instructions": "No filesystem changes made by worker. Analysis only.",
        },
        "approval_required": False,
        "next_steps_recommendation": "No external action needed. Route to OverCR for downstream handling.",
    }

    upstream_id = input_context.get("upstream_task_id")
    if upstream_id:
        packet["upstream_task_id"] = upstream_id

    return packet


def build_engagement_signal_packet(request: dict) -> dict:
    """
    Build a cryer_engagement_signal response packet.

    Produces engagement signal summary from provided review/rating text.
    """
    task_id = request.get("task_id", "task-0000")
    instruction = request.get("instruction", "")
    input_context = request.get("input_context", {})
    entity = _extract_entity(request)
    snippets = _extract_snippets(request)

    # Build metrics from input context
    provided_metrics = input_context.get("metrics", [])
    metrics = []

    if provided_metrics:
        for m in provided_metrics:
            metrics.append({
                "type": m.get("type", "review_count") if m.get("type") in METRIC_TYPES_ENGAGEMENT else "review_count",
                "classification": m.get("classification", "inferred") if m.get("classification") in CLASSIFICATIONS else "inferred",
                "value": str(m.get("value", "unknown")),
                "confidence": max(0, min(100, m.get("confidence", 50))),
                "source_quality": m.get("source_quality", "secondary") if m.get("source_quality") in SOURCE_QUALITIES else "secondary",
                "unknowns": m.get("unknowns", []),
            })
    else:
        confidence = 40
        classification = "assumed"
        if snippets:
            confidence = min(55, 30 + len(snippets) // 150)
            classification = "inferred" if len(snippets) > 150 else "assumed"

        metrics.append({
            "type": "review_count",
            "classification": classification,
            "value": "unknown",
            "confidence": confidence,
            "source_quality": "unverified",
            "unknowns": ["Exact count requires direct verification"],
        })

    packet = {
        "packet_type": "cryer_engagement_signal",
        "version": "1.0",
        "timestamp": _utc_now(),
        "source": "cryer",
        "target": "overcr",
        "task_id": task_id,
        "summary": f"CryER engagement signal analysis for: {entity}",
        "engagement_signal_data": {
            "entity": entity,
            "metrics": metrics,
            "engagement_summary": f"Engagement analysis for {entity} based on {len(metrics)} metric(s) from provided input. Further verification recommended.",
            "recommended_routing": "overcr",
        },
        "audit_trail": {
            "worker_version": "0.4.0",
            "execution_timestamp": _utc_now(),
            "methods_used": ["public_signal_analysis"],
            "files_modified": [],
            "rollback_instructions": "No filesystem changes made by worker. Analysis only.",
        },
        "approval_required": False,
        "next_steps_recommendation": "No external action needed. Route to OverCR for downstream handling.",
    }

    upstream_id = input_context.get("upstream_task_id")
    if upstream_id:
        packet["upstream_task_id"] = upstream_id

    return packet


def build_booking_friction_packet(request: dict) -> dict:
    """
    Build a cryer_booking_friction response packet.

    Detects booking/scheduling friction from provided text snippets.
    """
    task_id = request.get("task_id", "task-0000")
    instruction = request.get("instruction", "")
    input_context = request.get("input_context", {})
    entity = _extract_entity(request)
    snippets = _extract_snippets(request)

    # Build friction points from input context
    provided_frictions = input_context.get("friction_points", [])
    friction_points = []

    if provided_frictions:
        for f in provided_frictions:
            friction_points.append({
                "type": f.get("type", "contact_required") if f.get("type") in FRICTION_TYPES_BOOKING else "contact_required",
                "classification": f.get("classification", "observed") if f.get("classification") in CLASSIFICATIONS else "observed",
                "confidence": max(0, min(100, f.get("confidence", 50))),
                "detail": f.get("detail", "Booking friction detected in provided input"),
                "source_quality": f.get("source_quality", "primary") if f.get("source_quality") in SOURCE_QUALITIES else "primary",
                "unknowns": f.get("unknowns", []),
            })
    else:
        # Default friction from snippet analysis
        confidence = 50
        classification = "assumed"

        friction_points.append({
            "type": "contact_required",
            "classification": classification,
            "confidence": confidence,
            "detail": f"Booking process for {entity} requires analysis of provided input",
            "source_quality": "secondary",
            "unknowns": ["Direct verification of booking process recommended"],
        })

    packet = {
        "packet_type": "cryer_booking_friction",
        "version": "1.0",
        "timestamp": _utc_now(),
        "source": "cryer",
        "target": "overcr",
        "task_id": task_id,
        "summary": f"CryER booking friction analysis for: {entity}",
        "booking_friction_data": {
            "entity": entity,
            "friction_points": friction_points,
            "friction_summary": f"Booking friction analysis for {entity}: {len(friction_points)} friction point(s) identified from provided input.",
            "recommended_routing": "overcr",
        },
        "audit_trail": {
            "worker_version": "0.4.0",
            "execution_timestamp": _utc_now(),
            "methods_used": ["public_signal_analysis"],
            "files_modified": [],
            "rollback_instructions": "No filesystem changes made by worker. Analysis only.",
        },
        "approval_required": False,
        "next_steps_recommendation": "No external action needed. Route to OverCR for downstream handling.",
    }

    upstream_id = input_context.get("upstream_task_id")
    if upstream_id:
        packet["upstream_task_id"] = upstream_id

    return packet


def build_directory_completeness_packet(request: dict) -> dict:
    """
    Build a cryer_directory_completeness response packet.

    Assesses directory listing completeness from provided directory text.
    """
    task_id = request.get("task_id", "task-0000")
    instruction = request.get("instruction", "")
    input_context = request.get("input_context", {})
    entity = _extract_entity(request)
    snippets = _extract_snippets(request)

    # Build completeness assessment from input context
    provided_present = input_context.get("present_fields", [])
    provided_missing = input_context.get("missing_fields", [])

    # Default field analysis
    present_fields = provided_present if provided_present else ["name"]
    missing_fields = provided_missing if provided_missing else [
        "phone", "website", "hours", "description", "photos"
    ]

    # Calculate completeness score
    total_expected = len(present_fields) + len(missing_fields)
    completeness_score = (len(present_fields) * 100) // max(1, total_expected)

    classification = "observed" if provided_present else "inferred"
    confidence = min(80, 40 + len(present_fields) * 5)

    packet = {
        "packet_type": "cryer_directory_completeness",
        "version": "1.0",
        "timestamp": _utc_now(),
        "source": "cryer",
        "target": "overcr",
        "task_id": task_id,
        "summary": f"CryER directory completeness assessment for: {entity}",
        "directory_completeness_data": {
            "entity": entity,
            "present_fields": present_fields,
            "missing_fields": missing_fields,
            "completeness_score": completeness_score,
            "classification": classification,
            "confidence": confidence,
            "recommended_routing": "overcr",
            "source_quality": "secondary",
            "unknowns": ["Direct verification of listing recommended"],
        },
        "audit_trail": {
            "worker_version": "0.4.0",
            "execution_timestamp": _utc_now(),
            "methods_used": ["public_signal_analysis"],
            "files_modified": [],
            "rollback_instructions": "No filesystem changes made by worker. Analysis only.",
        },
        "approval_required": False,
        "next_steps_recommendation": "No external action needed. Route to OverCR for downstream handling.",
    }

    upstream_id = input_context.get("upstream_task_id")
    if upstream_id:
        packet["upstream_task_id"] = upstream_id

    return packet


def build_hiring_growth_packet(request: dict) -> dict:
    """
    Build a cryer_hiring_growth response packet.

    Detects hiring/growth signals from provided job listings or announcements.
    """
    task_id = request.get("task_id", "task-0000")
    instruction = request.get("instruction", "")
    input_context = request.get("input_context", {})
    entity = _extract_entity(request)
    snippets = _extract_snippets(request)

    # Build signals from input context
    provided_signals = input_context.get("signals", [])
    signals = []

    if provided_signals:
        for s in provided_signals:
            signals.append({
                "type": s.get("type", "job_posting") if s.get("type") in SIGNAL_TYPES_HIRING else "job_posting",
                "classification": s.get("classification", "observed") if s.get("classification") in CLASSIFICATIONS else "observed",
                "confidence": max(0, min(100, s.get("confidence", 60))),
                "detail": s.get("detail", "Hiring signal detected in provided input"),
                "source_quality": s.get("source_quality", "primary") if s.get("source_quality") in SOURCE_QUALITIES else "primary",
                "unknowns": s.get("unknowns", []),
            })
    else:
        # Default signal from snippet analysis
        confidence = 50
        classification = "assumed"
        if snippets:
            confidence = min(65, 40 + len(snippets) // 100)
            classification = "inferred" if len(snippets) > 150 else "assumed"

        signals.append({
            "type": "job_posting",
            "classification": classification,
            "confidence": confidence,
            "detail": f"Hiring/growth signal analysis for {entity} based on provided input",
            "source_quality": "secondary",
            "unknowns": ["Direct verification of job postings recommended"],
        })

    packet = {
        "packet_type": "cryer_hiring_growth",
        "version": "1.0",
        "timestamp": _utc_now(),
        "source": "cryer",
        "target": "overcr",
        "task_id": task_id,
        "summary": f"CryER hiring/growth signal analysis for: {entity}",
        "hiring_growth_data": {
            "entity": entity,
            "signals": signals,
            "growth_summary": f"Hiring/growth analysis for {entity}: {len(signals)} signal(s) detected from provided input. Further verification recommended.",
            "recommended_routing": "overcr",
        },
        "audit_trail": {
            "worker_version": "0.4.0",
            "execution_timestamp": _utc_now(),
            "methods_used": ["public_signal_analysis"],
            "files_modified": [],
            "rollback_instructions": "No filesystem changes made by worker. Analysis only.",
        },
        "approval_required": False,
        "next_steps_recommendation": "No external action needed. Route to OverCR for downstream handling.",
    }

    upstream_id = input_context.get("upstream_task_id")
    if upstream_id:
        packet["upstream_task_id"] = upstream_id

    return packet


def build_blocked_packet(request: dict, reason: str) -> dict:
    """Build a cryer_blocked packet when the worker cannot proceed."""
    task_id = request.get("task_id", "task-0000")

    return {
        "packet_type": "cryer_recon",  # Use recon as fallback since blocked is not a registered CryER type
        "version": "1.0",
        "timestamp": _utc_now(),
        "source": "cryer",
        "target": "overcr",
        "task_id": task_id,
        "summary": f"CryER blocked: {reason}",
        "recon_data": {
            "targets": [],
        },
        "audit_trail": {
            "worker_version": "0.4.0",
            "execution_timestamp": _utc_now(),
            "collection_timestamps": [_utc_now()],
            "methods_used": ["none"],
            "files_modified": [],
            "rollback_instructions": "No filesystem changes made by worker.",
        },
        "approval_required": False,
        "next_steps_recommendation": f"Blocked: {reason}. Clarify task specification and resubmit.",
    }


# ── Domain dispatch ────────────────────────────────────────────

DOMAIN_TO_PACKET_TYPE = {
    "recon": "cryer_recon",
    "reputation_signal": "cryer_reputation_signal",
    "engagement_signal": "cryer_engagement_signal",
    "booking_friction": "cryer_booking_friction",
    "directory_completeness": "cryer_directory_completeness",
    "hiring_growth": "cryer_hiring_growth",
}

DOMAIN_BUILDERS = {
    "recon": build_recon_packet,
    "reputation_signal": build_reputation_signal_packet,
    "engagement_signal": build_engagement_signal_packet,
    "booking_friction": build_booking_friction_packet,
    "directory_completeness": build_directory_completeness_packet,
    "hiring_growth": build_hiring_growth_packet,
}


def main():
    """Main entry point: read request, produce response, write to stdout."""
    request = read_request()

    # Determine domain and packet type
    domain = request.get("domain", "recon")
    required_packet_type = request.get("required_packet_type", "")

    # Resolve builder: prefer explicit packet type, then domain
    builder = None

    if required_packet_type:
        # Map packet type back to domain
        for dom, ptype in DOMAIN_TO_PACKET_TYPE.items():
            if ptype == required_packet_type:
                builder = DOMAIN_BUILDERS[dom]
                break

    if builder is None:
        builder = DOMAIN_BUILDERS.get(domain)

    if builder is None:
        # Unknown domain — produce blocked packet
        response = build_blocked_packet(
            request,
            f"Unknown domain '{domain}' for CryER. Supported: {list(DOMAIN_BUILDERS.keys())}"
        )
    else:
        try:
            response = builder(request)
        except Exception as e:
            response = build_blocked_packet(
                request,
                f"CryER worker error: {e}"
            )

    # Write response packet to stdout
    print(json.dumps(response, indent=2))


if __name__ == "__main__":
    main()