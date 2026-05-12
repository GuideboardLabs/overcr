#!/usr/bin/env python3
"""
OverCR v0.0.5 Packet Validator

Validates subagent response packets against the schema defined in
orchestration/packet_validation_rules.md.

Usage:
    python validate_packet.py <packet_file.json> [packet_file2.json ...]
    python validate_packet.py --dir <directory_with_json_files>

Exits 0 if all packets pass, 1 if any fail.
Prints a JSON validation report for each packet.
"""

import json
import re
import sys
import os
from datetime import datetime, timezone
from pathlib import Path

# ──────────────────────────────────────────────
# Level 1: Structural Integrity
# ──────────────────────────────────────────────

REQUIRED_L1_FIELDS = {
    "packet_type": str,
    "version": str,
    "timestamp": str,
    "source": str,
    "target": str,
    "task_id": str,
    "summary": str,
}

VALID_SOURCES = {"cryer", "pyper", "coder", "knower"}

PACKET_TYPES_BY_SOURCE = {
    "cryer": {"cryer_recon", "cryer_update", "cryer_alert", "cryer_reputation_signal", "cryer_engagement_signal", "cryer_booking_friction", "cryer_directory_completeness", "cryer_hiring_growth"},
    "pyper": {"pyper_approval", "pyper_revision", "pyper_objection_response", "pyper_execution_plan", "pyper_execution_receipt", "pyper_execution_refusal"},
    "coder": {"coder_completion", "coder_blocked", "coder_diagnostic", "coder_patch_plan"},
    "knower": {"knower_research", "knower_assessment", "knower_myth_separation", "knower_claim_review", "knower_myth_fact"},
}

ALL_PACKET_TYPES = set()
for types in PACKET_TYPES_BY_SOURCE.values():
    ALL_PACKET_TYPES.update(types)


def validate_level1(packet, errors):
    """Validate structural integrity — required fields, types, basic constraints."""
    # Check required fields exist and have correct type
    for field, expected_type in REQUIRED_L1_FIELDS.items():
        if field not in packet:
            errors.append(f"Level 1: missing required field '{field}'")
        elif not isinstance(packet[field], expected_type):
            errors.append(f"Level 1: field '{field}' must be {expected_type.__name__}, got {type(packet[field]).__name__}")
        elif field == "summary" and not packet[field].strip():
            errors.append(f"Level 1: field '{field}' must be non-empty")

    # Validate version
    if "version" in packet and packet["version"] != "1.0":
        errors.append(f"Level 1: version must be '1.0', got '{packet['version']}'")

    # Validate target
    if "target" in packet and packet["target"] != "overcr":
        errors.append(f"Level 1: target must be 'overcr', got '{packet['target']}'")

    # Validate source
    if "source" in packet and packet["source"] not in VALID_SOURCES:
        errors.append(f"Level 1: source must be one of {VALID_SOURCES}, got '{packet['source']}'")

    # Validate task_id format
    if "task_id" in packet and not re.match(r'^task-\d{4}$', packet["task_id"]):
        errors.append(f"Level 1: task_id must match pattern 'task-NNNN', got '{packet['task_id']}'")


def validate_timestamp(ts, errors):
    """Validate ISO 8601 timestamp format."""
    # Try multiple ISO 8601 formats
    formats = [
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f%z",
    ]
    parsed = False
    for fmt in formats:
        try:
            datetime.strptime(ts, fmt)
            parsed = True
            break
        except ValueError:
            continue
    # Also try fromisoformat (Python 3.7+) as fallback
    if not parsed:
        try:
            datetime.fromisoformat(ts.replace("Z", "+00:00"))
            parsed = True
        except (ValueError, AttributeError):
            pass
    if not parsed:
        errors.append(f"Level 1: timestamp '{ts}' is not valid ISO 8601")


# ──────────────────────────────────────────────
# Level 2: Packet Type Registration
# ──────────────────────────────────────────────

def validate_level2(packet, errors):
    """Validate packet_type is registered for the given source."""
    ptype = packet.get("packet_type", "")
    source = packet.get("source", "")

    if ptype and ptype not in ALL_PACKET_TYPES:
        errors.append(f"Level 2: unknown packet_type '{ptype}'")
        return

    if source in PACKET_TYPES_BY_SOURCE:
        if ptype not in PACKET_TYPES_BY_SOURCE[source]:
            expected = PACKET_TYPES_BY_SOURCE[source]
            errors.append(f"Level 2: source '{source}' does not produce packet_type '{ptype}'. Expected one of: {expected}")


# ──────────────────────────────────────────────
# Level 3: Source-Packet Consistency
# ──────────────────────────────────────────────

def validate_level3(packet, errors):
    """Validate that the packet has the correct payload fields for its type."""
    ptype = packet.get("packet_type", "")
    source = packet.get("source", "")

    if source == "cryer":
        if ptype in ("cryer_recon", "cryer_update"):
            if "recon_data" not in packet:
                errors.append(f"Level 3: {ptype} must have 'recon_data' field")
        elif ptype == "cryer_alert":
            if "alert_type" not in packet:
                errors.append(f"Level 3: {ptype} must have 'alert_type' field")
        elif ptype == "cryer_reputation_signal":
            if "reputation_signal_data" not in packet:
                errors.append(f"Level 3: {ptype} must have 'reputation_signal_data' field")
        elif ptype == "cryer_engagement_signal":
            if "engagement_signal_data" not in packet:
                errors.append(f"Level 3: {ptype} must have 'engagement_signal_data' field")
        elif ptype == "cryer_booking_friction":
            if "booking_friction_data" not in packet:
                errors.append(f"Level 3: {ptype} must have 'booking_friction_data' field")
        elif ptype == "cryer_directory_completeness":
            if "directory_completeness_data" not in packet:
                errors.append(f"Level 3: {ptype} must have 'directory_completeness_data' field")
        elif ptype == "cryer_hiring_growth":
            if "hiring_growth_data" not in packet:
                errors.append(f"Level 3: {ptype} must have 'hiring_growth_data' field")

    elif source == "pyper":
        if ptype in ("pyper_approval", "pyper_revision"):
            if "draft_data" not in packet:
                errors.append(f"Level 3: {ptype} must have 'draft_data' field")
        elif ptype == "pyper_objection_response":
            if "prospect_entity" not in packet or "objection" not in packet or "response_draft" not in packet:
                errors.append(f"Level 3: {ptype} must have 'prospect_entity', 'objection', and 'response_draft' fields")
        elif ptype == "pyper_execution_plan":
            if "execution_plan_data" not in packet:
                errors.append(f"Level 3: {ptype} must have 'execution_plan_data' field")
        elif ptype == "pyper_execution_receipt":
            if "receipt_data" not in packet:
                errors.append(f"Level 3: {ptype} must have 'receipt_data' field")
        elif ptype == "pyper_execution_refusal":
            if "refusal_data" not in packet:
                errors.append(f"Level 3: {ptype} must have 'refusal_data' field")

    elif source == "coder":
        if ptype == "coder_completion":
            if "completion_data" not in packet:
                errors.append(f"Level 3: {ptype} must have 'completion_data' field")
        elif ptype == "coder_blocked":
            if "blockers" not in packet:
                errors.append(f"Level 3: {ptype} must have 'blockers' field")
        elif ptype == "coder_diagnostic":
            if "diagnostics" not in packet:
                errors.append(f"Level 3: {ptype} must have 'diagnostics' field")
        elif ptype == "coder_patch_plan":
            if "patch_plan_data" not in packet:
                errors.append(f"Level 3: {ptype} must have 'patch_plan_data' field")

    elif source == "knower":
        if ptype == "knower_research":
            if "research_data" not in packet:
                errors.append(f"Level 3: {ptype} must have 'research_data' field")
        elif ptype == "knower_assessment":
            if "assessment" not in packet:
                errors.append(f"Level 3: {ptype} must have 'assessment' field")
        elif ptype == "knower_myth_separation":
            if "myths" not in packet:
                errors.append(f"Level 3: {ptype} must have 'myths' field")
        elif ptype == "knower_claim_review":
            if "claim_review_data" not in packet:
                errors.append(f"Level 3: {ptype} must have 'claim_review_data' field")
        elif ptype == "knower_myth_fact":
            if "myth_fact_data" not in packet:
                errors.append(f"Level 3: {ptype} must have 'myth_fact_data' field")


# ──────────────────────────────────────────────
# Level 4: Approval Gate Enforcement
# ──────────────────────────────────────────────

