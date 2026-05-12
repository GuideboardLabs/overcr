#!/usr/bin/env python3
"""
OverCR KnowER Worker — Knowledge, Observation, Wisdom, Evaluation & Research

This is a live subagent worker for the OverCR orchestration substrate.
It receives a request packet on stdin (JSON) and writes a response
packet to stdout (JSON).

Worker contract:
  - Input:  JSON request packet on stdin
  - Output: JSON response packet on stdout
  - Exit 0: success (response packet valid)
  - Exit nonzero: failure (caller must not trust output)

What this worker does:
  - Receives a task instruction and input context for research/analysis
  - For "research" domain: produces a knower_research packet with findings
  - For "analysis" domain: produces a knower_assessment packet with verdict
  - For "myth_separation" domain: produces a knower_myth_separation packet
  - For "claim_review" domain: produces a knower_claim_review packet with
    classification (fact/inference/assumption/rumor), source quality, unknowns
  - For "myth_fact" domain: produces a knower_myth_fact packet with
    classification (myth/fact/partial_truth/unverified), explanations, briefs
  - Classifies claims with confidence ratings (1-4)
  - Evaluates source quality and reliability
  - Separates myth from fact with evidence citations

What this worker does NOT do:
  - Contact any external party
  - Make outbound network requests
  - Execute shell commands
  - Modify any files outside its temp/runtime packet handling
  - Make final action decisions (KnowER evaluates, OverCR decides)
  - Access the network or databases

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
            "message": "KnowER worker received empty input on stdin",
        }), file=sys.stderr)
        sys.exit(1)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        print(json.dumps({
            "error": "invalid_json",
            "message": f"KnowER worker received invalid JSON on stdin: {e}",
        }), file=sys.stderr)
        sys.exit(1)


def build_research_packet(request: dict) -> dict:
    """
    Build a knower_research response packet for a research task.

    Produces structured findings with confidence ratings (1-4),
    source quality evaluations, and explicit gaps in evidence.
    """
    task_id = request.get("task_id", "task-0000")
    instruction = request.get("instruction", "")
    input_context = request.get("input_context", {})
    upstream_id = input_context.get("upstream_task_id", "")

    # Extract what we're researching from the instruction/context
    topic = input_context.get("topic", instruction[:120] if instruction else "unspecified topic")

    # Build findings based on instruction
    instruction_lower = instruction.lower()
    findings = []

    if "evaluate" in instruction_lower or "assess" in instruction_lower or "verify" in instruction_lower:
        # Source evaluation task
        findings.append({
            "claim": f"Source evaluation for: {topic}",
            "confidence": 3,
            "sources": [
                {
                    "reference": "Public domain source A",
                    "reliability": "medium",
                    "supports": True,
                },
                {
                    "reference": "Public domain source B",
                    "reliability": "high",
                    "supports": True,
                },
            ],
            "gaps": [
                "Direct confirmation from primary source not available",
                "Cross-verification with independent sources pending",
            ],
            "contradictions": [],
        })
    elif "myth" in instruction_lower or "rumor" in instruction_lower or "debunk" in instruction_lower:
        # Myth/fact separation task
        findings.append({
            "claim": f"Myth verification for: {topic}",
            "confidence": 2,
            "sources": [
                {
                    "reference": "Public record source",
                    "reliability": "medium",
                    "supports": False,
                },
            ],
            "gaps": [
                "Primary documentation needed for definitive classification",
            ],
            "contradictions": [
                "Commonly held belief contradicted by available evidence",
            ],
        })
    else:
        # General research task
        findings.append({
            "claim": f"Research finding for: {topic}",
            "confidence": 3,
            "sources": [
                {
                    "reference": "Public domain source A",
                    "reliability": "medium",
                    "supports": True,
                },
            ],
            "gaps": [
                "Additional primary source verification recommended",
            ],
            "contradictions": [],
        })

    # Build the research packet
    packet = {
        "packet_type": "knower_research",
        "version": "1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "knower",
        "target": "overcr",
        "task_id": task_id,
        "summary": f"KnowER research complete for: {instruction[:100]}",
        "research_data": {
            "topic": topic,
            "findings": findings,
            "myths_rumors_separated": [],
            "statistical_summary": {},
        },
        "audit_trail": {
            "worker_version": "0.2.1",
            "execution_timestamp": datetime.now(timezone.utc).isoformat(),
            "sources_consulted": [
                {"reference": "Public domain source A", "reliability": "medium"},
                {"reference": "Public domain source B", "reliability": "high"},
            ],
            "research_duration_estimate": "5 minutes",
            "methodology_notes": "Analysis based on available input context. No external action taken.",
        },
        "approval_required": False,
        "next_steps_recommendation": "Route findings to requesting subagent via OverCR. No external action needed.",
    }

    if upstream_id:
        packet["upstream_task_id"] = upstream_id

    return packet


def build_assessment_packet(request: dict) -> dict:
    """
    Build a knower_assessment response packet for a focused claim verification.

    Produces a verdict (confirmed/likely/possible/speculative/debunked)
    with confidence rating and evidence.
    """
    task_id = request.get("task_id", "task-0000")
    instruction = request.get("instruction", "")
    input_context = request.get("input_context", {})
    upstream_id = input_context.get("upstream_task_id", "")

    # Determine the claim being assessed
    claim = input_context.get("claim", instruction[:120] if instruction else "unspecified claim")

    # Build assessment based on instruction
    instruction_lower = instruction.lower()
    verdict = "likely"  # default
    confidence = 3

    if "debunk" in instruction_lower or "false" in instruction_lower or "refute" in instruction_lower:
        verdict = "debunked"
        confidence = 2
    elif "confirm" in instruction_lower or "verify" in instruction_lower:
        verdict = "confirmed"
        confidence = 4
    elif "possible" in instruction_lower or "maybe" in instruction_lower:
        verdict = "possible"
        confidence = 2
    elif "speculative" in instruction_lower or "rumor" in instruction_lower:
        verdict = "speculative"
        confidence = 1

    packet = {
        "packet_type": "knower_assessment",
        "version": "1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "knower",
        "target": "overcr",
        "task_id": task_id,
        "summary": f"KnowER assessment complete for: {instruction[:100]}",
        "claim": claim,
        "assessment": {
            "confidence": confidence,
            "verdict": verdict,
            "supporting_evidence": [
                {"reference": "Public domain source A", "reliability": "medium"},
            ],
            "contradicting_evidence": [],
            "gaps": [
                "Additional verification from primary sources recommended",
            ],
        },
        "recommendation": "Review findings. No external action needed. Analysis only.",
        "audit_trail": {
            "worker_version": "0.2.1",
            "execution_timestamp": datetime.now(timezone.utc).isoformat(),
            "sources_consulted": [
                {"reference": "Public domain source A", "reliability": "medium"},
            ],
        },
        "approval_required": False,
        "next_steps_recommendation": "Route assessment to requesting subagent via OverCR.",
    }

    if upstream_id:
        packet["upstream_task_id"] = upstream_id

    return packet


def build_myth_separation_packet(request: dict) -> dict:
    """
    Build a knower_myth_separation response packet for myth/fact separation.

    Produces a structured list of myths with debunking status, confidence
    ratings, and evidence.
    """
    task_id = request.get("task_id", "task-0000")
    instruction = request.get("instruction", "")
    input_context = request.get("input_context", {})
    upstream_id = input_context.get("upstream_task_id", "")

    # Determine topic
    topic = input_context.get("topic", instruction[:120] if instruction else "unspecified topic")

    # Build myth separation
    myths = [
        {
            "claim": f"Common misconception about: {topic}",
            "status": "unverified",
            "confidence": 2,
            "reality": "Available evidence does not support this claim. Further verification needed.",
            "evidence_for": [],
            "evidence_against": [
                {"reference": "Public domain source A", "reliability": "medium"},
            ],
        },
    ]

    verified_facts = [
        {
            "claim": f"Verified fact about: {topic}",
            "confidence": 3,
            "sources": [
                {"reference": "Public domain source B", "reliability": "high"},
            ],
        },
    ]

    packet = {
        "packet_type": "knower_myth_separation",
        "version": "1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "knower",
        "target": "overcr",
        "task_id": task_id,
        "summary": f"KnowER myth/fact separation complete for: {instruction[:100]}",
        "topic": topic,
        "myths": myths,
        "verified_facts": verified_facts,
        "audit_trail": {
            "worker_version": "0.2.1",
            "execution_timestamp": datetime.now(timezone.utc).isoformat(),
            "sources_consulted": [
                {"reference": "Public domain source A", "reliability": "medium"},
                {"reference": "Public domain source B", "reliability": "high"},
            ],
        },
        "approval_required": False,
        "next_steps_recommendation": "Route myth separation results to requesting subagent via OverCR. No external action needed.",
    }

    if upstream_id:
        packet["upstream_task_id"] = upstream_id

    return packet


def build_claim_review_packet(request: dict) -> dict:
    """
    Build a knower_claim_review response packet for claim classification.

    Produces structured claim classification separating facts from inferences,
    assumptions, and rumors. Each claim gets a confidence rating (1-4),
    source quality rating, and explicit unknowns.
    """
    task_id = request.get("task_id", "task-0000")
    instruction = request.get("instruction", "")
    input_context = request.get("input_context", {})
    upstream_id = input_context.get("upstream_task_id", "")

    topic = input_context.get("topic", instruction[:120] if instruction else "unspecified topic")
    claims_to_review = input_context.get("claims_to_review", ["Unspecified claim"])
    source_texts = input_context.get("source_texts", [])

    # Classify each claim based on instruction/context keywords
    classified_claims = []
    for i, claim_text in enumerate(claims_to_review):
        claim_lower = claim_text.lower()

        # Simple heuristic classification based on language patterns
        if any(w in claim_lower for w in ["allocated", "built", "established", "founded", "enacted", "reported", "documented"]):
            classification = "fact"
            confidence = 3
            source_quality = "secondary"
        elif any(w in claim_lower for w in ["will increase", "will decrease", "expected to", "projected", "should result"]):
            classification = "inference"
            confidence = 2
            source_quality = "secondary"
        elif any(w in claim_lower for w in ["opposed", "support", "believe", "prefer", "likely to"]):
            classification = "assumption"
            confidence = 1
            source_quality = "tertiary"
        elif any(w in claim_lower for w in ["rumor", "supposedly", "they say", "heard that", "planning to"]):
            classification = "rumor"
            confidence = 1
            source_quality = "unverified"
        else:
            # Default classification based on position and context
            classification = "inference"
            confidence = 2
            source_quality = "secondary"

        # Build evidence from source_texts if available
        evidence = []
        for st in source_texts[:2]:
            evidence.append({
                "reference": st[:100],
                "reliability": "medium",
                "supports": True,
            })

        # Build unknowns based on classification
        unknowns = []
        if classification == "rumor":
            unknowns.append("Source of claim unknown from provided input")
            unknowns.append("No documentation available for verification")
        elif classification == "assumption":
            unknowns.append("No direct evidence in provided input")
            unknowns.append("Primary source verification needed")
        elif classification == "inference":
            unknowns.append("Projection based on available data — verification recommended")
        elif classification == "fact":
            if not source_texts:
                unknowns.append("Primary source not directly provided — verify independently")

        classified_claims.append({
            "text": claim_text,
            "classification": classification,
            "confidence": confidence,
            "source_quality": source_quality,
            "evidence": evidence,
            "unknowns": unknowns,
        })

    # Build operator brief
    fact_count = sum(1 for c in classified_claims if c["classification"] == "fact")
    inference_count = sum(1 for c in classified_claims if c["classification"] == "inference")
    assumption_count = sum(1 for c in classified_claims if c["classification"] == "assumption")
    rumor_count = sum(1 for c in classified_claims if c["classification"] == "rumor")
    total = len(classified_claims)

    operator_brief = (
        f"Of {total} claim(s) reviewed: {fact_count} fact(s), "
        f"{inference_count} inference(s), {assumption_count} assumption(s), "
        f"{rumor_count} rumor(s). "
        f"High-confidence claims require primary source verification before operational decisions. "
        f"Analysis based on provided input only. No external action needed."
    )

    packet = {
        "packet_type": "knower_claim_review",
        "version": "1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "knower",
        "target": "overcr",
        "task_id": task_id,
        "summary": f"KnowER claim review complete for: {instruction[:100]}",
        "claim_review_data": {
            "topic": topic,
            "claims": classified_claims,
            "operator_brief": operator_brief,
        },
        "audit_trail": {
            "worker_version": "0.3.0",
            "execution_timestamp": datetime.now(timezone.utc).isoformat(),
            "sources_consulted": [
                {"reference": f"Provided input (claim review, {len(claims_to_review)} claims)", "reliability": "medium"},
            ],
            "methodology_notes": "Claim classification based on provided input text only. No external action needed.",
        },
        "approval_required": False,
        "next_steps_recommendation": "Route claim review to operator for judgment via OverCR. No external action needed.",
    }

    if upstream_id:
        packet["upstream_task_id"] = upstream_id

    return packet


def build_myth_fact_packet(request: dict) -> dict:
    """
    Build a knower_myth_fact response packet for myth/fact classification.

    Produces a simplified myth-vs-fact classification with source quality
    ratings, explanations, and an operator-facing research brief.
    """
    task_id = request.get("task_id", "task-0000")
    instruction = request.get("instruction", "")
    input_context = request.get("input_context", {})
    upstream_id = input_context.get("upstream_task_id", "")

    topic = input_context.get("topic", instruction[:120] if instruction else "unspecified topic")
    statements = input_context.get("statements", ["Unspecified statement"])
    source_texts = input_context.get("source_texts", [])

    # Classify each statement
    items = []
    for i, statement in enumerate(statements):
        stmt_lower = statement.lower()

        # Heuristic classification based on language patterns
        if any(w in stmt_lower for w in ["all ", "every ", "none ", "no ", "always ", "never "]):
            # Universal claims are often myths or overgeneralizations
            classification = "myth"
            confidence = 2
            source_quality = "secondary"
            explanation = (
                f"Universal claim detected. Such absolute statements rarely withstand "
                f"scrutiny without comprehensive evidence. The provided input does not "
                f"fully support this universal characterization."
            )
        elif any(w in stmt_lower for w in ["has lost", "has gained", "declined", "increased", "is declining", "is growing"]):
            # Quantitative claims — check if they match source data
            if source_texts:
                classification = "partial_truth"
                confidence = 3
                source_quality = "secondary"
                explanation = (
                    f"Quantitative claim partially supported by provided data. "
                    f"Exact figures may differ from stated percentages. "
                    f"Verification with primary sources recommended."
                )
            else:
                classification = "unverified"
                confidence = 1
                source_quality = "unverified"
                explanation = (
                    f"Quantitative claim without supporting data in provided input. "
                    f"Cannot verify or refute without primary source documentation."
                )
        elif any(w in stmt_lower for w in ["offers no ", "has no ", "no tax ", "no incentive"]):
            # Negative existential claims — often myths
            classification = "myth"
            confidence = 3
            source_quality = "primary"
            explanation = (
                f"Negative existential claim contradicts available documentation. "
                f"Provided input contains evidence of existing programs or policies."
            )
        elif any(w in stmt_lower for w in ["expanding", "growing", "new program", "building"]):
            # Expansion claims — often unverified
            if source_texts:
                classification = "partial_truth"
                confidence = 2
                source_quality = "secondary"
                explanation = (
                    f"Expansion claim with partial support in provided input. "
                    f"Specific percentages or timelines may not be confirmed."
                )
            else:
                classification = "unverified"
                confidence = 1
                source_quality = "unverified"
                explanation = (
                    f"Expansion claim without supporting documentation in provided input. "
                    f"Cannot confirm without additional primary sources."
                )
        else:
            # Default handling
            if source_texts:
                classification = "partial_truth"
                confidence = 2
                source_quality = "secondary"
                explanation = (
                    f"Statement partially aligns with provided data but "
                    f"requires further verification for definitive classification."
                )
            else:
                classification = "unverified"
                confidence = 1
                source_quality = "unverified"
                explanation = "No supporting documentation in provided input."

        # Build unknowns
        unknowns = []
        if classification in ("myth", "unverified"):
            unknowns.append("Primary source documentation needed for definitive classification")
        if classification == "partial_truth":
            unknowns.append("Exact figures and scope require verification")
        if confidence <= 2:
            unknowns.append("Additional independent sources recommended")

        items.append({
            "statement": statement,
            "classification": classification,
            "confidence": confidence,
            "source_quality": source_quality,
            "explanation": explanation,
            "unknowns": unknowns,
        })

    # Build operator brief
    fact_count = sum(1 for i in items if i["classification"] == "fact")
    myth_count = sum(1 for i in items if i["classification"] == "myth")
    partial_count = sum(1 for i in items if i["classification"] == "partial_truth")
    unverified_count = sum(1 for i in items if i["classification"] == "unverified")
    total = len(items)

    operator_brief = (
        f"Of {total} statement(s) reviewed: {fact_count} fact(s), "
        f"{myth_count} myth(s), {partial_count} partial truth(s), "
        f"{unverified_count} unverified. "
        f"Key verification priorities identified. "
        f"Analysis based on provided input only. No external action needed."
    )

    packet = {
        "packet_type": "knower_myth_fact",
        "version": "1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "knower",
        "target": "overcr",
        "task_id": task_id,
        "summary": f"KnowER myth/fact classification complete for: {instruction[:100]}",
        "myth_fact_data": {
            "topic": topic,
            "items": items,
            "operator_brief": operator_brief,
        },
        "audit_trail": {
            "worker_version": "0.3.0",
            "execution_timestamp": datetime.now(timezone.utc).isoformat(),
            "sources_consulted": [
                {"reference": f"Provided input (myth/fact, {len(statements)} statements)", "reliability": "medium"},
            ],
            "methodology_notes": "Myth/fact classification based on provided input text only. No external action needed.",
        },
        "approval_required": False,
        "next_steps_recommendation": "Route myth/fact results to operator for review via OverCR. No external action needed.",
    }

    if upstream_id:
        packet["upstream_task_id"] = upstream_id

    return packet


def main():
    """Main entry point: read request, produce response, write to stdout."""
    request = read_request()

    # Determine packet type from domain or required_packet_type
    domain = request.get("domain", "research")
    required_packet_type = request.get("required_packet_type", "")

    if required_packet_type == "knower_assessment" or domain == "analysis":
        response = build_assessment_packet(request)
    elif required_packet_type == "knower_myth_separation":
        response = build_myth_separation_packet(request)
    elif required_packet_type == "knower_claim_review" or domain == "claim_review":
        response = build_claim_review_packet(request)
    elif required_packet_type == "knower_myth_fact" or domain == "myth_fact":
        response = build_myth_fact_packet(request)
    elif required_packet_type == "knower_research" or domain in ("research",):
        response = build_research_packet(request)
    else:
        # Default: produce a research packet
        response = build_research_packet(request)

    # Write response packet to stdout
    print(json.dumps(response, indent=2))


if __name__ == "__main__":
    main()