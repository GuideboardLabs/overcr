"""
OverCR v2.8.0 — Branch Trace

Records every branch decision in a composite workflow. Every
conditional edge evaluation, routing choice, retry attempt,
escalation event, and fallback activation is captured.

Branch traces are append-only and replayable. They form the
audit backbone for composite workflow execution — proving
exactly why each path was taken.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


@dataclass
class BranchEntry:
    """A single branch decision record."""
    entry_id: str
    entry_type: str  # conditional_branch | retry | escalation | fallback | routing | subworkflow_call
    source_node_id: str = ""
    target_node_id: str = ""
    condition: Optional[dict] = None
    decision_metadata: dict = field(default_factory=dict)
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    parent_run_id: str = ""
    child_run_id: str = ""

    def to_dict(self) -> dict:
        d = {
            "entry_id": self.entry_id,
            "entry_type": self.entry_type,
            "timestamp": self.timestamp,
            "decision_metadata": self.decision_metadata,
        }
        if self.source_node_id:
            d["source_node_id"] = self.source_node_id
        if self.target_node_id:
            d["target_node_id"] = self.target_node_id
        if self.condition:
            d["condition"] = self.condition
        if self.parent_run_id:
            d["parent_run_id"] = self.parent_run_id
        if self.child_run_id:
            d["child_run_id"] = self.child_run_id
        return d


class BranchTrace:
    """
    Append-only branch decision trace for composite workflows.

    Every conditional branch, retry, escalation, fallback, and
    subworkflow call is recorded. Traces are serializable and
    replayable — given the same initial state and conditions,
    the same branch decisions will be produced.
    """

    def __init__(self, run_id: str = ""):
        self.run_id = run_id
        self._entries: list[BranchEntry] = []
        self._counter = 0

    def record_conditional_branch(
        self,
        source_node_id: str,
        target_node_id: str,
        condition: dict,
        metadata: Optional[dict] = None,
    ) -> BranchEntry:
        """Record a conditional branch decision."""
        return self._add(
            entry_type="conditional_branch",
            source_node_id=source_node_id,
            target_node_id=target_node_id,
            condition=condition,
            decision_metadata=metadata or {},
        )

    def record_retry(
        self,
        source_node_id: str,
        attempt_number: int,
        reason: str = "",
        metadata: Optional[dict] = None,
    ) -> BranchEntry:
        """Record a retry event."""
        return self._add(
            entry_type="retry",
            source_node_id=source_node_id,
            target_node_id=source_node_id,  # Retry loops back to same node
            decision_metadata={
                "attempt_number": attempt_number,
                "reason": reason,
                **(metadata or {}),
            },
        )

    def record_escalation(
        self,
        source_node_id: str,
        target: str,
        reason: str = "",
        severity: str = "medium",
        metadata: Optional[dict] = None,
    ) -> BranchEntry:
        """Record an escalation event."""
        return self._add(
            entry_type="escalation",
            source_node_id=source_node_id,
            target_node_id=target,
            decision_metadata={
                "reason": reason,
                "severity": severity,
                **(metadata or {}),
            },
        )

    def record_fallback(
        self,
        source_node_id: str,
        target_node_id: str,
        reason: str = "",
        metadata: Optional[dict] = None,
    ) -> BranchEntry:
        """Record a fallback activation."""
        return self._add(
            entry_type="fallback",
            source_node_id=source_node_id,
            target_node_id=target_node_id,
            decision_metadata={
                "reason": reason,
                **(metadata or {}),
            },
        )

    def record_routing(
        self,
        source_node_id: str,
        target_node_id: str,
        decision_type: str,
        metadata: Optional[dict] = None,
    ) -> BranchEntry:
        """Record a static routing decision."""
        return self._add(
            entry_type="routing",
            source_node_id=source_node_id,
            target_node_id=target_node_id,
            decision_metadata={
                "decision_type": decision_type,
                **(metadata or {}),
            },
        )

    def record_subworkflow_call(
        self,
        source_node_id: str,
        subworkflow_ref_id: str,
        child_run_id: str = "",
        metadata: Optional[dict] = None,
    ) -> BranchEntry:
        """Record a subworkflow invocation."""
        return self._add(
            entry_type="subworkflow_call",
            source_node_id=source_node_id,
            target_node_id=subworkflow_ref_id,
            child_run_id=child_run_id,
            decision_metadata=metadata or {},
        )

    def _add(self, **kwargs) -> BranchEntry:
        self._counter += 1
        entry = BranchEntry(
            entry_id=f"branch-{self._counter:04d}",
            parent_run_id=self.run_id,
            **kwargs,
        )
        self._entries.append(entry)
        return entry

    def get_entries(self) -> list[BranchEntry]:
        return list(self._entries)

    def export(self) -> list[dict]:
        return [e.to_dict() for e in self._entries]

    def filter_by_type(self, entry_type: str) -> list[BranchEntry]:
        return [e for e in self._entries if e.entry_type == entry_type]

    def filter_by_node(self, node_id: str) -> list[BranchEntry]:
        return [e for e in self._entries
                if e.source_node_id == node_id or e.target_node_id == node_id]

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "entry_count": len(self._entries),
            "entries": self.export(),
        }

    def replay_path(self) -> list[str]:
        """
        Replay the path taken through the workflow.

        Returns an ordered list of node_ids visited, including
        retries and escalation targets.
        """
        path = []
        for e in self._entries:
            if e.source_node_id and e.source_node_id not in path:
                path.append(e.source_node_id)
            if e.target_node_id and e.target_node_id not in path:
                path.append(e.target_node_id)
        return path