def validate_level4(packet, errors, warnings):
    """Validate approval_required gates."""
    ptype = packet.get("packet_type", "")
    source = packet.get("source", "")
    approval = packet.get("approval_required", None)

    # PypER packets MUST have approval_required=true
    if source == "pyper":
        if approval is not True:
            errors.append("Level 4: PypER packet must have approval_required=true")

    # PypER execution plan MUST have execution_authority="none"
    if ptype == "pyper_execution_plan":
        if packet.get("execution_authority") != "none":
            errors.append("Level 4: pyper_execution_plan MUST have execution_authority='none' — PypER has no execution authority in inference mode")

    # CodER completion with breaking changes should have approval
    if ptype == "coder_completion":
        comp_data = packet.get("completion_data", {})
        deliverables = comp_data.get("deliverables", [])
        for d in deliverables:
            if d.get("breaking_changes") is True and approval is not True:
                warnings.append("Level 4: CodER packet with breaking_changes=true should have approval_required=true")
            if d.get("reversible") is False and approval is not True:
                warnings.append("Level 4: CodER packet with reversible=false should have approval_required=true")

    # CodER patch_plan MUST have approval_required=true (all file mutation requires approval)
    if ptype == "coder_patch_plan":
        if approval is not True:
            errors.append("Level 4: coder_patch_plan MUST have approval_required=true — all file mutation requires approval")


# ──────────────────────────────────────────────
# Level 5: Forbidden Action Flags
# ──────────────────────────────────────────────

OUTBOUND_PATTERN = re.compile(r'(?:contact|reach\.?out|dm\b|message\s+them)', re.IGNORECASE)
# Note: "email" and "call" are too common in legitimate contexts (e.g., evidence_citations).
# We check for "contact" as an instruction, not as a noun in citations.

# Governance override patterns: packets that claim self-granted authority over doctrine.
# Subagents cannot grant themselves permission, bypass approval, or redefine governance.
GOVERNANCE_OVERRIDE_PATTERN = re.compile(
    r'(?:'
    r'may\s+(?:submit|send|contact|reach|act|proceed|bypass|override)'  # "may submit contact forms"
    r'|permitted\s+to\b'              # "permitted to contact"
    r'|authorized\s+to\b'             # "authorized to bypass"
    r'|can\s+bypass\b'                 # "can bypass approval"
    r'|no\s+approval\s+(?:needed|required|necessary)'  # "no approval needed"
    r'|approval\s+not\s+required'      # "approval not required"
    r'|autonomous(?:ly)?\s+(?:action|execution|outreach)'  # "autonomous action"
    r'|override\s+(?:approval|doctrine|governance|gate)'  # "override approval gate"
    r'|self[- ]?approved'             # "self-approved"
    r')',
    re.IGNORECASE,
)

# v0.4.1: Browsing claim pattern — model output cannot claim live browsing occurred.
# Matches phrases like "I browsed", "I searched the web", "web search results",
# "from the internet", "live browsing", "live data", "real-time search"
BROWSING_CLAIM_PATTERN = re.compile(
    r'(?:'
    r'(?:i\s+)?(?:browsed|crawled|scraped|searched)\s+(?:the\s+)?(?:web|internet|net)'
    r'|web\s+search\s+(?:result|found|show)'
    r'|live\s+(?:browsing|data|search|crawl)'
    r'|real[- ]time\s+(?:search|data|browse|crawl|web)'
    r'|from\s+(?:the\s+)?internet'
    r'|online\s+(?:search|browse|crawl)'
    r')',
    re.IGNORECASE,
)

# v0.4.1: Direct routing claim pattern — model output cannot claim direct routing to subagent.
# Matches "route to pyper", "send to coder", "forward to knower", "target: pyper", etc.
DIRECT_ROUTING_PATTERN = re.compile(
    r'(?:'
    r'(?:route|send|forward|deliver|target|address)\s+(?:directly\s+)?(?:to\s+)?(?:pyper|coder|knower|cryer)'
    r'|target\s*:\s*(?:pyper|coder|knower|cryer)'
    r'|direct\s+handoff\s+to\s+(?:pyper|coder|knower|cryer)'
    r')',
    re.IGNORECASE,
)

# v0.7.0: Execution safety patterns for PypER execution planning packets.
# These catch forbidden commands in execution plan data that could cause
# shell injection, remote execution, package installation, or privilege
# escalation if the plan were executed without proper safeguards.

# Shell injection patterns — chained commands, subshells
SHELL_INJECTION_PATTERN = re.compile(
    r'(?:'
    r';\s*(?:rm|del|format|mkfs|dd|chmod|chown)\b'  # chained destructive commands
    r'|\b`[^`]*`'                                     # backtick subshell
    r'|\$\([^)]*\)'                                   # $() subshell
    r'|&&\s*(?:rm|del|format|mkfs|dd)\b'              # chained destructive via &&
    r')',
    re.IGNORECASE,
)

# Remote execution chain patterns — curl|bash, wget|sh, etc.
REMOTE_EXECUTION_PATTERN = re.compile(
    r'(?:'
    r'curl\s+.+?\|\s*(?:ba)?sh\b'
    r'|curl\s+.+?\|\s*(?:python3?|perl|ruby|node)\b'
    r'|wget\s+.+?\|\s*(?:ba)?sh\b'
    r'|wget\s+.+?\|\s*(?:python3?|perl|ruby|node)\b'
    r'|curl\s+.+?(?:--exec\b|-o\s+/dev/null)'
    r')',
    re.IGNORECASE,
)

# Package install patterns — apt, pip, npm, etc.
PACKAGE_INSTALL_PATTERN = re.compile(
    r'(?:'
    r'(?:apt|apt-get)\s+install\b'
    r'|\byum\s+install\b'
    r'|\bdnf\s+install\b'
    r'|\bpip(?:3)?\s+install\b'
    r'|\bnpm\s+install\b'
    r'|\byarn\s+add\b'
    r'|\bcargo\s+install\b'
    r'|\bgem\s+install\b'
    r'|\bbrew\s+install\b'
    r')',
    re.IGNORECASE,
)

# Privilege escalation patterns — sudo, su, chmod 777, etc.
PRIVILEGE_ESCALATION_PATTERN = re.compile(
    r'(?:'
    r'\bsudo\s+'
    r'|\bsu\s+(?:-|\broot\b)'
    r'|\bchmod\s+(?:777|666|7[0-7]{3})\b'
    r'|\bchown\s+\S+\s+\S+'
    r')',
    re.IGNORECASE,
)

# Deceptive execution claim pattern — claiming a command actually ran
DECEPTIVE_EXECUTION_PATTERN = re.compile(
    r'(?:'
    r'command\s+(?:was\s+)?executed\s+successfully'
    r'|script\s+ran\s+successfully'
    r'|execution\s+completed\s+without\s+error'
    r'|commands?\s+(?:were|was|have been)\s+(?:executed|run|applied)\s+successfully'
    r')',
    re.IGNORECASE,
)

def validate_level5(packet, errors):
    """Validate no forbidden patterns in non-draft packet types."""
    ptype = packet.get("packet_type", "")
    source = packet.get("source", "")

    # Check target is not another subagent
    if packet.get("target") != "overcr":
        errors.append(f"Level 5: target must be 'overcr', got '{packet.get('target')}' — direct subagent addressing is forbidden")

    # For non-PypER packets (PypER drafts legitimately contain outreach language)
    # check top-level instruction/constraint fields for outbound contact instructions
    if source != "pyper":
        # Recursively check string values for forbidden patterns
        _check_forbidden_strings(packet, errors, current_path="root", depth=0)

    # Check for governance override claims — packets cannot grant themselves authority
    _check_governance_overrides(packet, errors, current_path="root", depth=0)

    # v0.4.1: Check for browsing claims — model output cannot claim live browsing occurred
    _check_browsing_claims(packet, errors, current_path="root", depth=0)

    # v0.4.1: Check for direct routing claims — model output cannot route to another subagent
    # Only applies to non-audit_trail, non-raw_sources context (claims, not descriptions)
    _check_direct_routing_claims(packet, errors, current_path="root", depth=0)

    # v0.7.0: Check for execution safety violations in PypER execution plan packets
    # Shell injection, remote execution, package install, privilege escalation,
    # hidden subprocess execution, deceptive execution claims
    if ptype in ("pyper_execution_plan", "pyper_execution_receipt", "pyper_execution_refusal"):
        _check_execution_safety(packet, errors, current_path="root", depth=0)


