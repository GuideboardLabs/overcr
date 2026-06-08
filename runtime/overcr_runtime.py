"""
OverCR Runtime — Main Runtime Driver (v0.2.1)

The smallest useful runtime driver for the OverCR orchestration system.
This module ties together task_store, audit_writer, approval_gate, and
validate_packet.py into an executable pipeline.

What it DOES:
  - Create task records with assigned IDs
  - Select subagent type from domain
  - Generate request packets
  - Accept response packets
  - Validate response packets using tools/validate_packet.py
  - Advance task lifecycle states (filesystem-first)
  - Enforce approval_required gates
  - Write audit entries for every transition
  - Store outputs in filesystem state
  - Produce operator-facing summaries
  - Invoke live subagent workers via SubagentAdapter (v0.2.1)
  - Full pipeline: invoke -> receive -> validate -> route (v0.2.1)

What it does NOT do:
  - No web crawling
  - No autonomous outbound action
  - No database dependency
  - No new subagents
  - No uncontrolled loops
"""

import json
import sys
from pathlib import Path
from typing import Optional

from runtime.task_store import TaskStore, DOMAIN_SUBAGENT_MAP
from runtime.audit_writer import AuditWriter
from runtime.approval_gate import ApprovalGate, ApprovalGateError

# Import the existing validator from tools/
TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"


