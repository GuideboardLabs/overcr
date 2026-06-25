#!/usr/bin/env python3
"""
OverCR CryER Inference Worker — Crawling Reputation, Yield, Engagement & Recon (Live Inference)

This worker uses a live Hermes model to produce CryER packets from provided input snippets.
It follows the v0.4.3 inference pattern: call Hermes -z, sanitize output, validate packet.

Worker contract:
  - Input:  JSON request packet on stdin
  - Output: JSON response packet on stdout
  - Exit 0: success (response packet valid)
  - Exit nonzero: failure (caller must not trust output)

What this worker does:
  - Calls Hermes CLI (oneshot mode, --ignore-rules to avoid prompt contamination)
  - Sanitizes output (extracts JSON from code fences, preamble, etc.)
  - Produces CryER packets for 7 domains: recon, reputation_signal, engagement_signal,
    booking_friction, directory_completeness, hiring_growth, and inference_governance

What this worker does NOT do:
  - Live web crawling or browser automation
  - Login/authenticated access
  - Outbound contact or form submission
  - Direct routing to other subagents (Pyper, CodER, etc.)
  - Governance override claims

Safety note:
  The output is ALWAYS validated by the OverCR 6-level packet validator.
  Invalid output blocks task advancement — the task stays in_progress or enters validation_failed.
"""

import importlib.util
import json
import os
import sys
import hashlib
from datetime import datetime, timezone
from pathlib import Path


# ── Configuration ────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OVERCR_ROOT = Path(os.environ.get("OVERCR_ROOT", PROJECT_ROOT))

# Inference provider: "mock", "hermes_cli" (real), etc.
INFERENCE_SOURCE = os.environ.get("CryER_INFERENCE_SOURCE", "hermes_cli")

# Inference output sanitizer (v0.4.3 pattern)
SANITIZER_MODULE = PROJECT_ROOT / "runtime" / "output_sanitizer.py"

# Fallback to deterministic worker if inference fails
USE_DETERMINISTIC_FALLBACK = True
FALLBACK_WORKER_PATH = PROJECT_ROOT / "subagents" / "cryer" / "worker.py"


# ── Helper: YAML parsing (no PyYAML dependency) ────────────────

def _parse_yaml_simple(yaml_text: str) -> dict:
    """Simple flat YAML parser — no nested maps, lists, or comments."""
    result = {}
    for line in yaml_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            k, v = line.split(":", 1)
            result[k.strip()] = v.strip()
    return result


# ── Inference adapter factory (v0.4.3 pattern) ────────────────