# Whitelist paths where OUTBOUND_PATTERN matches are allowed (known enum values)
WHITELISTED_PATHS_FOR_OUTBOUND = frozenset({
    "friction_points[].type", "friction_points[].classification", "friction_points[].source_quality",
    "friction_points[].unknowns",  # Descriptive context
    "metrics[].type", "metrics[].classification", "metrics[].source_quality", "metrics[].unknowns",
    "signals[].type", "signals[].classification", "signals[].source_quality", "signals[].unknowns",
})

def _check_forbidden_strings(obj, errors, current_path, depth):
    """Recursively check string values for outbound contact instructions."""
    if depth > 5:  # Prevent deep recursion
        return
    if isinstance(obj, str):
        if OUTBOUND_PATTERN.search(obj):
            # Whitelist known enum values in CryER packet types
            # e.g., "contact_required" in friction_points[].type
            if "friction_points" in current_path or "metrics" in current_path or "signals" in current_path:
                # Check if this is the "type" field in a known enum context
                last_field = current_path.split(".")[-1] if current_path else ""
                if last_field == "type" or last_field == "classification" or last_field == "source_quality":
                    # Skip whitelisted enum fields
                    return
            # Allow if it's in audit_trail or raw_sources (descriptive context)
            if "audit_trail" not in current_path and "raw_sources" not in current_path and "evidence" not in current_path:
                errors.append(f"Level 5: potential outbound contact instruction at '{current_path}': '{obj[:80]}...'")
    elif isinstance(obj, dict):
        for k, v in obj.items():
            _check_forbidden_strings(v, errors, f"{current_path}.{k}", depth + 1)
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            _check_forbidden_strings(item, errors, f"{current_path}[{i}]", depth + 1)


def _check_governance_overrides(obj, errors, current_path, depth):
    """Recursively check string values for governance override claims.

    A subagent packet cannot grant itself authority that contradicts doctrine.
    This catches assertions like "may submit contact forms", "no approval needed",
    "authorized to bypass", etc. — language that claims the subagent has
    permission to override or skip governance controls.

    Exempt: audit_trail, raw_sources, evidence (descriptive context, not claims).
    """
    if depth > 5:
        return
    if isinstance(obj, str):
        if GOVERNANCE_OVERRIDE_PATTERN.search(obj):
            # Allow in audit_trail and raw_sources (descriptive context)
            if "audit_trail" not in current_path and "raw_sources" not in current_path:
                errors.append(
                    f"Level 5: governance override claim at '{current_path}': "
                    f"'{obj[:80]}...' — subagent cannot grant itself authority over doctrine"
                )
    elif isinstance(obj, dict):
        for k, v in obj.items():
            _check_governance_overrides(v, errors, f"{current_path}.{k}", depth + 1)
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            _check_governance_overrides(item, errors, f"{current_path}[{i}]", depth + 1)


def _check_browsing_claims(obj, errors, current_path, depth):
    """v0.4.1: Recursively check for browsing claims — model output cannot claim live browsing.

    Model output that claims to have browsed the web or accessed live data is
    a governance violation. The worker only receives provided input text — it
    cannot and does not browse.

    Exempt: audit_trail, raw_sources, evidence (descriptive context).
    """
    if depth > 5:
        return
    if isinstance(obj, str):
        if BROWSING_CLAIM_PATTERN.search(obj):
            # Allow in audit_trail, raw_sources, evidence (descriptive context)
            if "audit_trail" not in current_path and "raw_sources" not in current_path and "evidence" not in current_path:
                errors.append(
                    f"Level 5: browsing claim at '{current_path}': "
                    f"'{obj[:80]}...' — model output cannot claim live browsing occurred"
                )
    elif isinstance(obj, dict):
        for k, v in obj.items():
            _check_browsing_claims(v, errors, f"{current_path}.{k}", depth + 1)
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            _check_browsing_claims(item, errors, f"{current_path}[{i}]", depth + 1)


def _check_direct_routing_claims(obj, errors, current_path, depth):
    """v0.4.1: Recursively check for direct routing claims — model output cannot route to another subagent.

    Model output that claims to route directly to another subagent (e.g.,
    "route to pyper", "target: coder") is a governance violation. All routing
    goes through OverCR, never direct.

    Exempt: audit_trail, raw_sources (descriptive context).
    """
    if depth > 5:
        return
    if isinstance(obj, str):
        if DIRECT_ROUTING_PATTERN.search(obj):
            # Allow in audit_trail and raw_sources (descriptive context)
            if "audit_trail" not in current_path and "raw_sources" not in current_path:
                errors.append(
                    f"Level 5: direct routing claim at '{current_path}': "
                    f"'{obj[:80]}...' — model output cannot route directly to another subagent"
                )
    elif isinstance(obj, dict):
        for k, v in obj.items():
            _check_direct_routing_claims(v, errors, f"{current_path}.{k}", depth + 1)
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            _check_direct_routing_claims(item, errors, f"{current_path}[{i}]", depth + 1)


def _check_execution_safety(obj, errors, current_path, depth):
    """v0.7.0: Check for execution safety violations in PypER execution planning packets.

    Catches:
      - Shell injection patterns (chained destructive commands, subshells)
      - Remote execution chains (curl|bash, wget|sh)
      - Package install attempts (apt install, pip install, etc.)
      - Privilege escalation attempts (sudo, su root, chmod 777, etc.)
      - Hidden subprocess execution (subprocess.run, os.system)
      - Deceptive execution claims (claiming commands actually ran)

    Exempt: audit_trail (descriptive context).
    Does NOT exempt execution_plan_data.steps[].command — that is the
    primary field to check for safety violations.
    """
    if depth > 5:
        return
    if isinstance(obj, str):
        # Shell injection
        if SHELL_INJECTION_PATTERN.search(obj):
            if "audit_trail" not in current_path:
                errors.append(
                    f"Level 5: shell injection pattern at '{current_path}': "
                    f"'{obj[:80]}...' — chained destructive commands or subshell execution forbidden"
                )
        # Remote execution
        if REMOTE_EXECUTION_PATTERN.search(obj):
            if "audit_trail" not in current_path:
                errors.append(
                    f"Level 5: remote execution chain at '{current_path}': "
                    f"'{obj[:80]}...' — curl|bash and wget|sh patterns forbidden"
                )
        # Package install
        if PACKAGE_INSTALL_PATTERN.search(obj):
            if "audit_trail" not in current_path:
                errors.append(
                    f"Level 5: package install pattern at '{current_path}': "
                    f"'{obj[:80]}...' — package installation commands forbidden in execution plans"
                )
        # Privilege escalation
        if PRIVILEGE_ESCALATION_PATTERN.search(obj):
            if "audit_trail" not in current_path:
                errors.append(
                    f"Level 5: privilege escalation pattern at '{current_path}': "
                    f"'{obj[:80]}...' — sudo, su, chmod 777 escalation forbidden"
                )
        # Deceptive execution claims
        if DECEPTIVE_EXECUTION_PATTERN.search(obj):
            if "audit_trail" not in current_path:
                errors.append(
                    f"Level 5: deceptive execution claim at '{current_path}': "
                    f"'{obj[:80]}...' — PypER may not claim commands actually executed"
                )
    elif isinstance(obj, dict):
        for k, v in obj.items():
            _check_execution_safety(v, errors, f"{current_path}.{k}", depth + 1)
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            _check_execution_safety(item, errors, f"{current_path}[{i}]", depth + 1)

def validate_level6(packet, errors):
    """Validate type-specific required payload fields."""
    ptype = packet.get("packet_type", "")

    validators = {
        "cryer_recon": _validate_cryer_recon,
        "cryer_update": _validate_cryer_update,
        "cryer_alert": _validate_cryer_alert,
        "cryer_reputation_signal": _validate_cryer_reputation_signal,
        "cryer_engagement_signal": _validate_cryer_engagement_signal,
        "cryer_booking_friction": _validate_cryer_booking_friction,
        "cryer_directory_completeness": _validate_cryer_directory_completeness,
        "cryer_hiring_growth": _validate_cryer_hiring_growth,
        "pyper_approval": _validate_pyper_approval,
        "pyper_revision": _validate_pyper_revision,
        "pyper_objection_response": _validate_pyper_objection_response,
        "pyper_execution_plan": _validate_pyper_execution_plan,
        "pyper_execution_receipt": _validate_pyper_execution_receipt,
        "pyper_execution_refusal": _validate_pyper_execution_refusal,
        "coder_completion": _validate_coder_completion,
        "coder_blocked": _validate_coder_blocked,
        "coder_diagnostic": _validate_coder_diagnostic,
        "coder_patch_plan": _validate_coder_patch_plan,
        "knower_research": _validate_knower_research,
        "knower_assessment": _validate_knower_assessment,
        "knower_myth_separation": _validate_knower_myth_separation,
        "knower_claim_review": _validate_knower_claim_review,
        "knower_myth_fact": _validate_knower_myth_fact,
    }

    validator = validators.get(ptype)
    if validator:
        validator(packet, errors)

    # v0.4.1: Validate inference governance constraints for all packets
    _validate_inference_governance(packet, errors)


