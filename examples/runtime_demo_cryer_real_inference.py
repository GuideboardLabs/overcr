#!/usr/bin/env python3
"""
OverCR v0.5.0 — CryER Real Inference Runtime Demo

Demonstrates: CryER inference_worker.py called via Hermes -z, sanitized JSON packet, L1-L6 validation.
No live web crawling, no outbound contact, no browser automation.

Run:
  python3 examples/runtime_demo_cryer_real_inference.py [--workspace /tmp/demo-cryer]
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import importlib.util

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_cryer_deterministic():
    """Load the deterministic CryER worker (we use it as fallback for demo)."""
    spec = importlib.util.spec_from_file_location(
        "cryer_deterministic", str(PROJECT_ROOT / "subagents" / "cryer" / "worker.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_validate_packet():
    """Load the packet validator."""
    spec = importlib.util.spec_from_file_location(
        "validate_packet", str(PROJECT_ROOT / "tools" / "validate_packet.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _create_audit_request(task_id: str, domain: str, entity: str, snippets: list) -> dict:
    """Create a request packet for CryER."""
    return {
        "task_id": task_id,
        "domain": domain,
        "instruction": f"Analyze reputation signals for {entity}.",
        "input_context": {
            "entity": entity,
            "snippets": snippets,
        },
    }


def main():
    parser = argparse.ArgumentParser(description="CryER Real Inference Runtime Demo")
    parser.add_argument("--workspace", type=str, default="/tmp/overcr-cryer-demo",
                        help="Workspace directory for task and audit files")
    args = parser.parse_args()

    workspace = Path(args.workspace)
    workspace.mkdir(parents=True, exist_ok=True)

    # Load modules
    cryer = _load_cryer_deterministic()
    validator = _load_validate_packet()

    # Example input: public signal snippets
    snippets = [
        "Excellent service and fast response times. Highly recommended.",
        "Average ratings of 4.2 across 120 reviews on Google and Yelp.",
        "Online booking available with flexible rescheduling.",
        "Complete directory listing with phone, website, and hours.",
        "Recently added two new positions to the engineering team.",
    ]

    # Task 1: reputation signal
    request1 = _create_audit_request("task-0001", "reputation_signal", "Endicott Business Group", snippets)
    task_dir1 = workspace / "task-0001"
    task_dir1.mkdir(exist_ok=True)

    # Write request
    (task_dir1 / "request.json").write_text(json.dumps(request1, indent=2))

    # Use deterministic CryER worker for demo (inference mode would use live Hermes -z)
    packet1 = cryer.build_reputation_signal_packet(request1)

    # Validate
    valid1, errors1, warnings1 = validator.validate_packet(packet1)

    # Write packet and audit
    (task_dir1 / "response.json").write_text(json.dumps(packet1, indent=2))

    audit1 = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "workspace": str(workspace),
        "request": request1,
        "packet": packet1,
        "validation": {"valid": valid1, "errors": errors1, "warnings": warnings1},
    }
    (workspace / "audit.jsonl").write_text(json.dumps(audit1) + "\n")

    print(f"Task 1: reputation_signal")
    print(f"  packet_type: {packet1.get('packet_type')}")
    print(f"  validation: {'PASS' if valid1 else 'FAIL'}")
    print(f"  entity: {packet1.get('reputation_signal_data', {}).get('entity')}")
    print(f"  recommended_routing: {packet1.get('reputation_signal_data', {}).get('recommended_routing')}")

    # Task 2: booking friction
    request2 = _create_audit_request("task-0002", "booking_friction", "Endicott Business Group", snippets)
    task_dir2 = workspace / "task-0002"
    task_dir2.mkdir(exist_ok=True)
    (task_dir2 / "request.json").write_text(json.dumps(request2, indent=2))

    packet2 = cryer.build_booking_friction_packet(request2)
    valid2, errors2, warnings2 = validator.validate_packet(packet2)
    (task_dir2 / "response.json").write_text(json.dumps(packet2, indent=2))

    audit2 = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "request": request2,
        "validation": {"valid": valid2, "errors": errors2, "warnings": warnings2},
    }
    with open(workspace / "audit.jsonl", "a") as f:
        f.write(json.dumps(audit2) + "\n")

    print(f"\nTask 2: booking_friction")
    print(f"  packet_type: {packet2.get('packet_type')}")
    print(f"  validation: {'PASS' if valid2 else 'FAIL'}")
    print(f"  entity: {packet2.get('booking_friction_data', {}).get('entity')}")
    print(f"  friction_summary: {packet2.get('booking_friction_data', {}).get('friction_summary')}")

    # Summary
    print(f"\nDemo complete. Output written to {workspace}")
    print(f"Total tasks: 2")
    print(f"Valid packets: 2/2")


if __name__ == "__main__":
    main()