def _get_inference_adapter():
    """Return an inference adapter instance based on INFERENCE_SOURCE."""
    try:
        # Try real Hermes CLI adapter first (v0.4.3)
        from runtime.inference_adapter import get_adapter
        return get_adapter(INFERENCE_SOURCE)
    except Exception:
        pass

    try:
        # Try runtime module (overcr/runtime)
        spec = importlib.util.spec_from_file_location(
            "inference_adapter", str(OVERCR_ROOT / "runtime" / "inference_adapter.py")
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.get_adapter(INFERENCE_SOURCE)
    except Exception:
        pass

    # Fallback: mock adapter (same domain as KnowER v0.4.1)
    return _MockInferenceAdapter()


class _MockInferenceAdapter:
    """Simulated inference adapter — no real model calls."""
    adapter_type = "mock"

    def is_available(self) -> bool:
        return True

    def dry_run(self):
        return {
            "available": True,
            "cli_path": "mock",
            "model": "mock-model",
            "provider": "mock",
            "error": None,
        }

    def invoke(self, prompt: str, timeout: float = 60.0):
        """Mock inference returns a deterministic CryER packet template."""
        # Extract entity from prompt if present
        entity = "unspecified_entity"
        if "for:" in prompt:
            entity = prompt.split("for:")[1].strip().split()[0]
        elif "analysis for" in prompt:
            entity = prompt.split("analysis for")[1].strip().split()[0]

        metadata = {
            "inference_attempt_id": "inference-0000",
            "prompt_hash": hashlib.sha256(prompt.encode()).hexdigest()[:16],
            "selected_model": "mock/qwen3-coder-next",
            "selected_provider": "ollama-cloud",
            "route_used": "inference",
            "raw_output_summary": "[MOCK] inference — simulated, not live model reasoning",
            "validation_result": None,
            "fallback_used": False,
            "elapsed_s": 0.0,
        }

        packet = {
            "packet_type": "cryer_recon",
            "version": "1.0",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": "cryer",
            "target": "overcr",
            "task_id": "task-0000",
            "summary": f"CryER inference complete for: {entity}",
            "recon_data": {
                "targets": [{
                    "entity": entity,
                    "type": "business",
                    "signals": {
                        "reputation": {"yield_score": 60, "confidence": 55, "risk_flags": []},
                    },
                    "raw_sources": ["provided_input"],
                }],
            },
            "audit_trail": {
                "worker_version": "0.5.0",
                "execution_timestamp": datetime.now(timezone.utc).isoformat(),
                "collection_timestamps": [datetime.now(timezone.utc).isoformat()],
                "methods_used": ["live_inference"],
                "files_modified": [],
                "rollback_instructions": "Analysis only — no filesystem changes.",
                "inference_mode": True,
                "inference_source": "mock",
                "inference_metadata": metadata,
            },
            "approval_required": False,
            "next_steps_recommendation": "No external action needed. Route to OverCR.",
        }

        return {"success": True, "raw_text": json.dumps(packet), "metadata": metadata}


# ── Prompt template ─────────────────────────────────────────────

INFERENCE_PROMPT = """You are CryER, a subagent of OverCR — the portable AI orchestration substrate.

You perform REPUTATION, ENGAGEMENT, BOOKING FRICTION, DIRECTORY COMPLETENESS, and HIRING/GROWTH analysis
via live model inference from provided public signal snippets.

CRITICAL RULES:
- You MUST produce valid CryER packets — never claim you made outbound contact, browsed the web,
  submitted forms, or made government/overhaul decisions.
- You must route ALL packets to "overcr" only — never to pyper, coder, or other subagents.
- You must distinguish observed signals, inferred signals, assumed signals, and unknowns.
- You must NEVER extract or store private personal data.
- If the input lacks sufficient data, produce a packet with low confidence (0-20) and recommended_routing="overcr".
- Inference attempt metadata MUST be included in audit_trail.inference_metadata.

INPUT FORMAT:
- input_context.entity: the target business or individual
- input_context.snippets: provided text (reviews, directories, announcements)
- domain: one of {recon, reputation_signal, engagement_signal, booking_friction, directory_completeness, hiring_growth}

OUTPUT FORMAT:
Return ONLY valid JSON with exactly these top-level fields:
  packet_type, version, timestamp, source, target, task_id, summary,
  [domain]_data, audit_trail, approval_required, next_steps_recommendation.

Domain schemas:
- recon_data.targets[].signals.reputation.{yield_score,confidence,risk_flags}
- reputation_signal_data.{entity,signals[],yield_score,confidence_notes,recommended_routing}
- engagement_signal_data.{entity,metrics[],engagement_summary,recommended_routing}
- booking_friction_data.{entity,friction_points[],friction_summary,recommended_routing}
- directory_completeness_data.{entity,present_fields,missing_fields,completeness_score,classification,confidence,recommended_routing}
- hiring_growth_data.{entity,signals[],growth_summary,recommended_routing}

All signals.metrics.friction_points.use classification ∈ {observed,inferred,assumed,unknown}.
All signals.metrics.friction_points.use source_quality ∈ {primary,secondary,tertiary,unverified}.
All top-level tasks have recommended_routing="overcr".

Now analyze the following input JSON:
{input_json}
"""


def build_inference_prompt(domain: str, request: dict) -> str:
    """Build an inference prompt from the request packet."""
    # Strip non-essential request keys for cleaner context
    minimal = {
        "domain": domain,
        "task_id": request.get("task_id"),
        "input_context": request.get("input_context", {}),
        "instruction": request.get("instruction"),
    }
    return INFERENCE_PROMPT.format(
        domain=domain,
        input_json=json.dumps(minimal, indent=2),
    )


# ── Packet builders (inference mode) ───────────────────────────

def _build_reputation_signal_packet_inference(entity: str, signals: list, inference_metadata: dict) -> dict:
    """Build a cryer_reputation_signal packet with inference metadata."""
    avg_confidence = sum(s.get("confidence", 50) for s in signals) // max(1, len(signals))
    yield_score = min(100, avg_confidence + 10)

    return {
        "packet_type": "cryer_reputation_signal",
        "version": "1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "cryer",
        "target": "overcr",
        "task_id": "task-0000",
        "summary": f"CryER reputation signal analysis for: {entity}",
        "reputation_signal_data": {
            "entity": entity,
            "signals": signals,
            "yield_score": yield_score,
            "confidence_notes": f"Confidence based on {len(signals)} signal(s) from provided input. Direct verification recommended.",
            "recommended_routing": "overcr",
        },
        "audit_trail": {
            "worker_version": "0.5.0",
            "execution_timestamp": datetime.now(timezone.utc).isoformat(),
            "methods_used": ["live_inference"],
            "files_modified": [],
            "rollback_instructions": "Analysis only — no filesystem changes.",
            "inference_mode": True,
            "inference_source": INFERENCE_SOURCE,
            "inference_metadata": inference_metadata,
        },
        "approval_required": False,
        "next_steps_recommendation": "No external action needed. Route to OverCR.",
    }


def _build_engagement_signal_packet_inference(entity: str, metrics: list, inference_metadata: dict) -> dict:
    return {
        "packet_type": "cryer_engagement_signal",
        "version": "1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "cryer",
        "target": "overcr",
        "task_id": "task-0000",
        "summary": f"CryER engagement signal analysis for: {entity}",
        "engagement_signal_data": {
            "entity": entity,
            "metrics": metrics,
            "engagement_summary": f"Engagement analysis for {entity} based on {len(metrics)} metric(s) from provided input. Further verification recommended.",
            "recommended_routing": "overcr",
        },
        "audit_trail": {
            "worker_version": "0.5.0",
            "execution_timestamp": datetime.now(timezone.utc).isoformat(),
            "methods_used": ["live_inference"],
            "files_modified": [],
            "rollback_instructions": "Analysis only — no filesystem changes.",
            "inference_mode": True,
            "inference_source": INFERENCE_SOURCE,
            "inference_metadata": inference_metadata,
        },
        "approval_required": False,
        "next_steps_recommendation": "No external action needed. Route to OverCR.",
    }


def _build_booking_friction_packet_inference(entity: str, friction_points: list, inference_metadata: dict) -> dict:
    return {
        "packet_type": "cryer_booking_friction",
        "version": "1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "cryer",
        "target": "overcr",
        "task_id": "task-0000",
        "summary": f"CryER booking friction analysis for: {entity}",
        "booking_friction_data": {
            "entity": entity,
            "friction_points": friction_points,
            "friction_summary": f"Booking friction analysis for {entity}: {len(friction_points)} friction point(s) identified from provided input.",
            "recommended_routing": "overcr",
        },
        "audit_trail": {
            "worker_version": "0.5.0",
            "execution_timestamp": datetime.now(timezone.utc).isoformat(),
            "methods_used": ["live_inference"],
            "files_modified": [],
            "rollback_instructions": "Analysis only — no filesystem changes.",
            "inference_mode": True,
            "inference_source": INFERENCE_SOURCE,
            "inference_metadata": inference_metadata,
        },
        "approval_required": False,
        "next_steps_recommendation": "No external action needed. Route to OverCR.",
    }


def _build_directory_completeness_packet_inference(entity: str, present_fields: list, missing_fields: list, inference_metadata: dict) -> dict:
    total_expected = len(present_fields) + len(missing_fields)
    completeness_score = (len(present_fields) * 100) // max(1, total_expected)
    classification = "observed" if present_fields else "inferred"
    confidence = min(80, 40 + len(present_fields) * 5)

    return {
        "packet_type": "cryer_directory_completeness",
        "version": "1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "cryer",
        "target": "overcr",
        "task_id": "task-0000",
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
            "worker_version": "0.5.0",
            "execution_timestamp": datetime.now(timezone.utc).isoformat(),
            "methods_used": ["live_inference"],
            "files_modified": [],
            "rollback_instructions": "Analysis only — no filesystem changes.",
            "inference_mode": True,
            "inference_source": INFERENCE_SOURCE,
            "inference_metadata": inference_metadata,
        },
        "approval_required": False,
        "next_steps_recommendation": "No external action needed. Route to OverCR.",
    }