def _load_validator():
    """Dynamically load the existing validate_packet module from tools/."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "validate_packet",
        TOOLS_DIR / "validate_packet.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class OverCRRuntime:
    """
    The OverCR v0.1.0 runtime driver.

    Orchestrates the complete task lifecycle using:
    - TaskStore for filesystem state
    - AuditWriter for the append-only audit log
    - ApprovalGate for enforcement of approval gates
    - validate_packet.py for 6-level packet validation
    """

    def __init__(self, root: str, vault_path: str | None = None):
        """
        Args:
            root: Path to the OverCR core directory (contains orchestration/,
                  tools/, runtime/).
            vault_path: Optional path to an Obsidian vault. If set, OverCR
                        enriches task context with relevant vault facts.
        """
        self.root = Path(root)
        self.task_store = TaskStore(root)
        self.audit = AuditWriter(root)
        self.gate = ApprovalGate()
        self._validator = None
        self._adapter = None
        self._vault_index = None
        self.vault_path = str(vault_path) if vault_path else None

    @property
    def adapter(self):
        """Lazy-load the SubagentAdapter (avoid import overhead until needed)."""
        if self._adapter is None:
            from runtime.subagent_adapter import SubagentAdapter
            self._adapter = SubagentAdapter(str(self.root))
        return self._adapter

    @property
    def validator(self):
        """Lazy-load the validator module (avoid import overhead until needed)."""
        if self._validator is None:
            self._validator = _load_validator()
        return self._validator

    @property
    def vault_index(self):
        """Lazy-load the VaultIndex (only if vault_path is configured)."""
        if self._vault_index is None and self.vault_path:
            from knowledge.vault import VaultIndex
            self._vault_index = VaultIndex(self.vault_path)
            self._vault_index.rebuild()
        return self._vault_index

    # ── Phase 1: Task Creation ───────────────────────────────

    def create_task(
        self,
        domain: str,
        description: str,
        instruction: str,
        input_context: dict,
        constraints: list[str] | None = None,
        required_packet_type: str | None = None,
        upstream_task_id: str | None = None,
    ) -> dict:
        """
        Create a new task. Selects subagent based on domain,
        assigns task ID, generates request packet, writes to disk.

        Returns the complete task record.
        """
        # Select subagent
        subagent = self.task_store.select_subagent(domain)

        # Create task record — enrich context with vault facts if configured
        enriched_context = dict(input_context)
        vault = self.vault_index
        if vault:
            facts = vault.search(
                domain=domain,
                tags=description.split(),
                query=instruction,
                max_results=15,
            )
            if facts:
                enriched_context["_vault_facts"] = facts
                enriched_context["_vault_note"] = (
                    f"OverCR found {len(facts)} relevant vault facts "
                    f"for domain '{domain}'. "
                    f"Index includes {vault.stats()['notes_with_facts']} notes."
                )

        task = self.task_store.create_task(
            assigned_subagent=subagent,
            domain=domain,
            description=description,
            instruction=instruction,
            input_context=enriched_context,
            constraints=constraints,
            required_packet_type=required_packet_type,
            upstream_task_id=upstream_task_id,
        )

        # Audit
        self.audit.task_created(
            task_id=task["task_id"],
            subagent=subagent,
            domain=domain,
            description=description,
        )
        self.audit.state_transition(
            task_id=task["task_id"],
            from_state="(init)",
            to_state="created",
            note=f"Task created for {subagent}/{domain}",
        )

        return task

    # ── Phase 2: Subagent Invocation ──────────────────────────

    def simulate_acknowledge(self, task_id: str) -> dict:
        """
        Simulate a subagent acknowledging a task assignment.
        Advances: created -> assigned -> in_progress

        This is the LEGACY path for subagents without live workers
        or for testing without actual subprocess invocation.

        For live worker invocation, use invoke_subagent() instead.
        """
        task = self.task_store.advance_state(
            task_id, "assigned", "Subagent acknowledged assignment"
        )
        self.audit.state_transition(task_id, "created", "assigned", "Subagent acknowledged")

        task = self.task_store.advance_state(
            task_id, "in_progress", "Subagent began work"
        )
        self.audit.state_transition(task_id, "assigned", "in_progress", "Subagent began work")

        return task

    def invoke_subagent(self, task_id: str, timeout: float = 30.0) -> dict:
        """
        Invoke a live subagent worker for a task.

        This is the live worker path. It:
          1. Advances task to assigned -> in_progress
          2. Invokes the worker subprocess via SubagentAdapter
          3. If successful: calls receive_response() and validate_response()
          4. If failed/timeout: leaves task in in_progress (safe state)

        Falls back to simulate_acknowledge() if no live worker exists
        for the assigned subagent.

        Args:
            task_id: The task ID to invoke a worker for
            timeout: Maximum seconds to wait for the worker

        Returns:
            A result dict with:
              - success: bool — whether the full pipeline completed
              - task: dict — the final task state
              - validation: dict | None — validation result (if reached)
              - adapter_result: dict | None — raw adapter result (if worker was invoked)
              - routing: dict | None — routing decision (if reached)
              - error: str | None — error message if something failed
        """
        # 1. Advance to assigned -> in_progress
        task = self.task_store.advance_state(
            task_id, "assigned", "Subagent acknowledged assignment"
        )
        self.audit.state_transition(task_id, "created", "assigned", "Subagent acknowledged")

        task = self.task_store.advance_state(
            task_id, "in_progress", "Subagent began work"
        )
        self.audit.state_transition(task_id, "assigned", "in_progress", "Subagent began work")

        # 2. Check if a live worker exists for this subagent
        subagent = task.get("assigned_subagent", "")

        if not self.adapter.has_live_worker(subagent):
            # No live worker — fall back to simulated path
            return {
                "success": False,
                "task": task,
                "validation": None,
                "adapter_result": None,
                "routing": None,
                "error": f"No live worker for subagent '{subagent}'. "
                         f"Use simulate_acknowledge() + manual packet injection.",
            }

        # 3. Invoke the worker
        adapter_result = self.adapter.invoke_for_task(self, task_id, timeout=timeout)

        # 4. If worker invocation failed, task stays in in_progress (safe state)
        if not adapter_result["success"]:
            self.audit.state_transition(
                task_id, "in_progress", "in_progress",
                f"Worker invocation failed: {adapter_result.get('error', 'unknown')}",
            )
            return {
                "success": False,
                "task": task,
                "validation": None,
                "adapter_result": adapter_result,
                "routing": None,
                "error": adapter_result.get("error", "Worker invocation failed"),
            }

        # 5. Worker succeeded — receive and validate the response
        response_packet = adapter_result["response_packet"]

        # Override task_id in the response to match (defensive)
        if response_packet.get("task_id") != task_id:
            response_packet["task_id"] = task_id

        try:
            task = self.receive_response(task_id, response_packet)
        except ValueError as e:
            return {
                "success": False,
                "task": self.task_store.load_task(task_id),
                "validation": None,
                "adapter_result": adapter_result,
                "routing": None,
                "error": f"receive_response failed: {e}",
            }

        # 6. Validate the response
        validation = self.validate_response(task_id)

        # 7. If validation passed, route
        routing = None
        if validation.get("valid"):
            try:
                routing = self.route(task_id)
            except ValueError as e:
                return {
                    "success": False,
                    "task": self.task_store.load_task(task_id),
                    "validation": validation,
                    "adapter_result": adapter_result,
                    "routing": None,
                    "error": f"routing failed: {e}",
                }

        return {
            "success": validation.get("valid", False),
            "task": self.task_store.load_task(task_id),
            "validation": validation,
            "adapter_result": adapter_result,
            "routing": routing,
            "error": None if validation.get("valid") else f"Validation failed: {validation.get('errors', [])}",
        }

    # ── Phase 3: Response Packet Reception ──────────────────

    def receive_response(self, task_id: str, packet: dict) -> dict:
        """
        Receive a subagent response packet. Store it and advance state
        to response_received.

        The caller (or demo) is responsible for producing the packet.
        The runtime does NOT spawn subagents.
        """
        # Verify task_id in packet matches
        if packet.get("task_id") != task_id:
            raise ValueError(
                f"Packet task_id '{packet.get('task_id')}' does not match "
                f"expected task_id '{task_id}'"
            )

        # Store the response packet
        self.task_store.set_response_packet(task_id, packet)

        # Advance state
        task = self.task_store.advance_state(
            task_id, "response_received",
            f"Received {packet.get('packet_type', 'unknown')} packet from {packet.get('source', 'unknown')}"
        )
        self.audit.state_transition(
            task_id, "in_progress", "response_received",
            f"Packet type: {packet.get('packet_type')}",
        )

        return task

    # ── Phase 4: Validation ─────────────────────────────────

    def validate_response(self, task_id: str) -> dict:
        """
        Validate the stored response packet using the 6-level validator.
        Advances state to validation_passed or validation_failed.
        Records the validation result on the task.
        """
        task = self.task_store.load_task(task_id)
        packet = task.get("response_packet")
        if not packet:
            raise ValueError(f"Task {task_id} has no response_packet to validate")

        # Run the 6-level validator
        valid, errors, warnings = self.validator.validate_packet(packet)

        # Store validation result
        result = {
            "valid": valid,
            "packet_type": packet.get("packet_type", "unknown"),
            "source": packet.get("source", "unknown"),
            "task_id": task_id,
            "errors": errors,
            "warnings": warnings,
        }
        self.task_store.set_validation_result(task_id, result)
        self.audit.validation_result(task_id, valid, errors, warnings)

        # Advance state
        if valid:
            task = self.task_store.advance_state(
                task_id, "validation_passed",
                f"Packet validated successfully ({len(warnings)} warnings)"
            )
            self.audit.state_transition(
                task_id, "response_received", "validation_passed",
                f"Valid. Warnings: {len(warnings)}",
            )
        else:
            task = self.task_store.advance_state(
                task_id, "validation_failed",
                f"Packet validation failed: {len(errors)} error(s)"
            )
            self.audit.state_transition(
                task_id, "response_received", "validation_failed",
                f"Failed. Errors: {errors}",
            )

        return {**result, "state": task["state"]}

    # ── Phase 5: Routing ────────────────────────────────────

    ROUTING_TABLE = {
        ("cryer", "cryer_recon"): [
            {"target": "pyper", "condition": "yield_score >= 50 and outreach potential"},
            {"target": "knower", "condition": "deep analysis needed"},
        ],
        ("cryer", "cryer_alert"): [
            {"target": "operator", "condition": "high-severity alert needs human attention"},
        ],
        ("knower", "knower_research"): [
            {"target": "pyper", "condition": "research supports outreach"},
            {"target": "coder", "condition": "research unblocks implementation"},
        ],
        ("knower", "knower_claim_review"): [
            {"target": "operator", "condition": "claim review requires operator judgment"},
        ],
        ("knower", "knower_myth_fact"): [
            {"target": "operator", "condition": "myth/fact classification always requires operator review"},
        ],
        ("pyper", "pyper_approval"): [
            {"target": "operator", "condition": "PypER approval always requires operator"},
        ],
        ("pyper", "pyper_execution_plan"): [
            {"target": "operator", "condition": "PypER execution plans always require operator review and approval"},
        ],
        ("pyper", "pyper_execution_receipt"): [
            {"target": "operator", "condition": "PypER execution receipts always require operator review"},
        ],
        ("pyper", "pyper_execution_refusal"): [
            {"target": "operator", "condition": "PypER execution refusals always require operator review"},
        ],
        # CryER v0.4.0 packet routing
        ("cryer", "cryer_reputation_signal"): [{"target": "operator", "condition": "reputation signals require operator review"}],
        ("cryer", "cryer_engagement_signal"): [{"target": "operator", "condition": "engagement signals require operator review"}],
        ("cryer", "cryer_booking_friction"): [{"target": "operator", "condition": "booking friction requires operator review"}],
        ("cryer", "cryer_directory_completeness"): [{"target": "operator", "condition": "directory assessment requires operator review"}],
        ("cryer", "cryer_hiring_growth"): [{"target": "operator", "condition": "hiring signals require operator review"}],
    }

    def route(self, task_id: str) -> dict:
        """
        Make a routing decision for a validated task.
        Advances: validation_passed -> routed (and possibly approval_pending)

        Returns the routing decision dict.
        """
        task = self.task_store.load_task(task_id)
        if task["state"] != "validation_passed":
            raise ValueError(
                f"Cannot route task in state '{task['state']}'. "
                f"Must be 'validation_passed'."
            )

        response = task.get("response_packet") or {}
        source = response.get("source", task["assigned_subagent"])
        ptype = response.get("packet_type", "")
        domain = task.get("domain", "")

        # Determine routing target
        routing_target, reason, creates_downstream = self._determine_routing(
            source, ptype, domain, response
        )

        decision = {
            "routing_target": routing_target,
            "reason": reason,
            "creates_downstream_task": creates_downstream,
        }

        # Store routing decision
        self.task_store.set_routing_decision(task_id, decision)
        self.audit.routing_decision(task_id, routing_target, reason, creates_downstream)

        # Advance state
        if routing_target == "operator":
            # Route directly to operator
            task = self.task_store.advance_state(
                task_id, "routed",
                f"Routed to operator: {reason}"
            )
            self.audit.state_transition(
                task_id, "validation_passed", "routed",
                f"Routed to operator",
            )
        elif routing_target in ("pyper", "knower", "coder", "cryer"):
            task = self.task_store.advance_state(
                task_id, "routed",
                f"Routed to {routing_target}: {reason}"
            )
            self.audit.state_transition(
                task_id, "validation_passed", "routed",
                f"Routed to {routing_target}",
            )
        elif routing_target == "archive":
            task = self.task_store.advance_state(
                task_id, "routed",
                f"Archived: {reason}"
            )
            self.audit.state_transition(
                task_id, "validation_passed", "routed",
                "Routed to archive",
            )
        else:
            raise ValueError(f"Unknown routing target: {routing_target}")

        # Check if approval gate applies
        # For routed tasks that will produce downstream action, check approval
        gate_decision = self.gate.enforce_gate(task, "completed")
        if gate_decision["approval_required"]:
            # Must go to approval_pending
            task = self.task_store.advance_state(
                task_id, "approval_pending",
                f"Approval required: {gate_decision['reason']}"
            )
            self.audit.state_transition(
                task_id, "routed", "approval_pending",
                "Approval gate enforced",
            )

        decision["final_state"] = task["state"]
        return decision

    def _determine_routing(
        self, source: str, ptype: str, domain: str, response: dict
    ) -> tuple[str, str, bool]:
        """
        Determine routing target based on packet source and type.

        Returns: (target, reason, creates_downstream)
        """
        # PypER always routes to operator — execution plans, receipts, refusals, approvals
        if source == "pyper":
            ptype_desc = {
                "pyper_execution_plan": "execution plan",
                "pyper_execution_receipt": "execution receipt",
                "pyper_execution_refusal": "execution refusal",
                "pyper_approval": "approval",
                "pyper_revision": "revision",
                "pyper_objection_response": "objection response",
            }.get(ptype, "packet")
            reason = f"PypER {ptype_desc} always requires operator review"
            if ptype == "pyper_execution_refusal":
                reason = f"PypER execution refused — operator action required"
            return "operator", reason, False

        # Check next_steps_recommendation in the response
        nsr = response.get("next_steps_recommendation", "").lower()

        # CryER recon -> PypER if yield is promising
        if source == "cryer" and ptype == "cryer_recon":
            # Check yield scores in recon data
            targets = response.get("recon_data", {}).get("targets", [])
            if targets:
                max_yield = max(
                    t.get("signals", {}).get("reputation", {}).get("yield_score", 0)
                    for t in targets
                )
                if max_yield >= 50 or "pyper" in nsr or "outreach" in nsr:
                    return "pyper", f"CryER recon yield={max_yield}, outreach opportunity identified", True

            # Otherwise route to knower for analysis
            return "knower", "CryER recon — route for analysis", True

        # CryER alert -> operator for human attention
        if source == "cryer" and ptype == "cryer_alert":
            return "operator", "CryER alert requires operator attention", False

        # KnowER research -> PypER or CodER
        if source == "knower" and ptype == "knower_research":
            if "outreach" in nsr or "pyper" in nsr:
                return "pyper", "KnowER research supports outreach", True
            return "coder", "KnowER research unblocks implementation", True

        # KnowER assessment -> archive or operator
        if source == "knower" and ptype == "knower_assessment":
            return "operator", "KnowER assessment requires operator review", False

        # CodER completion -> archive or operator
        if source == "coder" and ptype == "coder_completion":
            return "archive", "CodER task completed", False

        # CodER blocked -> knower for research
        if source == "coder" and ptype == "coder_blocked":
            return "knower", "CodER blocked — route to KnowER for research", True

        # CodER patch_plan -> operator (advisory plan requires operator review)
        if source == "coder" and ptype == "coder_patch_plan":
            return "operator", "CodER patch plan — requires operator review before any file mutation", True

        # Default: route to operator
        return "operator", f"Default route for {source}/{ptype}", False

    # ── Phase 6: Downstream Task Creation ──────────────────

    def create_downstream_task(
        self,
        upstream_task_id: str,
        routing_target: str,
        instruction_override: str | None = None,
    ) -> dict:
        """
        Create a downstream task based on a routing decision.

        Args:
            upstream_task_id: The task whose output feeds into this new task.
            routing_target: The subagent to route to.
            instruction_override: Optional instruction override.

        Returns:
            The new task record.
        """
        upstream = self.task_store.load_task(upstream_task_id)
        upstream_response = upstream.get("response_packet") or {}

        # Map routing target to domain
        target_domains = {
            "pyper": "outreach",
            "knower": "research",
            "coder": "code",
            "cryer": "recon",
        }
        domain = target_domains.get(routing_target, "research")
        description = f"Downstream task from {upstream_task_id} — route to {routing_target}"

        # Build instruction from upstream output
        upstream_summary = upstream_response.get("summary", upstream.get("description", ""))
        instruction = instruction_override or (
            f"Based on findings from {upstream_task_id}: {upstream_summary}"
        )

        # Build input context from upstream
        input_context = {
            "upstream_task_id": upstream_task_id,
            "upstream_summary": upstream_summary,
            "upstream_subagent": upstream.get("assigned_subagent"),
            "upstream_packet_type": upstream_response.get("packet_type"),
        }

        # If CryER -> PypER, include recon highlights
        if upstream.get("assigned_subagent") == "cryer" and routing_target == "pyper":
            targets = upstream_response.get("recon_data", {}).get("targets", [])
            input_context["recon_highlights"] = [
                {
                    "entity": t.get("entity"),
                    "yield_score": t.get("signals", {}).get("reputation", {}).get("yield_score"),
                    "confidence": t.get("signals", {}).get("reputation", {}).get("confidence"),
                }
                for t in targets
            ]

        return self.create_task(
            domain=domain,
            description=description,
            instruction=instruction,
            input_context=input_context,
            upstream_task_id=upstream_task_id,
        )

    # ── Phase 7: Approval Processing ─────────────────────────

    def process_approval(
        self,
        task_id: str,
        decision: str,
        reason: str | None = None,
        operator: str = "operator",
    ) -> dict:
        """
        Process an operator approval or rejection.

        Args:
            decision: "approved" or "rejected"
            reason: Optional reason
            operator: Who made the decision

        Returns:
            Updated task record.
        """
        task = self.task_store.load_task(task_id)
        if task["state"] != "approval_pending":
            raise ValueError(
                f"Cannot process approval for task in state '{task['state']}'. "
                f"Must be 'approval_pending'."
            )

        # Process the approval
        approval = self.gate.process_approval(task, decision, reason, operator)
        self.task_store.set_operator_approval(task_id, approval)
        self.audit.approval_action(
            task_id, "approval_decision", decision, reason, operator
        )

        if decision == "approved":
            task = self.task_store.advance_state(
                task_id, "approved",
                f"Approved by {operator}" + (f": {reason}" if reason else "")
            )
            self.audit.state_transition(
                task_id, "approval_pending", "approved",
                f"Approved by {operator}",
            )

            # Check if we can complete
            routing = task.get("routing_decision") or {}
            target = routing.get("routing_target", "")
            if target in ("operator", "archive") or not routing.get("creates_downstream_task", False):
                task = self.task_store.advance_state(
                    task_id, "completed",
                    "Task completed — approved and no further routing"
                )
                self.audit.state_transition(
                    task_id, "approved", "completed",
                    "Task completed after approval",
                )
                self.audit.task_completed(task_id, "completed", task.get("description", ""))

        elif decision == "rejected":
            # Increment revision count FIRST, then check if limit reached
            task = self.task_store.increment_revision(task_id)
            revision_count = task.get("revision_count", 0)

            # Transition to rejected
            task = self.task_store.advance_state(
                task_id, "rejected",
                f"Rejected by {operator}: {reason or 'no reason given'}"
            )
            self.audit.state_transition(
                task_id, "approval_pending", "rejected",
                f"Rejected — revision {revision_count}/{self.gate.MAX_REVISION_LOOPS}",
            )
            self.audit.revision_loop(task_id, revision_count, reason or "operator rejection")

            # Check if revision limit has been reached
            if revision_count >= self.gate.MAX_REVISION_LOOPS:
                # Revision limit exceeded — abandon the task
                task = self.task_store.advance_state(
                    task_id, "abandoned",
                    f"Revision limit ({self.gate.MAX_REVISION_LOOPS}) reached after {revision_count} rejections"
                )
                self.audit.state_transition(
                    task_id, "rejected", "abandoned",
                    f"Abandoned — revision limit ({self.gate.MAX_REVISION_LOOPS}) exceeded",
                )
                self.audit.task_completed(task_id, "abandoned", task.get("description", ""))
            else:
                # Route back to assigned for revision (revision loop still within limit)
                task = self.task_store.advance_state(
                    task_id, "assigned",
                    f"Revision loop {revision_count}/{self.gate.MAX_REVISION_LOOPS}"
                )
                self.audit.state_transition(
                    task_id, "rejected", "assigned",
                    f"Back to subagent for revision",
                )

        return task

    # ── Phase 8: Operator Summary ─────────────────────────────

    def operator_summary(self, task_id: str) -> dict:
        """
        Produce an operator-facing summary packet for a task.

        Trust boundary: Governance fields (approval_required, outbound_blocked,
        execution_authority) are computed from ApprovalGate and the task's
        validated filesystem state — NEVER from the untrusted response packet.
        Packet claims are preserved in packet_claims but clearly separated.
        """
        summary = self.task_store.task_summary(task_id)
        task = self.task_store.load_task(task_id)

        # ── Compute runtime-authenticated governance ──
        approval_required = self.gate.check_approval_required(task)
        blocked, block_reason = self.gate.should_block_outbound(task)

        # Execution authority: who can authorize the next action?
        state = task["state"]
        approval = task.get("operator_approval")

        if state == "completed" and approval and approval.get("decision") == "approved":
            execution_authority = "operator_approved_completed"
        elif state == "approved":
            execution_authority = "operator_approved_pending_completion"
        elif state == "approval_pending":
            execution_authority = "operator_decision_required"
        elif state == "validation_failed":
            execution_authority = "operator_decision_required"
        elif approval_required and not blocked:
            execution_authority = "operator_approved_outbound_unblocked"
        elif blocked:
            execution_authority = "outbound_blocked_no_approval"
        else:
            execution_authority = "no_approval_gate"

        summary["governance"] = {
            "approval_required": approval_required,
            "outbound_blocked": blocked,
            "outbound_block_reason": block_reason if blocked else None,
            "execution_authority": execution_authority,
            "validation_passed": (task.get("validation_result") or {}).get("valid"),
        }

        return summary

    # ── Utility ──────────────────────────────────────────────

    def get_audit_trail(self, task_id: str | None = None, limit: int = 100) -> list[dict]:
        """Read audit entries for a task or all tasks."""
        return self.audit.read_log(task_id=task_id, limit=limit)

    def get_task(self, task_id: str) -> dict:
        """Load a task record from disk."""
        return self.task_store.load_task(task_id)

    def list_tasks(self) -> list[dict]:
        """List all task records."""
        return self.task_store.list_tasks()

    def complete_task(self, task_id: str, note: str = "Task completed") -> dict:
        """
        Mark a task as completed. The task must be in a state that
        can transition to 'completed' (approved, routed with no
        approval gate, or routed to archive).
        """
        task = self.task_store.advance_state(task_id, "completed", note)
        self.audit.state_transition(task_id, task["state"], "completed", note)
        self.audit.task_completed(task_id, "completed", task.get("description", ""))
        return task

    def abandon_task(self, task_id: str, reason: str) -> dict:
        """
        Mark a task as abandoned. Used when revision limits are exceeded
        or when the operator explicitly abandons.
        """
        task = self.task_store.advance_state(task_id, "abandoned", reason)
        self.audit.state_transition(task_id, task["state"], "abandoned", reason)
        self.audit.task_completed(task_id, "abandoned", task.get("description", ""))
        return task

    def check_outbound_block(self, task_id: str) -> tuple[bool, str]:
        """Check whether outbound action is blocked for a task."""
        task = self.task_store.load_task(task_id)
        return self.gate.should_block_outbound(task)