def _require(packet, path, errors, check_fn=None, field_name=None):
    """Check that a nested field exists and optionally passes a check."""
    parts = path.split(".")
    obj = packet
    current_path = ""
    for part in parts:
        # Handle array indices like [0]
        if part.startswith("[") and part.endswith("]"):
            idx = int(part[1:-1])
            if not isinstance(obj, list) or idx >= len(obj):
                errors.append(f"Level 6: missing required field '{field_name or path}'")
                return
            obj = obj[idx]
            current_path += part
        else:
            if not isinstance(obj, dict) or part not in obj:
                errors.append(f"Level 6: missing required field '{field_name or path}'")
                return
            obj = obj[part]
            current_path += f".{part}" if current_path else part

    if check_fn and not check_fn(obj):
        errors.append(f"Level 6: field '{field_name or path}' failed validation")


# --- CryER ---

def _validate_cryer_recon(packet, errors):
    recon = packet.get("recon_data", {})
    targets = recon.get("targets", [])
    if not targets:
        errors.append("Level 6: cryer_recon must have at least 1 target in recon_data.targets")
    for i, t in enumerate(targets):
        if not t.get("entity"):
            errors.append(f"Level 6: target[{i}].entity must be non-empty")
        if t.get("type") not in ("business", "person", "domain", "directory"):
            errors.append(f"Level 6: target[{i}].type must be business/person/domain/directory, got '{t.get('type')}'")
        sig = t.get("signals", {})
        rep = sig.get("reputation", {})
        if not isinstance(rep.get("yield_score"), int) or not (0 <= rep.get("yield_score", -1) <= 100):
            errors.append(f"Level 6: target[{i}].signals.reputation.yield_score must be integer 0-100")
        if not isinstance(rep.get("confidence"), int) or not (0 <= rep.get("confidence", -1) <= 100):
            errors.append(f"Level 6: target[{i}].signals.reputation.confidence must be integer 0-100")
        sources = t.get("raw_sources", [])
        if not sources:
            errors.append(f"Level 6: target[{i}].raw_sources must have at least 1 source")
    audit = packet.get("audit_trail", {})
    if not audit.get("collection_timestamps"):
        errors.append("Level 6: audit_trail.collection_timestamps must have at least 1 timestamp")
    if not audit.get("methods_used"):
        errors.append("Level 6: audit_trail.methods_used must have at least 1 method")


def _validate_cryer_update(packet, errors):
    _validate_cryer_recon(packet, errors)  # Same base requirements
    if not packet.get("upstream_task_id"):
        errors.append("Level 6: cryer_update must have upstream_task_id referencing a prior task")
    if not packet.get("changes_summary"):
        errors.append("Level 6: cryer_update must have non-empty changes_summary")


def _validate_cryer_alert(packet, errors):
    if packet.get("alert_type") not in ("hiring_surge", "reputation_drop", "listing_change", "major_event"):
        errors.append(f"Level 6: alert_type must be one of hiring_surge/reputation_drop/listing_change/major_event, got '{packet.get('alert_type')}'")
    if packet.get("severity") not in ("high", "medium", "low"):
        errors.append(f"Level 6: severity must be high/medium/low, got '{packet.get('severity')}'")
    if not packet.get("entity"):
        errors.append("Level 6: cryer_alert must have non-empty entity")
    if not packet.get("description"):
        errors.append("Level 6: cryer_alert must have non-empty description")
    if not packet.get("evidence"):
        errors.append("Level 6: cryer_alert must have at least 1 evidence item")
    if not packet.get("recommended_action"):
        errors.append("Level 6: cryer_alert must have non-empty recommended_action")


def _validate_cryer_reputation_signal(packet, errors):
    """Validate cryer_reputation_signal packet — L6 field-level checks."""
    data = packet.get("reputation_signal_data", {})
    _require(packet, "reputation_signal_data.entity", errors, field_name="reputation_signal_data.entity")
    if not data.get("entity"):
        errors.append("Level 6: cryer_reputation_signal must have non-empty reputation_signal_data.entity")
    signals = data.get("signals", [])
    if not signals:
        errors.append("Level 6: cryer_reputation_signal must have at least 1 signal in reputation_signal_data.signals")
    valid_signal_types = ("rating", "review_volume", "sentiment", "accreditation", "mention_frequency", "complaint_pattern")
    valid_classifications = ("observed", "inferred", "assumed", "unknown")
    valid_source_qualities = ("primary", "secondary", "tertiary", "unverified")
    for i, s in enumerate(signals):
        if s.get("type") not in valid_signal_types:
            errors.append(f"Level 6: signal[{i}].type must be one of {valid_signal_types}, got '{s.get('type')}'")
        if s.get("classification") not in valid_classifications:
            errors.append(f"Level 6: signal[{i}].classification must be one of {valid_classifications}, got '{s.get('classification')}'")
        if not isinstance(s.get("confidence"), int) or not (0 <= s.get("confidence", -1) <= 100):
            errors.append(f"Level 6: signal[{i}].confidence must be integer 0-100, got '{s.get('confidence')}'")
        if not s.get("detail"):
            errors.append(f"Level 6: signal[{i}].detail must be non-empty")
        if s.get("source_quality") not in valid_source_qualities:
            errors.append(f"Level 6: signal[{i}].source_quality must be one of {valid_source_qualities}, got '{s.get('source_quality')}'")
        if "unknowns" not in s:
            errors.append(f"Level 6: signal[{i}].unknowns field is required (may be empty list)")
    if not isinstance(data.get("yield_score"), int) or not (0 <= data.get("yield_score", -1) <= 100):
        errors.append("Level 6: reputation_signal_data.yield_score must be integer 0-100")
    if not data.get("confidence_notes"):
        errors.append("Level 6: reputation_signal_data.confidence_notes must be non-empty")
    if data.get("recommended_routing") != "overcr":
        errors.append(f"Level 6: reputation_signal_data.recommended_routing must be 'overcr', got '{data.get('recommended_routing')}'")


def _validate_cryer_engagement_signal(packet, errors):
    """Validate cryer_engagement_signal packet — L6 field-level checks."""
    data = packet.get("engagement_signal_data", {})
    if not data.get("entity"):
        errors.append("Level 6: cryer_engagement_signal must have non-empty engagement_signal_data.entity")
    metrics = data.get("metrics", [])
    if not metrics:
        errors.append("Level 6: cryer_engagement_signal must have at least 1 metric in engagement_signal_data.metrics")
    valid_metric_types = ("review_count", "average_rating", "response_rate", "recency", "platform_presence")
    valid_classifications = ("observed", "inferred", "assumed", "unknown")
    valid_source_qualities = ("primary", "secondary", "tertiary", "unverified")
    for i, m in enumerate(metrics):
        if m.get("type") not in valid_metric_types:
            errors.append(f"Level 6: metric[{i}].type must be one of {valid_metric_types}, got '{m.get('type')}'")
        if m.get("classification") not in valid_classifications:
            errors.append(f"Level 6: metric[{i}].classification must be one of {valid_classifications}, got '{m.get('classification')}'")
        if not m.get("value"):
            errors.append(f"Level 6: metric[{i}].value must be non-empty")
        if not isinstance(m.get("confidence"), int) or not (0 <= m.get("confidence", -1) <= 100):
            errors.append(f"Level 6: metric[{i}].confidence must be integer 0-100, got '{m.get('confidence')}'")
        if m.get("source_quality") not in valid_source_qualities:
            errors.append(f"Level 6: metric[{i}].source_quality must be one of {valid_source_qualities}, got '{m.get('source_quality')}'")
        if "unknowns" not in m:
            errors.append(f"Level 6: metric[{i}].unknowns field is required (may be empty list)")
    if not data.get("engagement_summary"):
        errors.append("Level 6: engagement_signal_data.engagement_summary must be non-empty")
    if data.get("recommended_routing") != "overcr":
        errors.append(f"Level 6: engagement_signal_data.recommended_routing must be 'overcr', got '{data.get('recommended_routing')}'")


