"""
OverCR Runtime — Worker Healthcheck (v0.2.1)

Verifies that a live worker is functioning correctly by running it with
a minimal probe request and checking:

  1. The worker launches (exit code 0)
  2. The worker responds within timeout
  3. The worker emits valid packet schema (structural checks)
  4. The worker advertises expected capabilities

Healthcheck is non-destructive: failed healthchecks do NOT disable existing
runtime integrity or modify any task state. They only report status.

Safety guarantees:
  - Healthcheck sends a minimal probe packet, never real task data
  - Healthcheck results are informational only
  - Failed healthchecks never advance any task state
  - Healthcheck never modifies filesystem state beyond the worker's
    own temp/runtime packet handling
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from runtime.worker_runner import WorkerRunner, WorkerResult
from runtime.worker_registry import WorkerRegistry, WorkerRegistration
from runtime.worker_capabilities import (
    validate_capabilities,
    validate_packet_types,
    get_capability_summary,
)


# Standard probe packet template for healthchecks
# This is a minimal request packet that any worker should be able to process
HEALTHCHECK_PROBE = {
    "task_id": "healthcheck-0000",
    "domain": "healthcheck",
    "instruction": "Healthcheck probe — respond with a valid packet",
    "input_context": {},
    "required_packet_type": "",  # Worker chooses its default
}


class HealthcheckResult:
    """Result of a worker healthcheck."""

    def __init__(self):
        self.healthy: bool = False
        self.launch_ok: bool = False
        self.response_ok: bool = False
        self.schema_ok: bool = False
        self.capabilities_ok: bool = False
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.elapsed_seconds: float = 0.0
        self.exit_code: int = -1
        self.timed_out: bool = False
        self.response_packet: Optional[dict] = None

    def to_dict(self) -> dict:
        return {
            "healthy": self.healthy,
            "checks": {
                "launch": self.launch_ok,
                "response": self.response_ok,
                "schema": self.schema_ok,
                "capabilities": self.capabilities_ok,
            },
            "errors": self.errors,
            "warnings": self.warnings,
            "elapsed_seconds": self.elapsed_seconds,
            "exit_code": self.exit_code,
            "timed_out": self.timed_out,
            "response_packet": self.response_packet,
        }


LEVEL1_REQUIRED_FIELDS = {
    "packet_type", "version", "timestamp", "source", "target", "task_id", "summary"
}


def check_worker_health(
    worker_path: Path,
    registration: WorkerRegistration,
    timeout: float = 15.0,
    probe_packet: Optional[dict] = None,
) -> HealthcheckResult:
    """
    Run a healthcheck on a worker.

    Args:
        worker_path: Absolute path to the worker script
        registration: The worker's registration entry
        timeout: Maximum seconds to wait for the worker
        probe_packet: Custom probe packet (default: minimal healthcheck probe)

    Returns:
        HealthcheckResult with detailed check outcomes
    """
    result = HealthcheckResult()
    runner = WorkerRunner()

    # Use provided probe or the default
    probe = probe_packet or dict(HEALTHCHECK_PROBE)

    # ── Check 1: Launch ──
    worker_result: WorkerResult = runner.run(
        worker_script=worker_path,
        input_packet=probe,
        timeout=timeout,
        task_id="healthcheck-0000",
    )

    result.exit_code = worker_result.exit_code
    result.timed_out = worker_result.timed_out
    result.elapsed_seconds = worker_result.elapsed_seconds

    if worker_result.timed_out:
        result.errors.append(f"Worker timed out after {timeout}s")
        # Launch check: process started but timed out
        result.launch_ok = True  # it launched, just didn't finish
        return result

    if worker_result.exit_code != 0:
        result.errors.append(
            f"Worker exited with code {worker_result.exit_code}. "
            f"stderr: {worker_result.stderr_summary}"
        )
        result.launch_ok = False
        return result

    result.launch_ok = True

    # ── Check 2: Response (valid JSON) ──
    if not worker_result.stdout_raw.strip():
        result.errors.append("Worker produced no output")
        return result

    try:
        packet = json.loads(worker_result.stdout_raw)
    except json.JSONDecodeError as e:
        result.errors.append(f"Worker output is not valid JSON: {e}")
        return result

    if not isinstance(packet, dict):
        result.errors.append(f"Worker output is not a JSON object: {type(packet).__name__}")
        return result

    result.response_ok = True
    result.response_packet = packet

    # ── Check 3: Schema (Level 1 structural integrity) ──
    missing_fields = LEVEL1_REQUIRED_FIELDS - set(packet.keys())
    if missing_fields:
        result.errors.append(f"Missing required L1 fields: {sorted(missing_fields)}")
    else:
        # Validate field values
        schema_errors = []
        if packet.get("version") != "1.0":
            schema_errors.append(f"version is '{packet.get('version')}', expected '1.0'")
        if packet.get("target") != "overcr":
            schema_errors.append(f"target is '{packet.get('target')}', expected 'overcr'")
        if not isinstance(packet.get("summary"), str) or not packet["summary"].strip():
            schema_errors.append("summary is empty or not a string")

        if packet.get("source") != registration.subagent:
            result.warnings.append(
                f"Packet source is '{packet.get('source')}', "
                f"expected '{registration.subagent}'"
            )

        if packet.get("packet_type") not in registration.supported_packet_types:
            result.warnings.append(
                f"Packet type '{packet.get('packet_type')}' is not in "
                f"declared supported types: {sorted(registration.supported_packet_types)}"
            )

        if schema_errors:
            result.errors.extend(schema_errors)
        else:
            result.schema_ok = True

    # ── Check 4: Capabilities ──
    cap_check = validate_capabilities(registration)
    pkt_check = validate_packet_types(registration)

    if not cap_check.valid:
        result.errors.extend(cap_check.errors)
    result.warnings.extend(cap_check.warnings)

    if not pkt_check.valid:
        result.errors.extend(pkt_check.errors)
    result.warnings.extend(pkt_check.warnings)

    result.capabilities_ok = cap_check.valid and pkt_check.valid

    # ── Overall health ──
    result.healthy = (
        result.launch_ok
        and result.response_ok
        and result.schema_ok
        and result.capabilities_ok
    )

    return result


def check_all_workers(
    root: str,
    registry: WorkerRegistry,
    timeout: float = 15.0,
) -> Dict[str, HealthcheckResult]:
    """
    Run healthchecks on all registered workers.

    Args:
        root: OverCR root directory (for resolving worker paths)
        registry: The worker registry to check

    Returns:
        Dict mapping subagent name to HealthcheckResult
    """
    results = {}
    root_path = Path(root)

    for reg in registry.list_registrations():
        worker_path = root_path / reg.worker_path
        results[reg.subagent] = check_worker_health(
            worker_path=worker_path,
            registration=reg,
            timeout=timeout,
        )

    return results