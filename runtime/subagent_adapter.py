"""
OverCR Runtime — Subagent Adapter (v0.4.1)

Bridges OverCRRuntime with live subagent worker processes.
The adapter is the interface layer: it takes a task's request packet,
invokes the correct worker via WorkerRunner, captures the result,
and feeds it back into OverCRRuntime for validation and routing.

v0.4.1 additions:
  - Model/provider metadata can be injected into request packets from routing
  - CryER added as live worker with 6 domains
  - invoke() now accepts optional model_metadata dict for execution audit

Safety guarantees:
  - Worker output is NEVER trusted — always validated before state advancement
  - Failed worker output does NOT advance task state
  - Timeout leaves task in a safe failed/revision state
  - Stdout/stderr are captured as audit-safe summaries, never blindly trusted
  - Worker cannot modify OverCR doctrine (input is read-only request packet)
  - No outbound contact, no shell execution beyond invoking the worker process
  - No database dependency
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from runtime.worker_runner import WorkerRunner, WorkerResult


class SubagentAdapter:
    """
    Interface between OverCRRuntime and subagent workers.

    Responsibilities:
      1. Resolve a subagent name to a worker entry point
      2. Invoke the worker with the task's request packet as input
      3. Capture the worker result (response packet, stdout, stderr, exit code)
      4. Return a structured result that the runtime can validate and route

    The adapter does NOT:
      - Validate packets (that's the runtime's job)
      - Advance task state (that's the runtime's job)
      - Make routing decisions (that's the runtime's job)
      - Trust worker output (validation is always enforced)
    """

    # Mapping of subagent name to worker module path (relative to OverCR root)
    WORKER_REGISTRY = {
        "coder": "subagents/coder/worker.py",
        "knower": "subagents/knower/worker.py",
        "cryer": "subagents/cryer/worker.py",
        "pyper": "subagents/pyper/worker.py",
    }

    # Domains that map to subagents with live workers
    LIVE_WORKER_DOMAINS = {
        "code": "coder",
        "diagnostics": "coder",
        "patch_plan": "coder",
        "research": "knower",
        "analysis": "knower",
        "claim_review": "knower",
        "myth_fact": "knower",
        "recon": "cryer",
        "reputation_signal": "cryer",
        "engagement_signal": "cryer",
        "booking_friction": "cryer",
        "directory_completeness": "cryer",
        "hiring_growth": "cryer",
        "execution_plan": "pyper",
    }

    def __init__(self, root: str):
        """
        Args:
            root: Path to the OverCR root directory (contains runtime/,
                  subagents/, orchestration/).
        """
        self.root = Path(root)
        self.runner = WorkerRunner()

    def resolve_worker(self, subagent: str) -> Optional[Path]:
        """
        Resolve a subagent name to its worker script path.

        Returns None if no live worker exists for this subagent
        (the subagent still uses simulated responses).
        """
        relative = self.WORKER_REGISTRY.get(subagent)
        if relative is None:
            return None
        worker_path = self.root / relative
        if worker_path.exists():
            return worker_path
        return None

    def has_live_worker(self, subagent: str) -> bool:
        """Check whether a subagent has a live worker available."""
        return self.resolve_worker(subagent) is not None

    def has_live_worker_for_domain(self, domain: str) -> bool:
        """Check whether a domain maps to a subagent with a live worker."""
        subagent = self.LIVE_WORKER_DOMAINS.get(domain)
        if subagent is None:
            return False
        return self.has_live_worker(subagent)

    def invoke(
        self,
        subagent: str,
        request_packet: dict,
        task_id: str,
        timeout: float = 30.0,
        model_metadata: Optional[dict] = None,
    ) -> dict:
        """
        Invoke a subagent worker with a request packet.

        Args:
            subagent: Subagent name (e.g., "coder")
            request_packet: The task request packet dict
            task_id: The task ID (for audit trail)
            timeout: Maximum seconds to wait for the worker
            model_metadata: Optional dict with model routing info
                (selected_model, selected_provider, selected_route, etc.)
                Injected into the request packet's _routing_metadata field
                for audit purposes. Workers MUST ignore this field.

        Returns:
            A result dict with:
              - success: bool — whether the worker produced a parseable response
              - response_packet: dict | None — the parsed response packet (None on failure)
              - exit_code: int — worker process exit code
              - timed_out: bool — whether the worker timed out
              - stdout_summary: str — audit-safe summary of stdout (truncated)
              - stderr_summary: str — audit-safe summary of stderr (truncated)
              - error: str | None — error message if invocation failed
              - worker_path: str — the worker script path invoked
        """
        worker_path = self.resolve_worker(subagent)
        if worker_path is None:
            return {
                "success": False,
                "response_packet": None,
                "exit_code": -1,
                "timed_out": False,
                "stdout_summary": "",
                "stderr_summary": "",
                "error": f"No live worker for subagent '{subagent}'",
                "worker_path": "",
            }

        # Inject routing metadata into request packet (workers ignore this)
        augmented_packet = dict(request_packet)
        if model_metadata:
            augmented_packet["_routing_metadata"] = model_metadata

        # Run the worker
        result: WorkerResult = self.runner.run(
            worker_script=worker_path,
            input_packet=augmented_packet,
            timeout=timeout,
            task_id=task_id,
        )

        # Build the adapter result
        adapter_result = {
            "success": False,
            "response_packet": None,
            "exit_code": result.exit_code,
            "timed_out": result.timed_out,
            "stdout_summary": result.stdout_summary,
            "stderr_summary": result.stderr_summary,
            "error": None,
            "worker_path": str(worker_path),
        }

        if result.timed_out:
            adapter_result["error"] = (
                f"Worker timed out after {timeout}s"
            )
            return adapter_result

        if result.exit_code != 0:
            adapter_result["error"] = (
                f"Worker exited with code {result.exit_code}. "
                f"stderr: {result.stderr_summary}"
            )
            return adapter_result

        # Try to parse the output as a response packet
        if not result.stdout_raw.strip():
            adapter_result["error"] = "Worker produced no output"
            return adapter_result

        try:
            packet = json.loads(result.stdout_raw)
        except json.JSONDecodeError as e:
            adapter_result["error"] = (
                f"Worker output is not valid JSON: {e}. "
                f"First 200 chars: {result.stdout_raw[:200]}"
            )
            return adapter_result

        if not isinstance(packet, dict):
            adapter_result["error"] = (
                f"Worker output is not a JSON object: {type(packet).__name__}"
            )
            return adapter_result

        # Worker produced a parseable response packet
        adapter_result["success"] = True
        adapter_result["response_packet"] = packet
        return adapter_result

    def invoke_for_task(
        self,
        runtime,  # OverCRRuntime instance
        task_id: str,
        timeout: float = 30.0,
        model_metadata: Optional[dict] = None,
    ) -> dict:
        """
        High-level: invoke the worker for an existing task.

        This method:
          1. Loads the task from the runtime
          2. Resolves the subagent and worker
          3. Invokes the worker with the task's request_packet
          4. Returns the adapter result (does NOT advance state)

        The caller is responsible for:
          - Calling runtime.receive_response() if the worker succeeded
          - Calling runtime.validate_response() to validate the packet
          - Handling timeout/failure cases (leaving task in a safe state)

        Args:
            runtime: OverCRRuntime instance
            task_id: The task to invoke a worker for
            timeout: Maximum seconds to wait
            model_metadata: Optional model routing metadata to inject

        Returns:
            Adapter result dict (same as invoke())
        """
        task = runtime.get_task(task_id)
        subagent = task.get("assigned_subagent", "")
        request_packet = task.get("request_packet", {})

        return self.invoke(
            subagent=subagent,
            request_packet=request_packet,
            task_id=task_id,
            timeout=timeout,
            model_metadata=model_metadata,
        )