def _validate_cryer_booking_friction(packet, errors):
    """Validate cryer_booking_friction packet — L6 field-level checks."""
    data = packet.get("booking_friction_data", {})
    if not data.get("entity"):
        errors.append("Level 6: cryer_booking_friction must have non-empty booking_friction_data.entity")
    friction_points = data.get("friction_points", [])
    if not friction_points:
        errors.append("Level 6: cryer_booking_friction must have at least 1 friction point in booking_friction_data.friction_points")
    valid_friction_types = ("limited_hours", "no_online_booking", "complex_scheduling", "high_cancellation_penalty", "opaque_pricing", "contact_required", "poor_availability_info", "ux_barrier")
    valid_classifications = ("observed", "inferred", "assumed", "unknown")
    valid_source_qualities = ("primary", "secondary", "tertiary", "unverified")
    for i, f in enumerate(friction_points):
        if f.get("type") not in valid_friction_types:
            errors.append(f"Level 6: friction_point[{i}].type must be one of {valid_friction_types}, got '{f.get('type')}'")
        if f.get("classification") not in valid_classifications:
            errors.append(f"Level 6: friction_point[{i}].classification must be one of {valid_classifications}, got '{f.get('classification')}'")
        if not isinstance(f.get("confidence"), int) or not (0 <= f.get("confidence", -1) <= 100):
            errors.append(f"Level 6: friction_point[{i}].confidence must be integer 0-100, got '{f.get('confidence')}'")
        if not f.get("detail"):
            errors.append(f"Level 6: friction_point[{i}].detail must be non-empty")
        if f.get("source_quality") not in valid_source_qualities:
            errors.append(f"Level 6: friction_point[{i}].source_quality must be one of {valid_source_qualities}, got '{f.get('source_quality')}'")
        if "unknowns" not in f:
            errors.append(f"Level 6: friction_point[{i}].unknowns field is required (may be empty list)")
    if not data.get("friction_summary"):
        errors.append("Level 6: booking_friction_data.friction_summary must be non-empty")
    if data.get("recommended_routing") != "overcr":
        errors.append(f"Level 6: booking_friction_data.recommended_routing must be 'overcr', got '{data.get('recommended_routing')}'")


def _validate_cryer_directory_completeness(packet, errors):
    """Validate cryer_directory_completeness packet — L6 field-level checks."""
    data = packet.get("directory_completeness_data", {})
    if not data.get("entity"):
        errors.append("Level 6: cryer_directory_completeness must have non-empty directory_completeness_data.entity")
    if not isinstance(data.get("present_fields"), list):
        errors.append("Level 6: directory_completeness_data.present_fields must be a list")
    if not isinstance(data.get("missing_fields"), list):
        errors.append("Level 6: directory_completeness_data.missing_fields must be a list")
    if not isinstance(data.get("completeness_score"), int) or not (0 <= data.get("completeness_score", -1) <= 100):
        errors.append("Level 6: directory_completeness_data.completeness_score must be integer 0-100")
    valid_classifications = ("observed", "inferred", "assumed", "unknown")
    if data.get("classification") not in valid_classifications:
        errors.append(f"Level 6: directory_completeness_data.classification must be one of {valid_classifications}, got '{data.get('classification')}'")
    if not isinstance(data.get("confidence"), int) or not (0 <= data.get("confidence", -1) <= 100):
        errors.append(f"Level 6: directory_completeness_data.confidence must be integer 0-100, got '{data.get('confidence')}'")
    if data.get("recommended_routing") != "overcr":
        errors.append(f"Level 6: directory_completeness_data.recommended_routing must be 'overcr', got '{data.get('recommended_routing')}'")
    valid_source_qualities = ("primary", "secondary", "tertiary", "unverified")
    if data.get("source_quality") not in valid_source_qualities:
        errors.append(f"Level 6: directory_completeness_data.source_quality must be one of {valid_source_qualities}, got '{data.get('source_quality')}'")
    if "unknowns" not in data:
        errors.append("Level 6: directory_completeness_data.unknowns field is required (may be empty list)")


def _validate_cryer_hiring_growth(packet, errors):
    """Validate cryer_hiring_growth packet — L6 field-level checks."""
    data = packet.get("hiring_growth_data", {})
    if not data.get("entity"):
        errors.append("Level 6: cryer_hiring_growth must have non-empty hiring_growth_data.entity")
    signals = data.get("signals", [])
    if not signals:
        errors.append("Level 6: cryer_hiring_growth must have at least 1 signal in hiring_growth_data.signals")
    valid_signal_types = ("job_posting", "growth_indication", "expansion_signal", "hiring_surge", "department_opening", "role_specific")
    valid_classifications = ("observed", "inferred", "assumed", "unknown")
    valid_source_qualities = ("primary", "secondary", "tertiary", "unverified")
    for i, s in enumerate(signals):
        if s.get("type") not in valid_signal_types:
            errors.append(f"Level 6: signal[{i}].type must be one of {valid_signal_types}, got '{s.get('type')}'")
        if s.get("classification") not in valid_classifications:
            errors.append(f"Level 6: signal[{i}].classification must be one of {valid_classifications}, got '{s.get('classification')}'")
        if not isinstance(s.get("confidence"), int) or not (0 <= s.get("confidence", -1) <= 100):
            errors.append(f"Level 6: signal[{i}].confidence must be integer 0-100, got '{s.get('confidence')}'")
        if not s.get("detail"):
            errors.append(f"Level 6: signal[{i}].detail must be non-empty")
        if s.get("source_quality") not in valid_source_qualities:
            errors.append(f"Level 6: signal[{i}].source_quality must be one of {valid_source_qualities}, got '{s.get('source_quality')}'")
        if "unknowns" not in s:
            errors.append(f"Level 6: signal[{i}].unknowns field is required (may be empty list)")
    if not data.get("growth_summary"):
        errors.append("Level 6: hiring_growth_data.growth_summary must be non-empty")
    if data.get("recommended_routing") != "overcr":
        errors.append(f"Level 6: hiring_growth_data.recommended_routing must be 'overcr', got '{data.get('recommended_routing')}'")


# --- PypER ---

def _validate_pyper_prospect(prospect, idx, errors):
    if not prospect.get("entity"):
        errors.append(f"Level 6: prospect[{idx}].entity must be non-empty")
    if prospect.get("approach_type") not in ("cold_email", "warm_intro", "follow_up", "proposal", "objection_response"):
        errors.append(f"Level 6: prospect[{idx}].approach_type invalid, got '{prospect.get('approach_type')}'")
    drafts = prospect.get("drafts", [])
    if not drafts:
        errors.append(f"Level 6: prospect[{idx}] must have at least 1 draft")
    for j, d in enumerate(drafts):
        if not d.get("body"):
            errors.append(f"Level 6: prospect[{idx}].drafts[{j}].body must be non-empty")
        if not d.get("evidence_citations"):
            errors.append(f"Level 6: prospect[{idx}].drafts[{j}].evidence_citations must have at least 1 citation")


def _validate_pyper_approval(packet, errors):
    draft_data = packet.get("draft_data", {})
    prospects = draft_data.get("prospects", [])
    if not prospects:
        errors.append("Level 6: pyper_approval must have at least 1 prospect in draft_data.prospects")
    for i, p in enumerate(prospects):
        _validate_pyper_prospect(p, i, errors)
    # approval_required=true is checked in Level 4
    audit = packet.get("audit_trail", {})
    if not audit.get("upstream_sources"):
        errors.append("Level 6: audit_trail.upstream_sources must have at least 1 source task ID")


def _validate_pyper_revision(packet, errors):
    _validate_pyper_approval(packet, errors)
    if not packet.get("revision_of"):
        errors.append("Level 6: pyper_revision must have revision_of referencing prior task")
    if not packet.get("revision_reason"):
        errors.append("Level 6: pyper_revision must have non-empty revision_reason")


