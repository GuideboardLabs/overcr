"""
OverCR Runtime — Worker Runner (v0.2.0)

Executes subagent workers as local subprocesses with:
  - Strict timeout enforcement
  - Stdout/stderr capture with audit-safe summaries
  - Input packet delivery via stdin (JSON)
  - Response packet capture from stdout (JSON)
  - No shell command execution beyond invoking the worker process
  - No outbound network access enforcement (worker policy, not sandbox)

Worker contract:
  - Worker receives: JSON request packet on stdin
  - Worker produces: JSON response packet on stdout
  - Worker writes nothing to disk (stateless, no side effects)
  - Worker exit code: 0 = success, nonzero = failure
  - Worker must complete within timeout or be killed

Safety:
  - Worker output is NEVER trusted — validated by the runtime after capture
  - Stdout is treated as the response packet only if exit code == 0
  - Stderr is captured for diagnostics but never parsed as packet data
  - Timeout kills the subprocess (SIGKILL on POSIX, TerminateProcess on Windows)
  - Worker cannot modify OverCR doctrine (it receives a read-only input dict)
  - Failed/timed-out workers leave the task in a safe state (handled by the caller)
"""

import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# Maximum lengths for audit-safe summaries
MAX_STDOUT_SUMMARY = 2000
MAX_STDERR_SUMMARY = 1000


@dataclass
class WorkerResult:
    """Result of a worker subprocess execution."""

    exit_code: int = -1
    timed_out: bool = False
    stdout_raw: str = ""
    stderr_raw: str = ""
    stdout_summary: str = ""
    stderr_summary: str = ""
    elapsed_seconds: float = 0.0
    error: Optional[str] = None


def _truncate_for_audit(text: str, max_len: int, label: str = "output") -> str:
    """
    Produce an audit-safe summary of worker output.

    - Truncates to max_len characters
    - Replaces newlines with spaces for single-line audit entries
    - Strips control characters
    - Marks truncation with "[...truncated, N chars total]"
    """
    # Strip control characters (keep printable + common whitespace)
    cleaned = "".join(
        ch if ch.isprintable() or ch in ("\n", "\r", "\t") else f"\\x{ord(ch):02x}"
        for ch in text
    )
    # Collapse whitespace for audit readability
    collapsed = " ".join(cleaned.split())

    if len(collapsed) <= max_len:
        return collapsed

    original_len = len(text)
    truncated = collapsed[:max_len]
    return f"{truncated}[...truncated, {original_len} chars total]"


class WorkerRunner:
    """
    Executes subagent workers as local subprocesses.

    The runner:
      1. Writes the request packet to the worker's stdin as JSON
      2. Runs the worker script with `python3 <path>`
      3. Waits up to timeout seconds
      4. Captures stdout and stderr
      5. Produces audit-safe summaries (truncated, control-char stripped)
      6. Returns a WorkerResult with the raw and summarized outputs

    The runner does NOT:
      - Parse the response packet (that's SubagentAdapter's job)
      - Validate the packet (that's the runtime's job)
      - Advance task state (that's the runtime's job)
      - Execute arbitrary shell commands
      - Modify the filesystem beyond what subprocess.run does
    """

    def run(
        self,
        worker_script: Path,
        input_packet: dict,
        timeout: float = 30.0,
        task_id: str = "",
    ) -> WorkerResult:
        """
        Run a worker script with a request packet as stdin.

        Args:
            worker_script: Absolute path to the worker Python script
            input_packet: Request packet dict (will be JSON-serialized to stdin)
            timeout: Maximum seconds to wait for the worker
            task_id: Task ID for diagnostics (not passed to worker)

        Returns:
            WorkerResult with exit code, captured output, and summaries
        """
        result = WorkerResult()
        result.timed_out = False

        if not worker_script.exists():
            result.exit_code = -1
            result.error = f"Worker script not found: {worker_script}"
            return result

        # Serialize input packet
        input_json = json.dumps(input_packet, indent=2)

        # Execute the worker as a subprocess
        try:
            proc_result = subprocess.run(
                [sys.executable, str(worker_script)],
                input=input_json,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            result.exit_code = proc_result.returncode
            result.stdout_raw = proc_result.stdout
            result.stderr_raw = proc_result.stderr
            result.timed_out = False

        except subprocess.TimeoutExpired as e:
            result.exit_code = -1
            result.timed_out = True
            result.stdout_raw = e.stdout or ""
            result.stderr_raw = e.stderr or ""
            result.error = (
                f"Worker timed out after {timeout}s "
                f"(task_id={task_id})"
            )
        except Exception as e:
            result.exit_code = -1
            result.error = (
                f"Worker execution failed: {type(e).__name__}: {e} "
                f"(task_id={task_id})"
            )

        # Produce audit-safe summaries
        result.stdout_summary = _truncate_for_audit(
            result.stdout_raw, MAX_STDOUT_SUMMARY, "stdout"
        )
        result.stderr_summary = _truncate_for_audit(
            result.stderr_raw, MAX_STDERR_SUMMARY, "stderr"
        )

        return result