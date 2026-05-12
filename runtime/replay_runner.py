"""
OverCR Runtime — Replay Runner (v0.2.1)

Replays prior task/audit history from filesystem state. The replay runner
reconstructs the task lifecycle deterministically by re-reading the
task records and audit log from disk.

Replay is strictly read-only:
  - It NEVER modifies task records, audit logs, or any filesystem state
  - It NEVER advances task state
  - It NEVER invokes workers or makes routing decisions
  - It NEVER contacts any external service

Safety guarantees:
  - All file reads are non-mutating (open for read only)
  - Replay produces a deterministic report for a given filesystem state
  - Tampered audit history is detected
  - Inconsistent state transitions are flagged
  - Replay never triggers side effects
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set

from runtime.task_store import TaskStore, VALID_STATES, VALID_TRANSITIONS
from runtime.audit_writer import AuditWriter
from runtime.audit_integrity import AuditIntegrityVerifier


class ReplayStep:
    """A single step in the replay sequence."""

    def __init__(
        self,
        task_id: str,
        step_type: str,
        from_state: Optional[str],
        to_state: str,
        timestamp: str,
        details: Optional[dict] = None,
        consistent: bool = True,
        issue: Optional[str] = None,
    ):
        self.task_id = task_id
        self.step_type = step_type  # "state_transition", "validation", "routing", "approval", etc.
        self.from_state = from_state
        self.to_state = to_state
        self.timestamp = timestamp
        self.details = details or {}
        self.consistent = consistent
        self.issue = issue

    def to_dict(self) -> dict:
        d = {
            "task_id": self.task_id,
            "step_type": self.step_type,
            "from_state": self.from_state,
            "to_state": self.to_state,
            "timestamp": self.timestamp,
            "consistent": self.consistent,
        }
        if self.issue:
            d["issue"] = self.issue
        if self.details:
            d["details"] = self.details
        return d


class ReplayResult:
    """Complete result of a replay run."""

    def __init__(self):
        self.tasks_replayed: int = 0
        self.steps: List[ReplayStep] = []
        self.inconsistencies: List[dict] = []
        self.integrity_risk: str = "none"
        self.tamper_detected: bool = False
        self.audit_consistent: bool = True
        self.state_machine_violations: List[str] = []
        self.timestamp_ordering_ok: bool = True

    def to_dict(self) -> dict:
        return {
            "tasks_replayed": self.tasks_replayed,
            "total_steps": len(self.steps),
            "inconsistencies": self.inconsistencies,
            "integrity_risk": self.integrity_risk,
            "tamper_detected": self.tamper_detected,
            "audit_consistent": self.audit_consistent,
            "state_machine_violations": self.state_machine_violations,
            "timestamp_ordering_ok": self.timestamp_ordering_ok,
            "steps": [s.to_dict() for s in self.steps],
        }


def replay_task(task_id: str, store: TaskStore) -> List[ReplayStep]:
    """
    Replay a single task's lifecycle from its filesystem state.

    Reconstructs the state machine transitions from the task's state_log
    and validates each transition.

    This is read-only — it never modifies the task record.
    """
    task = store.load_task(task_id)
    if task is None:
        return [ReplayStep(
            task_id=task_id,
            step_type="error",
            from_state=None,
            to_state="error",
            timestamp=datetime.now(timezone.utc).isoformat(),
            consistent=False,
            issue=f"Task {task_id} not found",
        )]

    steps = []
    state_log = task.get("state_log", [])

    for i, entry in enumerate(state_log):
        from_state = entry.get("from_state")
        to_state = entry.get("to_state", entry.get("state"))
        timestamp = entry.get("timestamp", "")
        note = entry.get("note", "")

        # Validate state transition
        consistent = True
        issue = None

        if from_state and to_state:
            allowed = VALID_TRANSITIONS.get(from_state, set())
            if to_state not in allowed and to_state != from_state:
                # Check if it's a valid transition
                consistent = False
                issue = (
                    f"Invalid state transition: {from_state} -> {to_state} "
                    f"(allowed: {sorted(allowed)})"
                )

        step = ReplayStep(
            task_id=task_id,
            step_type="state_transition",
            from_state=from_state,
            to_state=to_state,
            timestamp=timestamp,
            details={"note": note},
            consistent=consistent,
            issue=issue,
        )
        steps.append(step)

    # Check that terminal states have no further transitions
    current_state = task.get("state")
    if current_state in ("completed", "abandoned"):
        terminal_transitions = [s for s in steps if s.from_state == current_state]
        for s in terminal_transitions:
            s.consistent = False
            s.issue = f"Terminal state {current_state} should have no outgoing transitions"

    return steps


def replay_all(root: str) -> ReplayResult:
    """
    Replay the complete lifecycle of all tasks from filesystem state.

    This is the primary entry point. It:
      1. Reads all task records from disk
      2. Replays each task's state transitions
      3. Runs audit integrity verification
      4. Detects tampering in audit history
      5. Validates state machine consistency
      6. Checks timestamp ordering

    All operations are read-only.
    """
    result = ReplayResult()

    # ── Initialize read-only stores ──
    store = TaskStore(root)

    # ── Replay each task ──
    tasks = store.list_tasks()
    result.tasks_replayed = len(tasks)

    for task_summary in tasks:
        task_id = task_summary.get("task_id", "")
        if not task_id:
            continue
        steps = replay_task(task_id, store)
        result.steps.extend(steps)

        # Collect inconsistencies
        for step in steps:
            if not step.consistent:
                result.inconsistencies.append({
                    "task_id": task_id,
                    "step": step.to_dict(),
                })
                result.state_machine_violations.append(
                    step.issue or f"Inconsistent step: {step.step_type}"
                )

    # ── Audit integrity check ──
    verifier = AuditIntegrityVerifier(root)
    integrity_report = verifier.verify()

    result.integrity_risk = integrity_report.get("integrity_risk", "unknown")
    result.audit_consistent = result.integrity_risk in ("none", "low")

    # ── Tamper detection ──
    findings = integrity_report.get("findings", [])
    high_findings = [f for f in findings if f.get("severity") == "high"]
    if high_findings:
        result.tamper_detected = True
        for finding in high_findings:
            result.inconsistencies.append({
                "task_id": finding.get("task_id", "unknown"),
                "type": "tamper_detection",
                "finding": finding,
            })

    # ── Timestamp ordering check ──
    # Verify that state transitions have monotonically non-decreasing timestamps
    for task_summary in tasks:
        task_id = task_summary.get("task_id", "")
        task = store.load_task(task_id)
        if task is None:
            continue

        state_log = task.get("state_log", [])
        prev_ts = None
        for entry in state_log:
            ts = entry.get("timestamp", "")
            if prev_ts and ts and ts < prev_ts:
                result.timestamp_ordering_ok = False
                result.inconsistencies.append({
                    "task_id": task_id,
                    "type": "timestamp_ordering",
                    "message": f"Out-of-order timestamp: {ts} after {prev_ts}",
                })
            if ts:
                prev_ts = ts

    return result


def replay_single_task(task_id: str, root: str) -> ReplayResult:
    """
    Replay a single task's lifecycle and check audit consistency for it.

    All operations are read-only.
    """
    result = ReplayResult()
    store = TaskStore(root)

    steps = replay_task(task_id, store)
    result.steps.extend(steps)
    result.tasks_replayed = 1

    # Collect inconsistencies
    for step in steps:
        if not step.consistent:
            result.inconsistencies.append({
                "task_id": task_id,
                "step": step.to_dict(),
            })
            result.state_machine_violations.append(
                step.issue or f"Inconsistent step: {step.step_type}"
            )

    # Audit integrity for this task
    verifier = AuditIntegrityVerifier(root)
    task_integrity = verifier.verify_task(task_id)
    task_risk = task_integrity.get("integrity_risk", "unknown")
    result.integrity_risk = task_risk
    result.audit_consistent = task_risk in ("none", "low")

    if task_risk in ("medium", "high"):
        findings = task_integrity.get("findings", [])
        if any(f.get("severity") == "high" for f in findings):
            result.tamper_detected = True

    # Timestamp ordering
    task = store.load_task(task_id)
    if task:
        state_log = task.get("state_log", [])
        prev_ts = None
        for entry in state_log:
            ts = entry.get("timestamp", "")
            if prev_ts and ts and ts < prev_ts:
                result.timestamp_ordering_ok = False
            if ts:
                prev_ts = ts

    return result