def _validate_pyper_objection_response(packet, errors):
    if not packet.get("prospect_entity"):
        errors.append("Level 6: pyper_objection_response must have non-empty prospect_entity")
    if not packet.get("objection"):
        errors.append("Level 6: pyper_objection_response must have non-empty objection")
    if not packet.get("response_draft"):
        errors.append("Level 6: pyper_objection_response must have non-empty response_draft")
    if not packet.get("evidence_citations"):
        errors.append("Level 6: pyper_objection_response must have at least 1 evidence_citation")


def _validate_pyper_execution_plan(packet, errors):
    """Validate pyper_execution_plan packet — L6 field-level checks."""
    ep = packet.get("execution_plan_data", {})
    if not ep:
        errors.append("Level 6: pyper_execution_plan must have non-empty execution_plan_data")
        return

    # plan_description required
    if not ep.get("plan_description"):
        errors.append("Level 6: execution_plan_data.plan_description must be non-empty")

    # entity required
    if not ep.get("entity"):
        errors.append("Level 6: execution_plan_data.entity must be non-empty")

    # steps required, at least 1
    steps = ep.get("steps", [])
    if not steps:
        errors.append("Level 6: pyper_execution_plan must have at least 1 step in execution_plan_data.steps")
    for i, step in enumerate(steps):
        if step.get("step_index") is None:
            errors.append(f"Level 6: step[{i}].step_index is required")
        if not step.get("description"):
            errors.append(f"Level 6: step[{i}].description must be non-empty")
        if step.get("safety_classification") not in ("safe", "forbidden"):
            errors.append(f"Level 6: step[{i}].safety_classification must be 'safe' or 'forbidden', got '{step.get('safety_classification')}'")

    # risk_level validation
    risk_level = ep.get("risk_level")
    if risk_level and risk_level not in ("low", "medium", "high"):
        errors.append(f"Level 6: execution_plan_data.risk_level must be low/medium/high, got '{risk_level}'")

    # dependency_analysis required
    dep = ep.get("dependency_analysis", {})
    if not dep:
        errors.append("Level 6: pyper_execution_plan.execution_plan_data.dependency_analysis is required")

    # dry_run_summary required
    if not ep.get("dry_run_summary"):
        errors.append("Level 6: execution_plan_data.dry_run_summary must be non-empty")

    # rollback_plan required
    if not ep.get("rollback_plan"):
        errors.append("Level 6: execution_plan_data.rollback_plan must be non-empty")

    # sandbox_recommendation required
    if not ep.get("sandbox_recommendation"):
        errors.append("Level 6: execution_plan_data.sandbox_recommendation must be non-empty")

    # Audit trail: execution_authority must be "none"
    audit = packet.get("audit_trail", {})
    if isinstance(audit, dict):
        if audit.get("execution_authority") not in (None, "none"):
            errors.append(f"Level 6: audit_trail.execution_authority must be 'none' for PypER execution plans, got '{audit.get('execution_authority')}'")

    # approval_required must be true (defense in depth with L4)
    if packet.get("approval_required") is not True:
        errors.append("Level 6: pyper_execution_plan must have approval_required=true")

    # execution_authority at top level must be "none"
    if packet.get("execution_authority") not in (None, "none"):
        errors.append(f"Level 6: pyper_execution_plan.execution_authority must be 'none', got '{packet.get('execution_authority')}'")


def _validate_pyper_execution_receipt(packet, errors):
    """Validate pyper_execution_receipt packet — L6 field-level checks."""
    rd = packet.get("receipt_data", {})
    if not rd:
        errors.append("Level 6: pyper_execution_plan must have non-empty receipt_data")
        return

    # execution_type must be "simulated" — PypER receipts are always simulated
    if rd.get("execution_type") != "simulated":
        errors.append(f"Level 6: receipt_data.execution_type must be 'simulated' — PypER may not claim real execution, got '{rd.get('execution_type')}'")

    # step_receipts required
    step_receipts = rd.get("step_receipts", [])
    if not step_receipts:
        errors.append("Level 6: pyper_execution_receipt must have at least 1 step_receipt in receipt_data.step_receipts")
    for i, sr in enumerate(step_receipts):
        # actual_execution must be False — PypER never claims real execution
        if sr.get("actual_execution") is True:
            errors.append(f"Level 6: step_receipt[{i}].actual_execution must be false — PypER may not claim commands actually executed")
        if sr.get("step_index") is None:
            errors.append(f"Level 6: step_receipt[{i}].step_index is required")

    # overall_result must mention "SIMULATED"
    overall = rd.get("overall_result", "")
    if overall and "SIMULATED" not in overall:
        errors.append("Level 6: receipt_data.overall_result must contain 'SIMULATED' — receipts may only describe dry-run results")

    # side_effects must be empty
    side_effects = rd.get("side_effects", [])
    if isinstance(side_effects, list) and len(side_effects) > 0:
        errors.append("Level 6: receipt_data.side_effects must be empty — simulated execution has no side effects")

    # Audit: execution_authority must be "none"
    audit = packet.get("audit_trail", {})
    if isinstance(audit, dict):
        if audit.get("execution_authority") not in (None, "none"):
            errors.append(f"Level 6: audit_trail.execution_authority must be 'none', got '{audit.get('execution_authority')}'")


def _validate_pyper_execution_refusal(packet, errors):
    """Validate pyper_execution_refusal packet — L6 field-level checks."""
    rd = packet.get("refusal_data", {})
    if not rd:
        errors.append("Level 6: pyper_execution_refusal must have non-empty refusal_data")
        return

    # reason required
    if not rd.get("reason"):
        errors.append("Level 6: refusal_data.reason must be non-empty")

    # refusal_category required
    if not rd.get("refusal_category"):
        errors.append("Level 6: refusal_data.refusal_category must be non-empty")
    valid_categories = ("unsafe_command", "package_install_forbidden", "remote_execution_forbidden",
                        "privilege_escalation_forbidden", "governance_violation",
                        "sovereignty_violation", "autonomous_execution_forbidden", "safety_violation")
    if rd.get("refusal_category") and rd["refusal_category"] not in valid_categories:
        errors.append(f"Level 6: refusal_data.refusal_category must be one of {valid_categories}, got '{rd.get('refusal_category')}'")

    # operator_action_required must be True
    if rd.get("operator_action_required") is not True:
        errors.append("Level 6: refusal_data.operator_action_required must be true")

    # approval_required must be true
    if packet.get("approval_required") is not True:
        errors.append("Level 6: pyper_execution_refusal must have approval_required=true")


# --- CodER ---

def _validate_coder_completion(packet, errors):
    comp = packet.get("completion_data", {})
    deliverables = comp.get("deliverables", [])
    if not deliverables:
        errors.append("Level 6: coder_completion must have at least 1 deliverable")
    valid_types = {"code", "script", "test", "fix", "config", "automation", "documentation"}
    for i, d in enumerate(deliverables):
        if d.get("type") not in valid_types:
            errors.append(f"Level 6: deliverable[{i}].type must be one of {valid_types}, got '{d.get('type')}'")
        if not d.get("path"):
            errors.append(f"Level 6: deliverable[{i}].path must be non-empty")
        if "reversible" not in d:
            errors.append(f"Level 6: deliverable[{i}].reversible is required (boolean)")
    audit = packet.get("audit_trail", {})
    if not audit.get("files_modified"):
        errors.append("Level 6: audit_trail.files_modified must have at least 1 path")
    if not audit.get("rollback_instructions"):
        errors.append("Level 6: audit_trail.rollback_instructions must be non-empty")


def _validate_coder_blocked(packet, errors):
    blockers = packet.get("blockers", [])
    if not blockers:
        errors.append("Level 6: coder_blocked must have at least 1 blocker")
    valid_types = {"missing_dependency", "unclear_spec", "needs_research", "scope_ambiguity", "permission_denied"}
    for i, b in enumerate(blockers):
        if b.get("type") not in valid_types:
            errors.append(f"Level 6: blocker[{i}].type must be one of {valid_types}, got '{b.get('type')}'")
        if not b.get("description"):
            errors.append(f"Level 6: blocker[{i}].description must be non-empty")


def _validate_coder_diagnostic(packet, errors):
    diagnostics = packet.get("diagnostics", [])
    if not diagnostics:
        errors.append("Level 6: coder_diagnostic must have at least 1 diagnostic")
    for i, d in enumerate(diagnostics):
        if not d.get("issue"):
            errors.append(f"Level 6: diagnostic[{i}].issue must be non-empty")
        if d.get("severity") not in ("critical", "high", "medium", "low"):
            errors.append(f"Level 6: diagnostic[{i}].severity must be critical/high/medium/low, got '{d.get('severity')}'")


