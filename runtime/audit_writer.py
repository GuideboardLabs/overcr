"""
OverCR Runtime — Audit Writer

Appends structured audit entries to the orchestration audit log.
Every state transition, validation, routing decision, approval action,
and operator interaction is recorded here.

Audit log location: <root>/runtime/audit.jsonl  (JSON Lines format)
Each line is a self-contained JSON object — no external references needed.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


class AuditWriter:
    """
    Append-only audit log writer.

    Each entry is a single JSON line written to audit.jsonl.
    The log is never truncated or rewritten — only appended to.
    """

    ENTRY_TYPES = {
        "state_transition",
        "task_created",
        "validation_result",
        "routing_decision",
        "approval_action",
        "operator_action",
        "revision_loop",
        "task_completed",
        "task_abandoned",
        "runtime_start",
        "runtime_stop",
        "error",
    }

    def __init__(self, root: str):
        """
        Args:
            root: Path to the OverCR core directory.
                  Audit log will be at <root>/runtime/audit.jsonl
        """
        self.root = Path(root)
        self.audit_dir = self.root / "runtime"
        self.audit_path = self.audit_dir / "audit.jsonl"
        self.audit_dir.mkdir(parents=True, exist_ok=True)

    def write(self, entry_type: str, task_id: str, details: dict) -> dict:
        """
        Append an audit entry to the log.

        Args:
            entry_type: One of ENTRY_TYPES.
            task_id: The task this entry relates to (or "runtime" for system events).
            details: Arbitrary dict of details about the event.

        Returns:
            The complete audit entry dict (also written to disk).
        """
        if entry_type not in self.ENTRY_TYPES:
            raise ValueError(
                f"Unknown audit entry type: '{entry_type}'. "
                f"Valid types: {sorted(self.ENTRY_TYPES)}"
            )

        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "entry_type": entry_type,
            "task_id": task_id,
            "details": details,
        }

        with open(self.audit_path, "a") as f:
            f.write(json.dumps(entry) + "\n")

        return entry

    def state_transition(
        self,
        task_id: str,
        from_state: str,
        to_state: str,
        note: str,
        extra: Optional[dict] = None,
    ) -> dict:
        """Record a task state transition."""
        details = {
            "from_state": from_state,
            "to_state": to_state,
            "note": note,
        }
        if extra:
            details.update(extra)
        return self.write("state_transition", task_id, details)

    def task_created(self, task_id: str, subagent: str, domain: str, description: str) -> dict:
        """Record task creation."""
        return self.write("task_created", task_id, {
            "subagent": subagent,
            "domain": domain,
            "description": description,
        })

    def validation_result(self, task_id: str, valid: bool, errors: list, warnings: list) -> dict:
        """Record a packet validation result."""
        return self.write("validation_result", task_id, {
            "valid": valid,
            "error_count": len(errors),
            "warning_count": len(warnings),
            "errors": errors,
            "warnings": warnings,
        })

    def routing_decision(self, task_id: str, target: str, reason: str, creates_downstream: bool = False) -> dict:
        """Record a routing decision."""
        return self.write("routing_decision", task_id, {
            "routing_target": target,
            "reason": reason,
            "creates_downstream_task": creates_downstream,
        })

    def approval_action(
        self,
        task_id: str,
        action: str,
        decision: str,
        reason: Optional[str] = None,
        operator: str = "operator",
    ) -> dict:
        """Record an approval gate action (approve/reject)."""
        details = {
            "gate_action": action,
            "decision": decision,
            "operator": operator,
        }
        if reason:
            details["reason"] = reason
        return self.write("approval_action", task_id, details)

    def revision_loop(self, task_id: str, revision_count: int, reason: str) -> dict:
        """Record a revision loop iteration."""
        return self.write("revision_loop", task_id, {
            "revision_count": revision_count,
            "reason": reason,
        })

    def task_completed(self, task_id: str, final_state: str, summary: str) -> dict:
        """Record task completion or abandonment."""
        entry_type = "task_completed" if final_state == "completed" else "task_abandoned"
        return self.write(entry_type, task_id, {
            "final_state": final_state,
            "summary": summary,
        })

    def runtime_event(self, event: str, details: Optional[dict] = None) -> dict:
        """Record a runtime-level event (start/stop/error)."""
        entry_type = event if event in self.ENTRY_TYPES else "error"
        return self.write(entry_type, "runtime", details or {})

    def read_log(self, task_id: Optional[str] = None, limit: int = 100) -> list[dict]:
        """
        Read audit entries from the log.

        Args:
            task_id: If given, filter to entries for this task.
            limit: Maximum number of entries to return.

        Returns:
            List of audit entry dicts, most recent last.
        """
        if not self.audit_path.exists():
            return []

        entries = []
        with open(self.audit_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if task_id is None or entry.get("task_id") == task_id:
                    entries.append(entry)

        return entries[-limit:]