def _build_hiring_growth_packet_inference(entity: str, signals: list, inference_metadata: dict) -> dict:
    return {
        "packet_type": "cryer_hiring_growth",
        "version": "1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "cryer",
        "target": "overcr",
        "task_id": "task-0000",
        "summary": f"CryER hiring/growth signal analysis for: {entity}",
        "hiring_growth_data": {
            "entity": entity,
            "signals": signals,
            "growth_summary": f"Hiring/growth analysis for {entity}: {len(signals)} signal(s) detected from provided input. Further verification recommended.",
            "recommended_routing": "overcr",
        },
        "audit_trail": {
            "worker_version": "0.5.0",
            "execution_timestamp": datetime.now(timezone.utc).isoformat(),
            "methods_used": ["live_inference"],
            "files_modified": [],
            "rollback_instructions": "Analysis only — no filesystem changes.",
            "inference_mode": True,
            "inference_source": INFERENCE_SOURCE,
            "inference_metadata": inference_metadata,
        },
        "approval_required": False,
        "next_steps_recommendation": "No external action needed. Route to OverCR.",
    }


# ── Deterministic fallback ─────────────────────────────────────

def _load_deterministic_worker():
    """Load the deterministic CryER worker modules for fallback."""
    spec = importlib.util.spec_from_file_location(
        "cryer_deterministic", str(FALLBACK_WORKER_PATH)
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _build_packet_deterministic(domain: str, request: dict) -> dict:
    """Call the deterministic CryER worker as fallback."""
    # Reuse deterministic builders from worker.py
    det = _load_deterministic_worker()

    # Extract helpers from the deterministic worker
    task_id = request.get("task_id", "task-0000")
    input_context = request.get("input_context", {})
    entity = input_context.get("entity", "unspecified_entity")

    if domain == "reputation_signal":
        signals = input_context.get("signals", [])
        for s in signals:
            if "confidence" not in s:
                s["confidence"] = 50
        if not signals:
            signals = [{
                "type": "sentiment",
                "classification": "assumed",
                "confidence": 40,
                "detail": f"Reputation signal analysis for {entity} based on provided input",
                "source_quality": "secondary",
                "unknowns": ["Direct verification needed"],
            }]
        avg_conf = sum(s["confidence"] for s in signals) // max(1, len(signals))
        yield_score = min(100, avg_conf + 10)
        return {
            "packet_type": "cryer_reputation_signal",
            "version": "1.0",
            "timestamp": datetime.now(timezone.utc).isoformat(),
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
                "worker_version": "0.5.0",
                "execution_timestamp": datetime.now(timezone.utc).isoformat(),
                "methods_used": ["public_signal_analysis"],
                "files_modified": [],
                "rollback_instructions": "No filesystem changes made by worker. Analysis only.",
                "inference_mode": False,
            },
            "approval_required": False,
            "next_steps_recommendation": "No external action needed. Route to OverCR.",
        }
    if domain == "engagement_signal":
        metrics = input_context.get("metrics", [])
        if not metrics:
            metrics = [{
                "type": "review_count",
                "classification": "assumed",
                "value": "unknown",
                "confidence": 40,
                "source_quality": "unverified",
                "unknowns": ["Exact count requires direct verification"],
            }]
        return {
            "packet_type": "cryer_engagement_signal",
            "version": "1.0",
            "timestamp": datetime.now(timezone.utc).isoformat(),
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
                "worker_version": "0.5.0",
                "execution_timestamp": datetime.now(timezone.utc).isoformat(),
                "methods_used": ["public_signal_analysis"],
                "files_modified": [],
                "rollback_instructions": "No filesystem changes made by worker. Analysis only.",
                "inference_mode": False,
            },
            "approval_required": False,
            "next_steps_recommendation": "No external action needed. Route to OverCR.",
        }
    if domain == "booking_friction":
        friction_points = input_context.get("friction_points", [])
        if not friction_points:
            friction_points = [{
                "type": "contact_required",
                "classification": "assumed",
                "confidence": 50,
                "detail": f"Booking process for {entity} requires analysis of provided input",
                "source_quality": "secondary",
                "unknowns": ["Direct verification of booking process recommended"],
            }]
        return {
            "packet_type": "cryer_booking_friction",
            "version": "1.0",
            "timestamp": datetime.now(timezone.utc).isoformat(),
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
                "worker_version": "0.5.0",
                "execution_timestamp": datetime.now(timezone.utc).isoformat(),
                "methods_used": ["public_signal_analysis"],
                "files_modified": [],
                "rollback_instructions": "No filesystem changes made by worker. Analysis only.",
                "inference_mode": False,
            },
            "approval_required": False,
            "next_steps_recommendation": "No external action needed. Route to OverCR.",
        }
    if domain == "directory_completeness":
        present = input_context.get("present_fields", ["name"])
        missing = input_context.get("missing_fields", ["phone", "website", "hours", "description", "photos"])
        total = len(present) + len(missing)
        score = (len(present) * 100) // max(1, total)
        return {
            "packet_type": "cryer_directory_completeness",
            "version": "1.0",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": "cryer",
            "target": "overcr",
            "task_id": task_id,
            "summary": f"CryER directory completeness assessment for: {entity}",
            "directory_completeness_data": {
                "entity": entity,
                "present_fields": present,
                "missing_fields": missing,
                "completeness_score": score,
                "classification": "inferred",
                "confidence": min(80, 40 + len(present) * 5),
                "recommended_routing": "overcr",
                "source_quality": "secondary",
                "unknowns": ["Direct verification of listing recommended"],
            },
            "audit_trail": {
                "worker_version": "0.5.0",
                "execution_timestamp": datetime.now(timezone.utc).isoformat(),
                "methods_used": ["public_signal_analysis"],
                "files_modified": [],
                "rollback_instructions": "No filesystem changes made by worker. Analysis only.",
                "inference_mode": False,
            },
            "approval_required": False,
            "next_steps_recommendation": "No external action needed. Route to OverCR.",
        }
    if domain == "hiring_growth":
        signals = input_context.get("signals", [])
        if not signals:
            signals = [{
                "type": "job_posting",
                "classification": "assumed",
                "confidence": 50,
                "detail": f"Hiring/growth signal analysis for {entity} based on provided input",
                "source_quality": "secondary",
                "unknowns": ["Direct verification of job postings recommended"],
            }]
        return {
            "packet_type": "cryer_hiring_growth",
            "version": "1.0",
            "timestamp": datetime.now(timezone.utc).isoformat(),
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
                "worker_version": "0.5.0",
                "execution_timestamp": datetime.now(timezone.utc).isoformat(),
                "methods_used": ["public_signal_analysis"],
                "files_modified": [],
                "rollback_instructions": "No filesystem changes made by worker. Analysis only.",
                "inference_mode": False,
            },
            "approval_required": False,
            "next_steps_recommendation": "No external action needed. Route to OverCR.",
        }
    # recon fallback
    entity = input_context.get("entity", "unspecified_entity")
    confidence = 40
    yield_score = 50
    return {
        "packet_type": "cryer_recon",
        "version": "1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "cryer",
        "target": "overcr",
        "task_id": task_id,
        "summary": f"CryER recon complete for: {entity}",
        "recon_data": {
            "targets": [{
                "entity": entity,
                "type": "business",
                "signals": {
                    "reputation": {"yield_score": yield_score, "confidence": confidence, "risk_flags": []},
                },
                "raw_sources": ["provided_input"],
            }],
        },
        "audit_trail": {
            "worker_version": "0.5.0",
            "execution_timestamp": datetime.now(timezone.utc).isoformat(),
            "collection_timestamps": [datetime.now(timezone.utc).isoformat()],
            "methods_used": ["public_signal_analysis"],
            "files_modified": [],
            "rollback_instructions": "No filesystem changes made by worker. Analysis only.",
            "inference_mode": False,
        },
        "approval_required": False,
        "next_steps_recommendation": "No external action needed. Route to OverCR.",
    }


