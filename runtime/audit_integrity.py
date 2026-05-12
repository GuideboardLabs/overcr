"""
OverCR Runtime — Audit Integrity Verifier

Cross-references the append-only audit log (audit.jsonl) against filesystem
task records (task-NNNN.json) to detect:

  - Missing audit entries (task has state_log entries with no audit counterpart)
  - Tampered audit entries (audit entry details don't match task record)
  - Orphaned audit entries (audit references a task_id with no task record)
  - State machine violations in audit trail (impossible state transitions)
  - Timestamp ordering anomalies (entries out of chronological order)

This module operates in READ-ONLY mode. It never modifies the audit log or
task records. It produces an integrity report with findings and an overall
integrity_risk level: "none", "low", "medium", "high".

Usage:
    from runtime.audit_integrity import AuditIntegrityVerifier
    verifier = AuditIntegrityVerifier(root)
    report = verifier.verify()
    print(report["integrity_risk"])  # "none", "low", "medium", "high"
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from runtime.task_store import TaskStore, VALID_TRANSITIONS


# ── Severity levels ──────────────────────────────────────────────────

SEVERITY_NONE = "none"
SEVERITY_LOW = "low"
SEVERITY_MEDIUM = "medium"
SEVERITY_HIGH = "high"

SEVERITY_ORDER = [SEVERITY_NONE, SEVERITY_LOW, SEVERITY_MEDIUM, SEVERITY_HIGH]


def worst_severity(a: str, b: str) -> str:
    """Return the worse of two severity levels."""
    return a if SEVERITY_ORDER.index(a) >= SEVERITY_ORDER.index(b) else b


# ── Valid transition set (for audit trail validation) ─────────────────

# Extends task_store transitions with the (init) -> created entry
AUDIT_TRANSITIONS = dict(VALID_TRANSITIONS)
AUDIT_TRANSITIONS["(init)"] = {"created"}


class AuditIntegrityVerifier:
    """
    Read-only verifier that cross-references audit log entries against
    filesystem task records.
    """

    def __init__(self, root: str):
        """
        Args:
            root: Path to the OverCR core directory containing
                  orchestration/ and runtime/audit.jsonl
        """
        self.root = Path(root)
        self.task_store = TaskStore(root)
        self.audit_path = self.root / "runtime" / "audit.jsonl"

    def _read_audit_entries(self) -> list[dict]:
        """Read all audit entries from the JSONL file."""
        if not self.audit_path.exists():
            return []
        entries = []
        with open(self.audit_path, "r") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    entry["_line_num"] = line_num
                    entries.append(entry)
                except json.JSONDecodeError as e:
                    entries.append({
                        "_line_num": line_num,
                        "_parse_error": str(e),
                        "_raw_line": line[:200],
                    })
        return entries

    def _task_state_log_index(self, task: dict) -> dict:
        """
        Build an index of (task_id, state) -> state_log entry from a task
        record, keyed for cross-referencing with audit entries.
        """
        index = {}
        for entry in task.get("state_log", []):
            key = (task["task_id"], entry["state"])
            index[key] = entry
        return index

    def verify(self) -> dict:
        """
        Run full audit integrity verification.

        Returns a report dict with:
          - integrity_risk: "none" | "low" | "medium" | "high"
          - findings: list of finding dicts, each with:
              - severity: "low" | "medium" | "high"
              - category: finding category string
              - task_id: relevant task_id or "runtime"
              - message: human-readable description
              - detail: additional detail dict
          - stats: summary statistics
        """
        findings = []
        overall_severity = SEVERITY_NONE

        # ── Load data ──
        audit_entries = self._read_audit_entries()
        tasks = self.task_store.list_tasks()
        task_map = {t["task_id"]: t for t in tasks}

        # ── Stats ──
        stats = {
            "audit_entries": len(audit_entries),
            "task_records": len(tasks),
            "audit_task_ids": set(),
            "parse_errors": 0,
        }

        # ── Phase 1: Parse errors ──
        for entry in audit_entries:
            if "_parse_error" in entry:
                stats["parse_errors"] += 1
                findings.append({
                    "severity": SEVERITY_HIGH,
                    "category": "audit_parse_error",
                    "task_id": "runtime",
                    "message": f"Audit log line {entry['_line_num']} is not valid JSON",
                    "detail": {
                        "line_num": entry["_line_num"],
                        "error": entry["_parse_error"],
                        "raw_snippet": entry.get("_raw_line", ""),
                    },
                })
                overall_severity = worst_severity(overall_severity, SEVERITY_HIGH)

        # ── Separate valid entries from parse errors ──
        valid_entries = [e for e in audit_entries if "_parse_error" not in e]
        for entry in valid_entries:
            stats["audit_task_ids"].add(entry.get("task_id", "unknown"))

        # ── Phase 2: Missing audit entries (task state_log has no audit counterpart) ──
        # Build audit index: (task_id, to_state) -> list of entries
        audit_state_index = {}
        for entry in valid_entries:
            if entry.get("entry_type") == "state_transition":
                tid = entry.get("task_id")
                to_state = entry.get("details", {}).get("to_state")
                key = (tid, to_state)
                if key not in audit_state_index:
                    audit_state_index[key] = []
                audit_state_index[key].append(entry)

        for task in tasks:
            tid = task["task_id"]
            for log_entry in task.get("state_log", []):
                state = log_entry["state"]
                key = (tid, state)
                if key not in audit_state_index:
                    findings.append({
                        "severity": SEVERITY_MEDIUM,
                        "category": "missing_audit_entry",
                        "task_id": tid,
                        "message": f"Task {tid} state_log has '{state}' but no matching audit entry",
                        "detail": {
                            "task_id": tid,
                            "state": state,
                            "state_log_timestamp": log_entry.get("timestamp"),
                            "note": log_entry.get("note"),
                        },
                    })
                    overall_severity = worst_severity(overall_severity, SEVERITY_MEDIUM)

        # ── Phase 3: Orphaned audit entries (task_id not in task records) ──
        known_task_ids = set(task_map.keys())
        for entry in valid_entries:
            tid = entry.get("task_id")
            if tid and tid != "runtime" and tid not in known_task_ids:
                findings.append({
                    "severity": SEVERITY_LOW,
                    "category": "orphaned_audit_entry",
                    "task_id": tid,
                    "message": f"Audit entry references task_id '{tid}' but no task record exists",
                    "detail": {
                        "task_id": tid,
                        "entry_type": entry.get("entry_type"),
                        "line_num": entry.get("_line_num"),
                    },
                })
                overall_severity = worst_severity(overall_severity, SEVERITY_LOW)

        # ── Phase 4: State transition violations in audit trail ──
        for task in tasks:
            tid = task["task_id"]
            # Get all state_transition audit entries for this task, in order
            task_transitions = [
                e for e in valid_entries
                if e.get("task_id") == tid
                and e.get("entry_type") == "state_transition"
            ]
            # Sort by line number (order of appearance = chronological order)
            task_transitions.sort(key=lambda e: e.get("_line_num", 0))

            for entry in task_transitions:
                details = entry.get("details", {})
                from_state = details.get("from_state")
                to_state = details.get("to_state")

                # (init) -> created is valid
                if from_state == "(init)" and to_state == "created":
                    continue

                # Check against valid transitions
                if from_state in AUDIT_TRANSITIONS:
                    if to_state not in AUDIT_TRANSITIONS[from_state]:
                        findings.append({
                            "severity": SEVERITY_HIGH,
                            "category": "invalid_state_transition",
                            "task_id": tid,
                            "message": (
                                f"Task {tid} has invalid state transition "
                                f"'{from_state}' -> '{to_state}' in audit trail"
                            ),
                            "detail": {
                                "task_id": tid,
                                "from_state": from_state,
                                "to_state": to_state,
                                "line_num": entry.get("_line_num"),
                                "allowed": list(AUDIT_TRANSITIONS.get(from_state, set())),
                            },
                        })
                        overall_severity = worst_severity(overall_severity, SEVERITY_HIGH)

        # ── Phase 5: Audit detail mismatches (task record contradicts audit) ──
        for entry in valid_entries:
            if entry.get("entry_type") != "state_transition":
                continue
            tid = entry.get("task_id")
            if tid not in task_map:
                continue  # orphaned — already flagged

            task = task_map[tid]
            details = entry.get("details", {})
            to_state = details.get("to_state")

            # Check that the task's current state_log contains this transition
            state_log_states = [s["state"] for s in task.get("state_log", [])]
            if to_state and to_state not in state_log_states:
                # The audit says the task entered this state, but state_log doesn't have it
                findings.append({
                    "severity": SEVERITY_HIGH,
                    "category": "audit_task_mismatch",
                    "task_id": tid,
                    "message": (
                        f"Audit says task {tid} transitioned to '{to_state}' "
                        f"but task state_log does not contain this state"
                    ),
                    "detail": {
                        "task_id": tid,
                        "audit_to_state": to_state,
                        "task_current_state": task.get("state"),
                        "task_state_log_states": state_log_states,
                    },
                })
                overall_severity = worst_severity(overall_severity, SEVERITY_HIGH)

        # ── Phase 6: Timestamp ordering anomalies ──
        for task in tasks:
            tid = task["task_id"]
            task_audit = [
                e for e in valid_entries
                if e.get("task_id") == tid
            ]
            task_audit.sort(key=lambda e: e.get("_line_num", 0))

            # Check that timestamps are non-decreasing within a task's entries
            prev_ts = None
            for entry in task_audit:
                ts_str = entry.get("timestamp")
                if not ts_str:
                    continue
                try:
                    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    continue
                if prev_ts and ts < prev_ts:
                    findings.append({
                        "severity": SEVERITY_LOW,
                        "category": "timestamp_anomaly",
                        "task_id": tid,
                        "message": (
                            f"Task {tid} has out-of-order timestamps in audit trail"
                        ),
                        "detail": {
                            "task_id": tid,
                            "entry_type": entry.get("entry_type"),
                            "timestamp": ts_str,
                        },
                    })
                    overall_severity = worst_severity(overall_severity, SEVERITY_LOW)
                    break  # Only flag once per task
                prev_ts = ts

        # ── Phase 7: Terminal state audit completeness ──
        for task in tasks:
            tid = task["task_id"]
            final_state = task.get("state")
            if final_state in ("completed", "abandoned"):
                # Should have a task_completed or task_abandoned audit entry
                completion_entries = [
                    e for e in valid_entries
                    if e.get("task_id") == tid
                    and e.get("entry_type") in ("task_completed", "task_abandoned")
                ]
                if not completion_entries:
                    findings.append({
                        "severity": SEVERITY_MEDIUM,
                        "category": "missing_completion_audit",
                        "task_id": tid,
                        "message": (
                            f"Task {tid} is in '{final_state}' state but has no "
                            f"completion audit entry"
                        ),
                        "detail": {
                            "task_id": tid,
                            "task_state": final_state,
                        },
                    })
                    overall_severity = worst_severity(overall_severity, SEVERITY_MEDIUM)

        # ── Build report ──
        stats["audit_task_ids"] = sorted(stats["audit_task_ids"])
        findings_by_severity = {
            SEVERITY_LOW: [f for f in findings if f["severity"] == SEVERITY_LOW],
            SEVERITY_MEDIUM: [f for f in findings if f["severity"] == SEVERITY_MEDIUM],
            SEVERITY_HIGH: [f for f in findings if f["severity"] == SEVERITY_HIGH],
        }

        return {
            "integrity_risk": overall_severity,
            "findings": findings,
            "findings_by_severity": findings_by_severity,
            "stats": stats,
            "summary": {
                "total_findings": len(findings),
                "high": len(findings_by_severity[SEVERITY_HIGH]),
                "medium": len(findings_by_severity[SEVERITY_MEDIUM]),
                "low": len(findings_by_severity[SEVERITY_LOW]),
                "integrity_risk": overall_severity,
            },
        }

    def verify_task(self, task_id: str) -> dict:
        """
        Verify audit integrity for a single task.

        Returns a subset of the full verify() report focused on one task.
        """
        full_report = self.verify()
        task_findings = [
            f for f in full_report["findings"]
            if f.get("task_id") == task_id
        ]
        worst = SEVERITY_NONE
        for f in task_findings:
            worst = worst_severity(worst, f["severity"])

        return {
            "task_id": task_id,
            "integrity_risk": worst,
            "findings": task_findings,
            "total_findings": len(task_findings),
        }