def _validate_coder_patch_plan(packet, errors):
    """Validate coder_patch_plan packet — L6 field-level checks."""
    pp = packet.get("patch_plan_data", {})
    if not pp:
        errors.append("Level 6: coder_patch_plan must have non-empty patch_plan_data")
        return

    # code_inspection_summary required
    if not pp.get("code_inspection_summary"):
        errors.append("Level 6: coder_patch_plan.patch_plan_data.code_inspection_summary must be non-empty")

    # bug_diagnosis required
    diag = pp.get("bug_diagnosis", {})
    if not diag:
        errors.append("Level 6: coder_patch_plan.patch_plan_data.bug_diagnosis is required")
    else:
        if not diag.get("summary"):
            errors.append("Level 6: bug_diagnosis.summary must be non-empty")
        if not diag.get("root_cause"):
            errors.append("Level 6: bug_diagnosis.root_cause must be non-empty")
        conf = diag.get("confidence")
        if conf is not None and (not isinstance(conf, (int, float)) or conf < 0.0 or conf > 1.0):
            errors.append(f"Level 6: bug_diagnosis.confidence must be 0.0-1.0, got {conf}")

    # patch_plan required
    plan = pp.get("patch_plan", {})
    if not plan:
        errors.append("Level 6: coder_patch_plan.patch_plan_data.patch_plan is required")
    else:
        if not plan.get("description"):
            errors.append("Level 6: patch_plan.description must be non-empty")
        if not isinstance(plan.get("files_to_modify"), list) or len(plan.get("files_to_modify", [])) < 1:
            errors.append("Level 6: patch_plan.files_to_modify must have at least 1 file")
        if plan.get("estimated_complexity") not in (None, "low", "medium", "high"):
            errors.append(f"Level 6: patch_plan.estimated_complexity must be low/medium/high, got '{plan.get('estimated_complexity')}'")

    # proposed_diff required
    if not pp.get("proposed_diff"):
        errors.append("Level 6: coder_patch_plan.patch_plan_data.proposed_diff must be non-empty")

    # test_plan required
    tp = pp.get("test_plan", {})
    if not tp:
        errors.append("Level 6: coder_patch_plan.patch_plan_data.test_plan is required")
    else:
        if not isinstance(tp.get("test_cases"), list) or len(tp.get("test_cases", [])) < 1:
            errors.append("Level 6: test_plan.test_cases must have at least 1 test case")

    # rollback_plan required
    if not pp.get("rollback_plan"):
        errors.append("Level 6: coder_patch_plan.patch_plan_data.rollback_plan must be non-empty")

    # risk_notes required
    risk = pp.get("risk_notes", {})
    if not risk:
        errors.append("Level 6: coder_patch_plan.patch_plan_data.risk_notes is required")
    else:
        if risk.get("level") not in ("low", "medium", "high"):
            errors.append(f"Level 6: risk_notes.level must be low/medium/high, got '{risk.get('level')}'")
        if not isinstance(risk.get("factors"), list) or len(risk.get("factors", [])) < 1:
            errors.append("Level 6: risk_notes.factors must have at least 1 factor")
        if not isinstance(risk.get("mitigations"), list) or len(risk.get("mitigations", [])) < 1:
            errors.append("Level 6: risk_notes.mitigations must have at least 1 mitigation")

    # audit_trail.files_modified must be empty (inference mode never modifies files)
    audit = packet.get("audit_trail", {})
    if isinstance(audit.get("files_modified"), list) and len(audit["files_modified"]) > 0:
        # files_modified in a patch_plan is advisory-only; warning, not error
        pass


# --- KnowER ---

def _validate_knower_research(packet, errors):
    rdata = packet.get("research_data", {})
    if not rdata.get("topic"):
        errors.append("Level 6: knower_research must have non-empty research_data.topic")
    findings = rdata.get("findings", [])
    if not findings:
        errors.append("Level 6: knower_research must have at least 1 finding")
    for i, f in enumerate(findings):
        if not f.get("claim"):
            errors.append(f"Level 6: finding[{i}].claim must be non-empty")
        if f.get("confidence") not in (1, 2, 3, 4):
            errors.append(f"Level 6: finding[{i}].confidence must be 1/2/3/4, got '{f.get('confidence')}'")
        if not f.get("sources"):
            errors.append(f"Level 6: finding[{i}].sources must have at least 1 source")
        if "gaps" not in f:
            errors.append(f"Level 6: finding[{i}].gaps field is required (may be empty list)")
    audit = packet.get("audit_trail", {})
    if not audit.get("sources_consulted"):
        errors.append("Level 6: audit_trail.sources_consulted must have at least 1 source")


def _validate_knower_assessment(packet, errors):
    assessment = packet.get("assessment", {})
    if not packet.get("claim"):
        errors.append("Level 6: knower_assessment must have non-empty claim")
    if assessment.get("confidence") not in (1, 2, 3, 4):
        errors.append(f"Level 6: assessment.confidence must be 1/2/3/4, got '{assessment.get('confidence')}'")
    if assessment.get("verdict") not in ("confirmed", "likely", "possible", "speculative", "debunked"):
        errors.append(f"Level 6: assessment.verdict must be confirmed/likely/possible/speculative/debunked, got '{assessment.get('verdict')}'")
    if "gaps" not in assessment:
        errors.append("Level 6: assessment.gaps field is required (may be empty list)")


def _validate_knower_myth_separation(packet, errors):
    if not packet.get("topic"):
        errors.append("Level 6: knower_myth_separation must have non-empty topic")
    myths = packet.get("myths", [])
    if not myths:
        errors.append("Level 6: knower_myth_separation must have at least 1 myth")
    for i, m in enumerate(myths):
        if not m.get("claim"):
            errors.append(f"Level 6: myth[{i}].claim must be non-empty")
        if m.get("status") not in ("debunked", "unverified", "partially_supported"):
            errors.append(f"Level 6: myth[{i}].status must be debunked/unverified/partially_supported, got '{m.get('status')}'")
        if m.get("confidence") not in (1, 2, 3, 4):
            errors.append(f"Level 6: myth[{i}].confidence must be 1/2/3/4, got '{m.get('confidence')}'")


def _validate_knower_claim_review(packet, errors):
    """Validate knower_claim_review packet — L6 field-level checks."""
    cr_data = packet.get("claim_review_data", {})
    if not cr_data.get("topic"):
        errors.append("Level 6: knower_claim_review must have non-empty claim_review_data.topic")
    claims = cr_data.get("claims", [])
    if not claims:
        errors.append("Level 6: knower_claim_review must have at least 1 claim in claim_review_data.claims")
    valid_classifications = ("fact", "inference", "assumption", "rumor")
    valid_source_qualities = ("primary", "secondary", "tertiary", "unverified")
    for i, c in enumerate(claims):
        if not c.get("text"):
            errors.append(f"Level 6: claim[{i}].text must be non-empty")
        if c.get("classification") not in valid_classifications:
            errors.append(f"Level 6: claim[{i}].classification must be one of {valid_classifications}, got '{c.get('classification')}'")
        if c.get("confidence") not in (1, 2, 3, 4):
            errors.append(f"Level 6: claim[{i}].confidence must be 1/2/3/4, got '{c.get('confidence')}'")
        if c.get("source_quality") not in valid_source_qualities:
            errors.append(f"Level 6: claim[{i}].source_quality must be one of {valid_source_qualities}, got '{c.get('source_quality')}'")
        if "evidence" not in c:
            errors.append(f"Level 6: claim[{i}].evidence field is required (may be empty list)")
        if "unknowns" not in c:
            errors.append(f"Level 6: claim[{i}].unknowns field is required (may be empty list)")
    if not cr_data.get("operator_brief"):
        errors.append("Level 6: knower_claim_review must have non-empty claim_review_data.operator_brief")


