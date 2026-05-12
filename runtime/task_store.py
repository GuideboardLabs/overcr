"""
OverCR Runtime — Task Store

Filesystem-backed task record management. Every state transition is written
to disk immediately. No task state lives only in memory.

Task records are stored at <root>/orchestration/tasks/task-NNNN.json
Task counter is at <root>/orchestration/task_counter.json

This module is the single source of truth for task CRUD.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Canonical state machine (v0.0.5 spec)
VALID_STATES = {
    "created",
    "assigned",
    "in_progress",
    "response_received",
    "validation_passed",
    "validation_failed",
    "routed",
    "approval_pending",
    "approved",
    "rejected",
    "completed",
    "abandoned",
}

# Valid transitions: from_state -> set(allowed_to_states)
VALID_TRANSITIONS = {
    "created":            {"assigned", "abandoned"},
    "assigned":            {"in_progress", "abandoned"},
    "in_progress":        {"response_received", "abandoned"},
    "response_received":  {"validation_passed", "validation_failed"},
    "validation_passed":  {"routed"},
    "validation_failed":  {"assigned", "abandoned"},  # revision loop or abandon
    "routed":             {"approval_pending", "completed"},
    "approval_pending":   {"approved", "rejected"},
    "approved":           {"completed"},
    "rejected":           {"assigned", "abandoned"},   # revision loop or abandon
    "completed":          set(),                       # terminal
    "abandoned":          set(),                       # terminal
}

# Subagent selection by domain
DOMAIN_SUBAGENT_MAP = {
    "recon":          "cryer",
    "outreach":       "pyper",
    "code":           "coder",
    "research":       "knower",
    "analysis":       "knower",
    "diagnostics":    "coder",
    "patch_plan":    "coder",
    "outreach_draft": "pyper",
    "execution_plan":  "pyper",
    "claim_review":   "knower",
    "myth_fact":      "knower",
    "reputation_signal": "cryer",
    "engagement_signal": "cryer",
    "booking_friction": "cryer",
    "directory_completeness": "cryer",
    "hiring_growth": "cryer",
}

# Packet types per subagent (mirrors validate_packet.py)
SUBAGENT_PACKET_TYPES = {
    "cryer":  {"cryer_recon", "cryer_reputation_signal", "cryer_engagement_signal", "cryer_booking_friction", "cryer_directory_completeness", "cryer_hiring_growth"},
    "pyper":  {"pyper_approval", "pyper_revision", "pyper_objection_response", "pyper_execution_plan", "pyper_execution_receipt", "pyper_execution_refusal"},
    "coder":  {"coder_completion", "coder_blocked", "coder_diagnostic", "coder_patch_plan"},
    "knower": {"knower_research", "knower_assessment", "knower_myth_separation", "knower_claim_review", "knower_myth_fact"},
}

# Domains that require approval (PypER always, others when gated)
APPROVAL_REQUIRED_DOMAINS = {"outreach", "outreach_draft"}


class TaskStore:
    """
    Filesystem-backed task record store.

    All operations write to disk immediately. Reading reconstructs state
    from disk — the filesystem is canonical truth.
    """

    def __init__(self, root: str):
        """
        Args:
            root: Path to the OverCR core directory containing
                  orchestration/task_counter.json and orchestration/tasks/
        """
        self.root = Path(root)
        self.tasks_dir = self.root / "orchestration" / "tasks"
        self.counter_path = self.root / "orchestration" / "task_counter.json"
        self._ensure_dirs()

    def _ensure_dirs(self):
        self.tasks_dir.mkdir(parents=True, exist_ok=True)

    # ── Task ID Management ──────────────────────────────────

    def _read_counter(self) -> int:
        """Read and return the current last_task_id from the counter file."""
        if not self.counter_path.exists():
            return 0
        with open(self.counter_path, "r") as f:
            data = json.load(f)
        return int(data.get("last_task_id", 0))

    def _write_counter(self, last_id: int):
        """Write the counter file with the given last_task_id."""
        data = {
            "last_task_id": f"{last_id:04d}",
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }
        with open(self.counter_path, "w") as f:
            json.dump(data, f, indent=2)

    def next_task_id(self) -> str:
        """Atomically increment and return the next task ID in format task-NNNN."""
        current = self._read_counter()
        next_id = current + 1
        self._write_counter(next_id)
        return f"task-{next_id:04d}"

    # ── Task CRUD ────────────────────────────────────────────

    def create_task(
        self,
        assigned_subagent: str,
        domain: str,
        description: str,
        instruction: str,
        input_context: dict,
        constraints: list[str] | None = None,
        required_packet_type: str | None = None,
        upstream_task_id: str | None = None,
    ) -> dict:
        """
        Create a new task record and write it to disk.

        Returns the complete task record dict.
        """
        task_id = self.next_task_id()

        if constraints is None:
            constraints = [
                "Public signals only. No private data.",
                "No outbound contact.",
            ]

        if required_packet_type is None:
            required_packet_type = self._default_packet_type(assigned_subagent, domain)

        request_packet = {
            "task_id": task_id,
            "assigned_subagent": assigned_subagent,
            "domain": domain,
            "instruction": instruction,
            "input_context": input_context,
            "constraints": constraints,
            "required_packet_type": required_packet_type,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        task = {
            "task_id": task_id,
            "upstream_task_id": upstream_task_id,
            "created_at": request_packet["created_at"],
            "created_by": "overcr",
            "assigned_subagent": assigned_subagent,
            "domain": domain,
            "description": description,
            "state": "created",
            "revision_count": 0,
            "state_log": [
                {
                    "state": "created",
                    "timestamp": request_packet["created_at"],
                    "note": f"Task created by OverCR — {description}",
                }
            ],
            "request_packet": request_packet,
            "response_packet": None,
            "validation_result": None,
            "routing_decision": None,
            "operator_approval": None,
        }

        self._write_task(task)
        return task

    def _default_packet_type(self, subagent: str, domain: str) -> str:
        """Return the default packet type for a subagent/domain combo."""
        defaults = {
            "cryer":  {"recon": "cryer_recon", "reputation_signal": "cryer_reputation_signal", "engagement_signal": "cryer_engagement_signal", "booking_friction": "cryer_booking_friction", "directory_completeness": "cryer_directory_completeness", "hiring_growth": "cryer_hiring_growth"},
            "pyper":  {"outreach": "pyper_approval", "outreach_draft": "pyper_approval", "execution_plan": "pyper_execution_plan"},
            "coder":  {"code": "coder_completion", "diagnostics": "coder_diagnostic", "patch_plan": "coder_patch_plan"},
            "knower": {"research": "knower_research", "analysis": "knower_assessment", "claim_review": "knower_claim_review", "myth_fact": "knower_myth_fact"},
        }
        sub_defaults = defaults.get(subagent, {})
        return sub_defaults.get(domain, list(SUBAGENT_PACKET_TYPES.get(subagent, ["unknown"]))[0])

    def load_task(self, task_id: str) -> dict:
        """Load a task record from disk by task_id."""
        path = self.tasks_dir / f"{task_id}.json"
        if not path.exists():
            raise FileNotFoundError(f"Task record not found: {path}")
        with open(path, "r") as f:
            return json.load(f)

    def _write_task(self, task: dict):
        """Write a task record to disk."""
        path = self.tasks_dir / f"{task['task_id']}.json"
        with open(path, "w") as f:
            json.dump(task, f, indent=2)

    def advance_state(self, task_id: str, new_state: str, note: str) -> dict:
        """
        Advance a task to a new state. Validates the transition
        and writes to disk immediately.

        Returns the updated task record.
        """
        task = self.load_task(task_id)
        old_state = task["state"]

        if old_state == new_state:
            return task  # idempotent

        if new_state not in VALID_STATES:
            raise ValueError(f"Invalid state: {new_state}. Valid: {VALID_STATES}")

        allowed = VALID_TRANSITIONS.get(old_state, set())
        if new_state not in allowed:
            raise ValueError(
                f"Invalid transition: {old_state} -> {new_state}. "
                f"Allowed from '{old_state}': {allowed}"
            )

        timestamp = datetime.now(timezone.utc).isoformat()
        task["state"] = new_state
        task["state_log"].append({
            "state": new_state,
            "timestamp": timestamp,
            "note": note,
        })

        self._write_task(task)
        return task

    def set_response_packet(self, task_id: str, packet: dict):
        """Store a response packet on the task record."""
        task = self.load_task(task_id)
        task["response_packet"] = packet
        self._write_task(task)

    def set_validation_result(self, task_id: str, result: dict):
        """Store a validation result on the task record."""
        task = self.load_task(task_id)
        task["validation_result"] = result
        self._write_task(task)

    def set_routing_decision(self, task_id: str, decision: dict):
        """Store a routing decision on the task record."""
        task = self.load_task(task_id)
        task["routing_decision"] = decision
        self._write_task(task)

    def set_operator_approval(self, task_id: str, approval: dict):
        """Store an operator approval/rejection on the task record."""
        task = self.load_task(task_id)
        task["operator_approval"] = approval
        self._write_task(task)

    def increment_revision(self, task_id: str) -> dict:
        """Increment the revision count on a task. Returns updated task."""
        task = self.load_task(task_id)
        task["revision_count"] = task.get("revision_count", 0) + 1
        self._write_task(task)
        return task

    def revision_count(self, task_id: str) -> int:
        """Return the current revision count for a task."""
        task = self.load_task(task_id)
        return task.get("revision_count", 0)

    def select_subagent(self, domain: str) -> str:
        """Select a subagent based on the task domain."""
        subagent = DOMAIN_SUBAGENT_MAP.get(domain)
        if subagent is None:
            raise ValueError(
                f"Unknown domain: '{domain}'. "
                f"Known domains: {list(DOMAIN_SUBAGENT_MAP.keys())}"
            )
        return subagent

    def list_tasks(self) -> list[dict]:
        """List all task records from disk."""
        tasks = []
        for path in sorted(self.tasks_dir.glob("task-*.json")):
            with open(path, "r") as f:
                tasks.append(json.load(f))
        return tasks

    def task_summary(self, task_id: str) -> dict:
        """Produce an operator-facing task summary packet.

        Trust boundary: This method uses ONLY filesystem-validated state
        for governance fields. Packet claims are isolated in a separate
        packet_claims section. Governance fields are filled with defaults
        here and MUST be overwritten by the runtime's operator_summary()
        which computes them from ApprovalGate — never from packet payloads.
        """
        task = self.load_task(task_id)
        response = task.get("response_packet") or {}
        validation = task.get("validation_result")

        # ── Validated state (filesystem-authoritative) ──
        summary_data = {
            "operator_packet_type": "task_summary",
            "task_id": task["task_id"],
            "upstream_task_id": task.get("upstream_task_id"),
            "state": task["state"],
            "subagent": task["assigned_subagent"],
            "packet_type": response.get("packet_type", "pending"),
            "summary": response.get("summary", task["description"]),

            # Governance: defaults only — runtime overrides these
            "governance": {
                "approval_required": None,       # filled by runtime from ApprovalGate
                "outbound_blocked": None,        # filled by runtime from ApprovalGate
                "outbound_block_reason": None,   # filled by runtime from ApprovalGate
                "execution_authority": None,      # filled by runtime from ApprovalGate
                "validation_passed": validation.get("valid") if validation else None,
            },

            # Key findings extracted from packet data
            "key_findings": [],
            "risk_flags": [],

            # Packet claims — explicitly marked as untrusted
            "packet_claims": {
                "approval_required": response.get("approval_required"),
                "next_steps_recommendation": response.get("next_steps_recommendation", ""),
                "outbound_contact": response.get("outbound_contact"),
            },

            "next_steps": [],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Extract findings from response packet (data fields, not governance)
        if response:
            recon = response.get("recon_data", {})
            for t in recon.get("targets", []):
                rep = t.get("signals", {}).get("reputation", {})
                summary_data["key_findings"].append(
                    f"{t['entity']}: yield_score={rep.get('yield_score')}, "
                    f"confidence={rep.get('confidence')}"
                )

            draft = response.get("draft_data", {})
            for p in draft.get("prospects", []):
                summary_data["key_findings"].append(
                    f"Draft for {p['entity']} ({p['approach_type']})"
                )

            # Risk flags (data, not governance)
            for t in recon.get("targets", []):
                rep = t.get("signals", {}).get("reputation", {})
                summary_data["risk_flags"].extend(rep.get("risk_flags", []))

        # State-based next steps (runtime-authoritative, never from packet)
        state = task["state"]
        if state == "approval_pending":
            summary_data["next_steps"] = [
                "Review and approve/reject the packet",
                "If approved, the task proceeds to next hop or completion",
                "If rejected, specify revision feedback or abandon",
            ]
        elif state == "validation_failed":
            validation_errors = []
            if validation and validation.get("errors"):
                validation_errors = validation["errors"]
            summary_data["next_steps"] = [
                "Review validation errors" + (f" ({len(validation_errors)} found)" if validation_errors else ""),
                "Decide: request revision from subagent or abandon",
            ]
            if validation_errors:
                summary_data["next_steps"].append(
                    "Errors: " + "; ".join(validation_errors[:3])
                )
        elif state == "completed":
            approval = task.get("operator_approval") or {}
            if approval.get("decision") == "approved":
                summary_data["next_steps"] = [
                    "Task completed with operator approval. No further action."
                ]
            else:
                summary_data["next_steps"] = ["Task completed. No further action."]
        elif state == "rejected":
            summary_data["next_steps"] = [
                "Task rejected. Decide: send for revision or abandon.",
            ]
        elif state == "routed":
            routing = task.get("routing_decision") or {}
            target = routing.get("routing_target", "unknown")
            summary_data["next_steps"] = [
                f"Task routed to {target}. Awaiting next phase.",
            ]
        elif state == "created":
            summary_data["next_steps"] = ["Task created. Awaiting subagent acknowledgment."]
        elif state == "assigned":
            summary_data["next_steps"] = ["Task assigned. Awaiting subagent start."]
        elif state == "in_progress":
            summary_data["next_steps"] = ["Subagent working on task."]

        return summary_data


def resolve_subagent(domain: str) -> str:
    """Convenience function: resolve a domain to a subagent name."""
    return DOMAIN_SUBAGENT_MAP[domain]