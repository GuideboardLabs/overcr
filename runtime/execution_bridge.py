#!/usr/bin/env python3
"""
OverCR Runtime — Execution Bridge (v0.4.1)

Wires ModelRouter routing decisions into Hermes execution.
This is the bridge between OverCR's config-driven routing layer
and the host runtime (Hermes) that executes subagent workers.

Architecture:
  OverCR (substrate)          Hermes (runtime)
  ─────────────────           ────────────────
  ModelRouter.route()         │
       ↓                       │
  ModelPolicy.validate()      │
       ↓                       │
  HermesExecutionAdapter      │
       ↓                       │
  SubagentAdapter.invoke()    │
       ↓                       ↓
  Worker subprocess       Model selection metadata
       │                  recorded in task + audit
       ↓
  Response validated,
  state advanced

What it does:
  - Accepts RoutingResult from ModelRouter
  - Validates routing against ModelPolicy governance
  - Resolves execution parameters (model, provider, timeout, fallback)
  - Delegates actual worker invocation to SubagentAdapter
  - Records execution audit fields in task records
  - Supports dry-run mode (resolve routing without invoking workers)
  - Fallback: if preferred model fails/times out, retry with fallback model
  - All routing decisions logged to audit trail

What it does NOT do:
  - No model execution (delegates to SubagentAdapter + WorkerRunner)
  - No direct Ollama/API calls (provider-agnostic)
  - No runtime replacement (Hermes remains the execution environment)
  - No autonomous execution loops
  - No outbound actions
  - No provider lock-in

Safety guarantees:
  - Routing failure never advances task state
  - Policy violation blocks execution (not just warns)
  - Timeout is enforced per-attempt (preferred + fallback)
  - Execution audit fields are always written, even on failure
  - Dry-run mode produces audit trail without consuming inference quota
"""

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from runtime.model_router import ModelRouter, RoutingResult, ModelRouterError
from runtime.model_policy import ModelPolicy, PolicyResult


@dataclass
class ExecutionAudit:
    """Audit record for a single execution attempt."""
    selected_model: str = ""
    selected_provider: str = ""
    selected_route: str = ""
    fallback_used: bool = False
    fallback_reason: Optional[str] = None
    execution_runtime: float = 0.0
    timeout_s: float = 30.0
    retry_count: int = 0
    policy_valid: bool = False
    policy_errors: List[str] = field(default_factory=list)
    policy_warnings: List[str] = field(default_factory=list)
    dry_run: bool = False
    subagent: str = ""
    task_id: str = ""
    timestamp: str = ""

    def to_dict(self) -> dict:
        return {
            "selected_model": self.selected_model,
            "selected_provider": self.selected_provider,
            "selected_route": self.selected_route,
            "fallback_used": self.fallback_used,
            "fallback_reason": self.fallback_reason,
            "execution_runtime_s": round(self.execution_runtime, 3),
            "timeout_s": self.timeout_s,
            "retry_count": self.retry_count,
            "policy_valid": self.policy_valid,
            "policy_errors": self.policy_errors,
            "policy_warnings": self.policy_warnings,
            "dry_run": self.dry_run,
            "subagent": self.subagent,
            "task_id": self.task_id,
            "timestamp": self.timestamp,
        }