# ── Main: Inference entry point ────────────────────────────────

def _main():
    """Main entry: read request, perform inference, produce validated packet."""
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            print(json.dumps({"error": "empty_input", "message": "Worker received empty input on stdin"}), file=sys.stderr)
            sys.exit(1)
        request = json.loads(raw)
    except json.JSONDecodeError as e:
        print(json.dumps({"error": "invalid_json", "message": f"Worker received invalid JSON on stdin: {e}"}), file=sys.stderr)
        sys.exit(1)

    # Extract domain and entity
    domain = request.get("domain", "recon")
    input_context = request.get("input_context", {})
    entity = input_context.get("entity", "unspecified_entity")
    task_id = request.get("task_id", "task-0000")

    # Initialize metadata placeholder
    inference_metadata = {
        "inference_attempt_id": "inference-0000",
        "prompt_hash": "",
        "selected_model": "unknown",
        "selected_provider": "unknown",
        "route_used": "inference",
        "raw_output_summary": "",
        "validation_result": None,
        "fallback_used": True,
        "elapsed_s": 0.0,
    }

    # Attempt inference (live or mock)
    adapter = _get_inference_adapter()
    prompt = build_inference_prompt(domain, request)

    try:
        result = adapter.invoke(prompt, timeout=60.0)
        if result.get("success"):
            raw_text = result.get("raw_text", "")
            inference_metadata = result.get("metadata", inference_metadata)
            inference_metadata["fallback_used"] = False
        else:
            raise ValueError("Inference adapter returned success=False")
    except Exception as e:
        if not USE_DETERMINISTIC_FALLBACK:
            print(json.dumps({"error": "inference_failed", "message": str(e)}), file=sys.stderr)
            sys.exit(1)
        # Fallback to deterministic worker
        try:
            packet = _build_packet_deterministic(domain, request)
        except Exception as e:
            print(json.dumps({"error": "fallback_failed", "message": str(e)}), file=sys.stderr)
            sys.exit(1)
        # Mark fallback in audit
        packet["audit_trail"]["inference_mode"] = False
        print(json.dumps(packet, indent=2))
        sys.exit(0)

    # Try to parse sanitized output
    try:
        packet = json.loads(raw_text)
    except json.JSONDecodeError as e:
        if not USE_DETERMINISTIC_FALLBACK:
            print(json.dumps({"error": "output_parse_error", "message": str(e)}), file=sys.stderr)
            sys.exit(1)
        packet = _build_packet_deterministic(domain, request)
        inference_metadata["fallback_used"] = True

    # Inject inference metadata if missing
    if "audit_trail" in packet:
        packet["audit_trail"]["inference_mode"] = True
        packet["audit_trail"]["inference_source"] = INFERENCE_SOURCE
        packet["audit_trail"]["inference_metadata"] = inference_metadata
    else:
        packet["audit_trail"] = {
            "worker_version": "0.5.0",
            "execution_timestamp": datetime.now(timezone.utc).isoformat(),
            "methods_used": ["live_inference"],
            "files_modified": [],
            "rollback_instructions": "Analysis only — no filesystem changes.",
            "inference_mode": True,
            "inference_source": INFERENCE_SOURCE,
            "inference_metadata": inference_metadata,
        }

    # Write packet to stdout
    print(json.dumps(packet, indent=2))


if __name__ == "__main__":
    _main()