def _validate_knower_myth_fact(packet, errors):
    """Validate knower_myth_fact packet — L6 field-level checks."""
    mf_data = packet.get("myth_fact_data", {})
    if not mf_data.get("topic"):
        errors.append("Level 6: knower_myth_fact must have non-empty myth_fact_data.topic")
    items = mf_data.get("items", [])
    if not items:
        errors.append("Level 6: knower_myth_fact must have at least 1 item in myth_fact_data.items")
    valid_classifications = ("myth", "fact", "partial_truth", "unverified")
    valid_source_qualities = ("primary", "secondary", "tertiary", "unverified")
    for i, item in enumerate(items):
        if not item.get("statement"):
            errors.append(f"Level 6: item[{i}].statement must be non-empty")
        if item.get("classification") not in valid_classifications:
            errors.append(f"Level 6: item[{i}].classification must be one of {valid_classifications}, got '{item.get('classification')}'")
        if item.get("confidence") not in (1, 2, 3, 4):
            errors.append(f"Level 6: item[{i}].confidence must be 1/2/3/4, got '{item.get('confidence')}'")
        if item.get("source_quality") not in valid_source_qualities:
            errors.append(f"Level 6: item[{i}].source_quality must be one of {valid_source_qualities}, got '{item.get('source_quality')}'")
        if not item.get("explanation"):
            errors.append(f"Level 6: item[{i}].explanation must be non-empty")
        if "unknowns" not in item:
            errors.append(f"Level 6: item[{i}].unknowns field is required (may be empty list)")
    if not mf_data.get("operator_brief"):
        errors.append("Level 6: knower_myth_fact must have non-empty myth_fact_data.operator_brief")


# ──────────────────────────────────────────────
# v0.4.1: Inference Governance (L6)
# ──────────────────────────────────────────────

def _validate_inference_governance(packet, errors):
    """v0.4.1: Validate inference-specific governance constraints.

    When a packet has inference_mode=True in audit_trail, enforce:
      - inference_source must be present and non-empty
      - inference_attempt_id must be present and non-empty
      - inference_model must be present and non-empty
      - inference_source must be one of: mock, hermes, unknown
      - 'unknown' classification is only allowed in inference packets
        (deterministic workers MUST classify; only inference may mark unknown)
    """
    audit = packet.get("audit_trail", {})
    if not isinstance(audit, dict):
        return  # Already caught by L4

    inference_mode = audit.get("inference_mode", False)

    if not inference_mode:
        # Not an inference packet — no inference governance checks needed
        return

    # Inference packet — enforce metadata requirements
    inference_source = audit.get("inference_source", "")
    if not inference_source:
        errors.append(
            "Level 6: inference packet must have non-empty audit_trail.inference_source"
        )
    elif inference_source not in ("mock", "hermes", "hermes_cli", "unknown"):
        errors.append(
            f"Level 6: audit_trail.inference_source must be one of ('mock', 'hermes', 'hermes_cli', 'unknown'), "
            f"got '{inference_source}'"
        )

    inference_attempt_id = audit.get("inference_attempt_id", "")
    if not inference_attempt_id:
        errors.append(
            "Level 6: inference packet must have non-empty audit_trail.inference_attempt_id"
        )

    inference_model = audit.get("inference_model", "")
    if not inference_model:
        errors.append(
            "Level 6: inference packet must have non-empty audit_trail.inference_model"
        )

    # Validate that inference_elapsed_s is a number if present
    elapsed = audit.get("inference_elapsed_s")
    if elapsed is not None and not isinstance(elapsed, (int, float)):
        errors.append(
            f"Level 6: audit_trail.inference_elapsed_s must be numeric, got '{type(elapsed).__name__}'"
        )


# ──────────────────────────────────────────────
# Main Validation Entry Point
# ──────────────────────────────────────────────

def validate_packet(packet):
    """Run all 6 levels of validation on a packet. Returns (valid, errors, warnings)."""
    errors = []
    warnings = []

    validate_level1(packet, errors)
    validate_timestamp(packet.get("timestamp", ""), errors)
    validate_level2(packet, errors)
    validate_level3(packet, errors)
    validate_level4(packet, errors, warnings)
    validate_level5(packet, errors)
    validate_level6(packet, errors)

    valid = len(errors) == 0
    return valid, errors, warnings


def validate_file(filepath):
    """Validate a single JSON file. Returns the report dict."""
    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        return {
            "valid": False,
            "file": filepath,
            "packet_type": "unknown",
            "source": "unknown",
            "task_id": "unknown",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "errors": [f"JSON parse error: {e}"],
            "warnings": []
        }

    # Handle flow files that contain packets in a different structure
    # Check if this is a flow file (has flow_steps) or a raw packet
    packets_to_validate = []

    if "flow_steps" in data:
        # Flow file — extract subagent response packets for validation.
        # Flow steps contain multiple phase types. We only validate subagent
        # response packets (phases: response_packet, downstream_response_packet).
        # Request packets (phases: request_packet, downstream_request_packet) use
        # a different schema (required_packet_type, not packet_type) and are NOT
        # subagent handoff packets. Validation results and routing decisions are
        # also skipped.
        response_phases = {"response_packet", "downstream_response_packet"}
        skip_phases = {"task_creation", "request_packet", "downstream_request_packet",
                       "task_state_transitions", "validation_result", "routing_decision",
                       "downstream_validation_result", "downstream_routing_decision",
                       "operator_facing_packet"}
        for step in data["flow_steps"]:
            phase = step.get("phase", "")
            if phase in skip_phases or "result" in step:
                continue
            if phase in response_phases or phase == "response_packet":
                pkt = step.get("packet", {})
                if isinstance(pkt, dict) and pkt.get("packet_type"):
                    packets_to_validate.append(pkt)
            elif phase == "downstream_response_packet":
                pkt = step.get("packet", {})
                if isinstance(pkt, dict) and pkt.get("packet_type"):
                    packets_to_validate.append(pkt)
            # Also handle any step with a packet that has packet_type (catch-all)
            elif "packet" in step:
                pkt = step["packet"]
                if isinstance(pkt, dict) and pkt.get("packet_type"):
                    packets_to_validate.append(pkt)

        if not packets_to_validate:
            return {
                "valid": True,
                "file": filepath,
                "note": "Flow file detected but no subagent response packets found to validate",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "errors": [],
                "warnings": []
            }

        # Validate each packet found
        all_errors = []
        all_warnings = []
        overall_valid = True
        for pkt in packets_to_validate:
            valid, errors, warnings = validate_packet(pkt)
            if not valid:
                overall_valid = False
            all_errors.extend([f"[{pkt.get('packet_type', 'unknown')}/{pkt.get('task_id', 'unknown')}] {e}" for e in errors])
            all_warnings.extend([f"[{pkt.get('packet_type', 'unknown')}/{pkt.get('task_id', 'unknown')}] {w}" for w in warnings])

        return {
            "valid": overall_valid,
            "file": filepath,
            "packets_validated": len(packets_to_validate),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "errors": all_errors,
            "warnings": all_warnings
        }

    else:
        # Raw packet file
        valid, errors, warnings = validate_packet(data)
        return {
            "valid": valid,
            "file": filepath,
            "packet_type": data.get("packet_type", "unknown"),
            "source": data.get("source", "unknown"),
            "task_id": data.get("task_id", "unknown"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "errors": errors,
            "warnings": warnings
        }


def main():
    """CLI entry point."""
    if len(sys.argv) < 2:
        print("Usage: python validate_packet.py <packet_file.json> [...]", file=sys.stderr)
        print("       python validate_packet.py --dir <directory>", file=sys.stderr)
        sys.exit(1)

    files = []
    if sys.argv[1] == "--dir":
        if len(sys.argv) < 3:
            print("Error: --dir requires a directory path", file=sys.stderr)
            sys.exit(1)
        dirpath = sys.argv[2]
        if not os.path.isdir(dirpath):
            print(f"Error: {dirpath} is not a directory", file=sys.stderr)
            sys.exit(1)
        for f in sorted(os.listdir(dirpath)):
            if f.endswith('.json'):
                files.append(os.path.join(dirpath, f))
    else:
        files = sys.argv[1:]

    all_valid = True
    results = []

    for filepath in files:
        result = validate_file(filepath)
        results.append(result)
        status = "PASS" if result["valid"] else "FAIL"
        print(f"[{status}] {filepath}")
        if result.get("errors"):
            for e in result["errors"]:
                print(f"  ERROR: {e}")
        if result.get("warnings"):
            for w in result["warnings"]:
                print(f"  WARN:  {w}")
        if not result["valid"]:
            all_valid = True if all_valid and False else False
            all_valid = False

    # Summary
    print(f"\n{'='*60}")
    print(f"Validated {len(results)} file(s)")
    passed = sum(1 for r in results if r["valid"])
    failed = sum(1 for r in results if not r["valid"])
    print(f"Passed: {passed}  Failed: {failed}")

    sys.exit(0 if all_valid else 1)


if __name__ == "__main__":
    main()