class HermesExecutionAdapter:
    """
    Bridge between OverCR routing decisions and Hermes worker execution.

    This adapter:
      1. Takes a RoutingResult from ModelRouter
      2. Validates it against ModelPolicy
      3. Decorates the SubagentAdapter invocation with model selection metadata
      4. Records execution audit fields in task records
      5. Supports dry-run mode (routing resolution only, no inference)

    It does NOT:
      - Call model APIs directly
      - Spawn model processes (that happens via SubagentAdapter)
      - Replace Hermes as the runtime
      - Make outbound contact
    """

    def __init__(
        self,
        root: str,
        router: Optional[ModelRouter] = None,
        policy: Optional[ModelPolicy] = None,
    ):
        """
        Args:
            root: Path to OverCR root directory
            router: Optional ModelRouter instance (created from root if not provided)
            policy: Optional ModelPolicy instance (created from root if not provided)
        """
        self.root = Path(root)
        self.router = router or ModelRouter(str(self.root))
        self.policy = policy or ModelPolicy(str(self.root))
        self._audit_log: List[ExecutionAudit] = []

    def resolve_routing(
        self,
        task_id: str,
        domain: Optional[str] = None,
        assigned_subagent: Optional[str] = None,
        task_type: Optional[str] = None,
        request_packet: Optional[dict] = None,
    ) -> Tuple[RoutingResult, PolicyResult, ExecutionAudit]:
        """
        Resolve routing for a task without executing it.

        This is the core routing resolution: ModelRouter selects a model/provider,
        ModelPolicy validates the choice, and the result is recorded in an
        ExecutionAudit.

        This method does NOT invoke the worker — it only resolves WHAT would
        be used. Use invoke_with_routing() for full execution, or call this
        directly for dry-run mode.

        Args:
            task_id: Task identifier
            domain: Task domain
            assigned_subagent: Assigned subagent
            task_type: Task type override
            request_packet: Optional full request packet

        Returns:
            Tuple of (RoutingResult, PolicyResult, ExecutionAudit)
        """
        # Step 1: Route via ModelRouter
        routing = self.router.route(
            task_id=task_id,
            domain=domain,
            assigned_subagent=assigned_subagent,
            task_type=task_type,
            request_packet=request_packet,
        )

        # Step 2: Resolve timeout from routing config
        route_config = self.router.config.get("_routes", {}).get(routing.route_used, {})
        subagent_config = self.router.config.get("_subagents", {}).get(routing.subagent, {})
        timeout = subagent_config.get("timeout") or route_config.get("timeout", 30.0)

        # Step 3: Validate against ModelPolicy
        # Determine model class from routing
        model_class = self._resolve_model_class(routing.model, routing.route_used, routing.subagent)

        policy_result = self.policy.validate_routing(
            model=routing.model,
            route=routing.route_used,
            subagent=routing.subagent,
            model_class=model_class,
        )

        # Step 4: Build execution audit
        audit = ExecutionAudit(
            selected_model=routing.model,
            selected_provider=routing.provider,
            selected_route=routing.route_used,
            fallback_used=routing.fallback_used,
            fallback_reason=routing.fallback_reason,
            timeout_s=timeout,
            policy_valid=policy_result.valid,
            policy_errors=policy_result.errors,
            policy_warnings=policy_result.warnings,
            subagent=routing.subagent or assigned_subagent or "",
            task_id=task_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        self._audit_log.append(audit)
        return routing, policy_result, audit

    def invoke_with_routing(
        self,
        subagent_adapter,  # SubagentAdapter instance
        task_id: str,
        runtime,  # OverCRRuntime instance (for task record updates)
        domain: Optional[str] = None,
        assigned_subagent: Optional[str] = None,
        task_type: Optional[str] = None,
        request_packet: Optional[dict] = None,
        fallback_on_failure: bool = True,
    ) -> dict:
        """
        Full execution: resolve routing, validate policy, invoke worker, record audit.

        Steps:
          1. Resolve routing (model, provider, route, timeout)
          2. Validate against ModelPolicy
          3. If policy invalid, block execution and record in audit
          4. Invoke worker via SubagentAdapter with resolved timeout
          5. Record execution audit fields in task record
          6. If worker fails and fallback_on_failure, retry with fallback model
          7. Return result dict with execution metadata

        Args:
            subagent_adapter: SubagentAdapter instance for worker invocation
            task_id: Task identifier
            runtime: OverCRRuntime instance for task record updates
            domain: Task domain
            assigned_subagent: Assigned subagent
            task_type: Task type override
            request_packet: Optional full request packet
            fallback_on_failure: Whether to retry with fallback on failure

        Returns:
            Result dict with:
              - success: bool
              - response_packet: dict | None
              - routing: RoutingResult (as dict)
              - policy: PolicyResult (as dict)
              - execution_audit: ExecutionAudit (as dict)
              - adapter_result: dict (raw SubagentAdapter result)
              - fallback_attempted: bool
        """
        start_time = time.time()

        # Resolve subagent from domain if not provided
        if not assigned_subagent and domain:
            from runtime.task_store import DOMAIN_SUBAGENT_MAP
            assigned_subagent = DOMAIN_SUBAGENT_MAP.get(domain, "")

        # Step 1: Resolve routing
        routing, policy_result, audit = self.resolve_routing(
            task_id=task_id,
            domain=domain,
            assigned_subagent=assigned_subagent,
            task_type=task_type,
            request_packet=request_packet,
        )

        # Step 2: Check policy validity
        if not policy_result.valid:
            audit.execution_runtime = time.time() - start_time
            audit.retry_count = 0
            return {
                "success": False,
                "response_packet": None,
                "routing": routing.to_dict(),
                "policy": policy_result.to_dict(),
                "execution_audit": audit.to_dict(),
                "adapter_result": None,
                "fallback_attempted": False,
                "error": f"Policy validation failed: {'; '.join(policy_result.errors)}",
            }

        # Step 3: Load task for request packet
        if request_packet is None:
            try:
                task = runtime.get_task(task_id)
                request_packet = task.get("request_packet", {})
            except Exception:
                request_packet = {}

        # Step 4: Invoke worker with resolved timeout
        adapter_result = subagent_adapter.invoke(
            subagent=assigned_subagent or "",
            request_packet=request_packet,
            task_id=task_id,
            timeout=audit.timeout_s,
        )

        fallback_attempted = False

        # Step 5: If worker failed and fallback enabled, retry
        if not adapter_result.get("success", False) and fallback_on_failure and not routing.fallback_used:
            # Try with fallback model
            fallback_routing = self._get_fallback_routing(
                task_id, domain, assigned_subagent, task_type, request_packet,
            )
            if fallback_routing:
                audit.fallback_used = True
                audit.fallback_reason = (
                    f"Preferred model failed: {adapter_result.get('error', 'unknown')}. "
                    f"Retrying with fallback: {fallback_routing.model}"
                )
                audit.selected_model = fallback_routing.model
                audit.selected_provider = fallback_routing.provider
                fallback_attempted = True
                audit.retry_count = 1

                # Retry with fallback timeout
                fallback_route_config = self.router.config.get(
                    "_routes", {}
                ).get(fallback_routing.route_used, {})
                fallback_timeout = fallback_route_config.get("timeout", 30.0)

                adapter_result = subagent_adapter.invoke(
                    subagent=assigned_subagent or "",
                    request_packet=request_packet,
                    task_id=task_id,
                    timeout=fallback_timeout,
                )

        # Step 6: Record execution audit in task
        audit.execution_runtime = time.time() - start_time
        self._record_execution_audit(runtime, task_id, audit)

        # Step 7: Build result
        result = {
            "success": adapter_result.get("success", False),
            "response_packet": adapter_result.get("response_packet"),
            "routing": routing.to_dict(),
            "policy": policy_result.to_dict(),
            "execution_audit": audit.to_dict(),
            "adapter_result": adapter_result,
            "fallback_attempted": fallback_attempted,
        }

        if not adapter_result.get("success", False) and not result.get("error"):
            result["error"] = adapter_result.get(
                "error", "Worker execution failed with no specific error"
            )

        return result

    def dry_run(
        self,
        task_id: str,
        domain: Optional[str] = None,
        assigned_subagent: Optional[str] = None,
        task_type: Optional[str] = None,
        request_packet: Optional[dict] = None,
    ) -> dict:
        """
        Dry-run mode: resolve routing and validate policy without invoking workers.

        This produces a full execution audit with model selection metadata
        but does NOT execute any worker or consume provider quota.

        Args:
            task_id: Task identifier
            domain: Task domain
            assigned_subagent: Assigned subagent
            task_type: Task type override
            request_packet: Optional full request packet

        Returns:
            Dict with:
              - dry_run: True
              - routing: RoutingResult (as dict)
              - policy: PolicyResult (as dict)
              - execution_audit: ExecutionAudit (as dict)
              - model_selected: str
              - provider: str
              - route: str
              - fallback_model: str (if available from config)
              - timeout_s: float
        """
        routing, policy_result, audit = self.resolve_routing(
            task_id=task_id,
            domain=domain,
            assigned_subagent=assigned_subagent,
            task_type=task_type,
            request_packet=request_packet,
        )

        audit.dry_run = True

        # Get fallback model from config
        route_config = self.router.config.get("_routes", {}).get(routing.route_used, {})
        subagent_config = self.router.config.get("_subagents", {}).get(routing.subagent, {})
        fallback_model = (
            subagent_config.get("fallback_model")
            or route_config.get("fallback_model", "")
        )

        return {
            "dry_run": True,
            "routing": routing.to_dict(),
            "policy": policy_result.to_dict(),
            "execution_audit": audit.to_dict(),
            "model_selected": routing.model,
            "provider": routing.provider,
            "route": routing.route_used,
            "fallback_model": fallback_model,
            "timeout_s": audit.timeout_s,
            "fallback_used": routing.fallback_used,
        }

    def _get_fallback_routing(
        self,
        task_id: str,
        domain: Optional[str],
        assigned_subagent: Optional[str],
        task_type: Optional[str],
        request_packet: Optional[dict],
    ) -> Optional[RoutingResult]:
        """Attempt to get a fallback routing decision."""
        try:
            result = self.router.route(
                task_id=task_id,
                domain=domain,
                assigned_subagent=assigned_subagent,
                task_type=task_type,
                request_packet=request_packet,
            )
            # Only return if it's actually a fallback
            if result.fallback_used:
                return result
            # Force fallback by using the fallback model directly
            route_config = self.router.config.get("_routes", {}).get(result.route_used, {})
            subagent_config = self.router.config.get("_subagents", {}).get(result.subagent, {})
            fallback_model = (
                subagent_config.get("fallback_model")
                or route_config.get("fallback_model")
            )
            if fallback_model and fallback_model != result.model:
                return RoutingResult(
                    model=fallback_model,
                    provider=subagent_config.get("provider") or route_config.get("provider", "ollama-cloud"),
                    route_used=result.route_used,
                    fallback_used=True,
                    fallback_reason="Fallback after preferred model failure",
                    task_id=task_id,
                    subagent=result.subagent,
                )
            return None
        except ModelRouterError:
            return None

    def _resolve_model_class(
        self,
        model: str,
        route: str,
        subagent: Optional[str],
    ) -> str:
        """Determine the model class for a given model/route/subagent combination."""
        # Check subagent policy first
        if subagent:
            subagent_config = self.policy.policy.get("_subagents", {}).get(subagent, {})
            pref_class = subagent_config.get("preferred_model_class")
            if pref_class:
                return pref_class

        # Check route policy
        route_config = self.policy.policy.get("_routes", {}).get(route, {})
        pref_class = route_config.get("preferred_model_class")
        if pref_class:
            return pref_class

        # Default based on route
        route_classes = {
            "overcr_hq": "expert",
            "code": "advanced",
            "research": "advanced",
            "diagnostics": "advanced",
            "analysis": "advanced",
            "outreach": "advanced",
            "recon": "advanced",
            "local_boot": "basic",
            "default": "standard",
        }
        return route_classes.get(route, "standard")

    def _record_execution_audit(
        self,
        runtime,  # OverCRRuntime instance
        task_id: str,
        audit: ExecutionAudit,
    ):
        """
        Record execution audit fields on the task record.

        This writes model selection metadata into the task JSON without
        advancing the task state. The audit data is appended to the task's
        execution_log array (or created if missing).
        """
        try:
            task = runtime.task_store.load_task(task_id)
        except FileNotFoundError:
            return

        # Create or append to execution_log
        execution_log = task.get("execution_log", [])
        execution_log.append(audit.to_dict())

        # Also set top-level execution fields for easy access
        task["execution_log"] = execution_log
        task["selected_model"] = audit.selected_model
        task["selected_provider"] = audit.selected_provider
        task["selected_route"] = audit.selected_route
        task["fallback_used"] = audit.fallback_used
        task["execution_runtime"] = audit.execution_runtime
        task["timeout_s"] = audit.timeout_s
        task["retry_count"] = audit.retry_count

        runtime.task_store._write_task(task)

    def get_audit_log(self) -> List[dict]:
        """Return all execution audit entries as dicts."""
        return [a.to_dict() for a in self._audit_log]

    def reset(self):
        """Reset internal audit log (for testing)."""
        self._audit_log = []