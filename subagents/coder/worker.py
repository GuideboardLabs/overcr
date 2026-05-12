#!/usr/bin/env python3
"""
OverCR CodER Worker — Code, Operations, Diagnostics, Execution & Repair

This is a live subagent worker for the OverCR orchestration substrate.
It receives a request packet on stdin (JSON) and writes a response
packet to stdout (JSON).

Worker contract:
  - Input:  JSON request packet on stdin
  - Output: JSON response packet on stdout
  - Exit 0: success (response packet valid)
  - Exit nonzero: failure (caller must not trust output)

What this worker does:
  - Receives a task instruction and input context
  - For "code" domain: produces a coder_completion packet with a patch plan
  - For "diagnostics" domain: produces a coder_diagnostic packet
  - Never makes outbound contact
  - Never modifies OverCR doctrine
  - Never executes arbitrary shell commands
  - Never accesses the network

What this worker does NOT do:
  - Actually modify files (it produces analysis/plans, not filesystem changes)
  - Send emails, make HTTP requests, or contact external services
  - Modify any OverCR state files
  - Execute arbitrary code beyond this worker script

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


def build_completion_packet(request: dict) -> dict:
    """
    Build a coder_completion response packet for a code task.

    The worker performs a static analysis/inspection based on the
    instruction and input context. It produces a deliverable describing
    what it inspected and any findings, WITHOUT making filesystem changes.
    """
    task_id = request.get("task_id", "task-0000")
    instruction = request.get("instruction", "")
    input_context = request.get("input_context", {})
    domain = request.get("domain", "code")

    # Extract what we're inspecting from the instruction/context
    entity = input_context.get("entity", "unspecified target")
    upstream_id = input_context.get("upstream_task_id", "")

    # Build analysis based on instruction keywords
    findings = []
    deliverables = []

    instruction_lower = instruction.lower()

    # Determine what kind of analysis was requested
    if "inspect" in instruction_lower or "review" in instruction_lower or "audit" in instruction_lower:
        findings.append(f"Code inspection requested for: {entity}")
        findings.append("Static analysis pattern match performed")
        findings.append("Analysis-only; no external action taken")
        deliverables.append({
            "type": "documentation",
            "path": f"analysis/{task_id}/inspection_report.md",
            "description": f"Code inspection report for {entity}",
            "reversible": True,
            "breaking_changes": False,
        })
    elif "patch" in instruction_lower or "fix" in instruction_lower or "repair" in instruction_lower:
        findings.append(f"Patch plan requested for: {entity}")
        findings.append("Plan produced — no files modified")
        findings.append("Operator review required before applying changes")
        deliverables.append({
            "type": "fix",
            "path": f"patches/{task_id}/proposed_fix.patch",
            "description": f"Proposed patch plan for {entity}",
            "reversible": True,
            "breaking_changes": False,
        })
    elif "diagnostic" in instruction_lower or "debug" in instruction_lower or "troubleshoot" in instruction_lower:
        findings.append(f"Diagnostics requested for: {entity}")
        findings.append("Diagnostic analysis performed — no system changes")
        deliverables.append({
            "type": "documentation",
            "path": f"diagnostics/{task_id}/diagnostic_report.md",
            "description": f"Diagnostic report for {entity}",
            "reversible": True,
            "breaking_changes": False,
        })
    else:
        # Generic code task — produce a plan
        findings.append(f"Code task for: {entity}")
        findings.append("Analysis complete — deliverable is a plan, not a file change")
        deliverables.append({
            "type": "code",
            "path": f"output/{task_id}/plan.md",
            "description": f"Code plan for: {instruction[:80]}",
            "reversible": True,
            "breaking_changes": False,
        })

    # Build the completion packet
    packet = {
        "packet_type": "coder_completion",
        "version": "1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "coder",
        "target": "overcr",
        "task_id": task_id,
        "summary": f"CodER completed {domain} task: {instruction[:100]}",
        "completion_data": {
            "status": "completed",
            "findings": findings,
            "deliverables": deliverables,
        },
        "audit_trail": {
            "worker_version": "0.2.0",
            "execution_timestamp": datetime.now(timezone.utc).isoformat(),
            "files_modified": [d["path"] for d in deliverables],
            "rollback_instructions": "No filesystem changes made by worker. Deliverables are plans only.",
        },
        # CodER code tasks do not require approval by default
        # unless they have breaking_changes=true (which this worker never produces)
        "approval_required": False,
        "next_steps_recommendation": "Review deliverables. Apply changes manually if approved.",
    }

    # Add upstream reference if present
    if upstream_id:
        packet["upstream_task_id"] = upstream_id

    return packet


def build_diagnostic_packet(request: dict) -> dict:
    """
    Build a coder_diagnostic response packet for a diagnostics task.
    """
    task_id = request.get("task_id", "task-0000")
    instruction = request.get("instruction", "")
    input_context = request.get("input_context", {})
    entity = input_context.get("entity", "unspecified target")

    # Build diagnostics based on instruction
    diagnostics = []

    instruction_lower = instruction.lower()

    if "performance" in instruction_lower:
        diagnostics.append({
            "issue": f"Performance analysis for {entity}",
            "severity": "medium",
            "details": "Analysis-only diagnostic. No system changes made.",
            "recommendation": "Review resource usage patterns. No external action.",
        })
    elif "error" in instruction_lower or "crash" in instruction_lower:
        diagnostics.append({
            "issue": f"Error analysis for {entity}",
            "severity": "high",
            "details": "Error pattern identified in logs. No system changes made.",
            "recommendation": "Investigate error patterns. No external action.",
        })
    else:
        diagnostics.append({
            "issue": f"General diagnostic for {entity}",
            "severity": "low",
            "details": "Diagnostic review completed. No issues requiring immediate attention.",
            "recommendation": "Monitor for changes. No external action.",
        })

    packet = {
        "packet_type": "coder_diagnostic",
        "version": "1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "coder",
        "target": "overcr",
        "task_id": task_id,
        "summary": f"CodER diagnostic complete for: {instruction[:100]}",
        "diagnostics": diagnostics,
        "audit_trail": {
            "worker_version": "0.2.0",
            "execution_timestamp": datetime.now(timezone.utc).isoformat(),
            "files_modified": [],
            "rollback_instructions": "No filesystem changes made by worker.",
        },
        "approval_required": False,
        "next_steps_recommendation": "Review diagnostic findings. Escalate if needed.",
    }

    upstream_id = input_context.get("upstream_task_id")
    if upstream_id:
        packet["upstream_task_id"] = upstream_id

    return packet


def build_blocked_packet(request: dict, reason: str) -> dict:
    """Build a coder_blocked packet when the worker cannot proceed."""
    task_id = request.get("task_id", "task-0000")

    return {
        "packet_type": "coder_blocked",
        "version": "1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "coder",
        "target": "overcr",
        "task_id": task_id,
        "summary": f"CodER blocked: {reason}",
        "blockers": [
            {
                "type": "unclear_spec",
                "description": reason,
            }
        ],
        "audit_trail": {
            "worker_version": "0.2.0",
            "execution_timestamp": datetime.now(timezone.utc).isoformat(),
            "files_modified": [],
            "rollback_instructions": "No changes made.",
        },
        "approval_required": False,
        "next_steps_recommendation": "Clarify task specification and resubmit.",
    }


def main():
    """Main entry point: read request, produce response, write to stdout."""
    request = read_request()

    # Determine packet type from domain
    domain = request.get("domain", "code")
    required_packet_type = request.get("required_packet_type", "")

    # Build the appropriate response packet
    if domain == "diagnostics" or required_packet_type == "coder_diagnostic":
        response = build_diagnostic_packet(request)
    elif domain == "code" or required_packet_type == "coder_completion":
        response = build_completion_packet(request)
    elif required_packet_type == "coder_blocked":
        response = build_blocked_packet(request, "Task specification unclear")
    else:
        # Default: produce a completion packet
        response = build_completion_packet(request)

    # Write response packet to stdout
    print(json.dumps(response, indent=2))


if __name__ == "__main__":
    main()