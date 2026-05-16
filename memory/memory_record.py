"""
OverCR Semantic Memory — Memory Record v2.1.0

A validated data model for a single semantic memory record.

Key invariant: memory records are ADVISORY. They inform operational decisions
but do NOT override canonical filesystem state. The provenance field is
mandatory and non-auto-filled — every memory must declare its origin.
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Valid lifecycle statuses
VALID_STATUSES = {"active", "stale", "rejected", "superseded"}

# Valid provenance types
VALID_PROVENANCE_TYPES = {
    "operator_direct",
    "promotion_rule",
    "subagent_output",
    "filesystem_artifact",
}

# Valid contradiction types
VALID_CONTRADICTION_TYPES = {
    "factual_contradiction",
    "temporal_contradiction",
    "scope_overlap",
}

# ID pattern
MEMORY_ID_PATTERN = re.compile(r"^mem-[a-z0-9]{8}$")


class MemoryRecord:
    """
    A single semantic memory record.

    Construction:
        - Use MemoryRecord.create() for new records (generates ID, timestamps)
        - Use MemoryRecord.from_dict() to reconstruct from stored JSON
        - Direct __init__ is for internal use only

    Immutability:
        - memory_id and created_at are immutable after creation
        - Status transitions follow a state machine
        - All mutations go through update_status() or supersede()
    """

    # Status state machine — defines valid transitions
    STATUS_TRANSITIONS = {
        "active":     {"stale", "rejected", "superseded"},
        "stale":      {"active", "rejected", "superseded"},
        "rejected":   set(),  # terminal — rejected memories never change
        "superseded": set(),  # terminal — superseded memories never change
    }

    def __init__(self, data: dict):
        """
        Internal constructor. Use create() or from_dict() instead.
        """
        self._data = data

    # ── Factory Methods ──────────────────────────────────────

    @classmethod
    def create(
        cls,
        source: str,
        provenance_type: str,
        provenance_rule: str,
        confidence: float,
        tags: list[str],
        project_scope: str,
        semantic_summary: str,
        operator_id: Optional[str] = None,
        task_id: Optional[str] = None,
        artifact_path: Optional[str] = None,
        supporting_artifacts: Optional[list[dict]] = None,
        canonical_state_refs: Optional[list[dict]] = None,
    ) -> "MemoryRecord":
        """
        Create a new memory record with validated fields.

        Args:
            source: Origin of this memory (operator name, subagent, rule ID).
            provenance_type: One of VALID_PROVENANCE_TYPES.
            provenance_rule: Identifier of the rule or method that created this.
            confidence: 0.0–1.0 confidence score.
            tags: At least one searchable tag.
            project_scope: Project/domain this memory belongs to.
            semantic_summary: Human-readable summary (1–4096 chars).
            operator_id: Optional operator who created/approved.
            task_id: Optional OverCR task that produced this memory.
            artifact_path: Optional filesystem path to source artifact.
            supporting_artifacts: Optional list of {path, description} dicts.
            canonical_state_refs: Optional list of {path, field, as_of} dicts.

        Returns:
            A new MemoryRecord with auto-generated ID and timestamps.
        """
        now = datetime.now(timezone.utc).isoformat()

        # Generate ID
        memory_id = cls._generate_id()

        # Validate inputs
        cls._validate_source(source)
        cls._validate_confidence(confidence)
        cls._validate_tags(tags)
        provenance_type = cls._validate_provenance_type(provenance_type)

        provenance = {
            "type": provenance_type,
            "rule": provenance_rule,
            "operator_id": operator_id,
            "task_id": task_id,
            "artifact_path": artifact_path,
        }

        data = {
            "memory_id": memory_id,
            "source": source,
            "created_at": now,
            "updated_at": now,
            "confidence": confidence,
            "provenance": provenance,
            "tags": list(tags),
            "project_scope": project_scope,
            "semantic_summary": semantic_summary,
            "supporting_artifacts": supporting_artifacts or [],
            "canonical_state_refs": canonical_state_refs or [],
            "contradiction_refs": [],
            "status": "active",
            "superseded_by": None,
            "stale_reason": None,
        }

        # Validate against schema rules
        cls._validate_data(data)
        return cls(data)

    @classmethod
    def from_dict(cls, data: dict) -> "MemoryRecord":
        """
        Reconstruct a MemoryRecord from a stored JSON dict.
        Validates all fields before construction.
        """
        cls._validate_data(data)
        return cls(data)

    # ── Properties ────────────────────────────────────────────

    @property
    def memory_id(self) -> str:
        return self._data["memory_id"]

    @property
    def source(self) -> str:
        return self._data["source"]

    @property
    def created_at(self) -> str:
        return self._data["created_at"]

    @property
    def updated_at(self) -> str:
        return self._data["updated_at"]

    @property
    def confidence(self) -> float:
        return self._data["confidence"]

    @property
    def provenance(self) -> dict:
        return self._data["provenance"]

    @property
    def tags(self) -> list[str]:
        return self._data["tags"]

    @property
    def project_scope(self) -> str:
        return self._data["project_scope"]

    @property
    def semantic_summary(self) -> str:
        return self._data["semantic_summary"]

    @property
    def supporting_artifacts(self) -> list[dict]:
        return self._data.get("supporting_artifacts", [])

    @property
    def canonical_state_refs(self) -> list[dict]:
        return self._data.get("canonical_state_refs", [])

    @property
    def contradiction_refs(self) -> list[dict]:
        return self._data.get("contradiction_refs", [])

    @property
    def status(self) -> str:
        return self._data["status"]

    @property
    def superseded_by(self) -> Optional[str]:
        return self._data.get("superseded_by")

    @property
    def stale_reason(self) -> Optional[str]:
        return self._data.get("stale_reason")

    # ── State Transitions ─────────────────────────────────────

    def update_status(self, new_status: str, reason: Optional[str] = None) -> "MemoryRecord":
        """
        Transition this memory to a new status.

        Valid transitions:
            active  -> stale | rejected | superseded
            stale   -> active | rejected | superseded

        Rejected and superseded are terminal states.

        Args:
            new_status: Target status from VALID_STATUSES.
            reason: Optional reason string (required for stale).

        Returns:
            Self (mutated in-place and ready for persistence).

        Raises:
            ValueError: If the transition is invalid.
        """
        if new_status not in VALID_STATUSES:
            raise ValueError(f"Invalid status: {new_status}. Valid: {VALID_STATUSES}")

        current = self._data["status"]
        allowed = self.STATUS_TRANSITIONS.get(current, set())

        if new_status not in allowed:
            raise ValueError(
                f"Invalid transition: {current} -> {new_status}. "
                f"Allowed from '{current}': {allowed}"
            )

        self._data["status"] = new_status
        self._data["updated_at"] = datetime.now(timezone.utc).isoformat()

        if new_status == "stale" and reason:
            self._data["stale_reason"] = reason
        elif new_status != "stale":
            self._data["stale_reason"] = None

        return self

    def supersede(self, replacement_id: str, reason: Optional[str] = None) -> "MemoryRecord":
        """
        Mark this memory as superseded by a newer memory.

        Args:
            replacement_id: The memory_id of the replacing record.
            reason: Optional explanation.

        Returns:
            Self (mutated in-place).

        Raises:
            ValueError: If this memory is not in 'active' or 'stale' status.
        """
        if not MEMORY_ID_PATTERN.match(replacement_id):
            raise ValueError(f"Invalid replacement memory_id: {replacement_id}")

        current = self._data["status"]
        if current not in ("active", "stale"):
            raise ValueError(f"Cannot supersede memory in '{current}' status.")

        self._data["status"] = "superseded"
        self._data["superseded_by"] = replacement_id
        self._data["updated_at"] = datetime.now(timezone.utc).isoformat()
        if reason:
            self._data["stale_reason"] = reason

        return self

    def add_contradiction(self, conflicting_id: str, conflict_type: str,
                          note: Optional[str] = None) -> "MemoryRecord":
        """
        Record a contradiction with another memory.

        Args:
            conflicting_id: The memory_id of the conflicting record.
            conflict_type: One of VALID_CONTRADICTION_TYPES.
            note: Optional human-readable explanation.

        Returns:
            Self (mutated in-place).
        """
        if not MEMORY_ID_PATTERN.match(conflicting_id):
            raise ValueError(f"Invalid conflicting memory_id: {conflicting_id}")
        if conflict_type not in VALID_CONTRADICTION_TYPES:
            raise ValueError(f"Invalid conflict_type: {conflict_type}")

        entry = {
            "conflicting_memory_id": conflicting_id,
            "conflict_type": conflict_type,
            "detected_at": datetime.now(timezone.utc).isoformat(),
            "note": note,
        }
        self._data.setdefault("contradiction_refs", []).append(entry)
        self._data["updated_at"] = datetime.now(timezone.utc).isoformat()
        return self

    # ── Serialization ─────────────────────────────────────────

    def to_dict(self) -> dict:
        """Return a deep copy of the internal data dict."""
        return json.loads(json.dumps(self._data))

    def to_json(self, indent: int = 2) -> str:
        """Serialize to a JSON string."""
        return json.dumps(self._data, indent=indent, ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str: str) -> "MemoryRecord":
        """Deserialize from a JSON string."""
        return cls.from_dict(json.loads(json_str))

    # ── Validation ─────────────────────────────────────────────

    @staticmethod
    def _generate_id() -> str:
        """Generate a memory ID: mem- + 8 hex chars."""
        import secrets
        return f"mem-{secrets.token_hex(4)}"

    @staticmethod
    def _validate_source(source: str):
        if not source or len(source) > 512:
            raise ValueError(f"Source must be 1–512 chars, got {len(source)}")

    @staticmethod
    def _validate_confidence(confidence: float):
        if not (0.0 <= confidence <= 1.0):
            raise ValueError(f"Confidence must be 0.0–1.0, got {confidence}")

    @staticmethod
    def _validate_tags(tags: list[str]):
        if not tags:
            raise ValueError("At least one tag is required")
        for t in tags:
            if not t or len(t) > 64:
                raise ValueError(f"Tags must be 1–64 chars, got '{t}'")

    @staticmethod
    def _validate_provenance_type(ptype: str) -> str:
        if ptype not in VALID_PROVENANCE_TYPES:
            raise ValueError(f"Invalid provenance type: {ptype}. Valid: {VALID_PROVENANCE_TYPES}")
        return ptype

    @staticmethod
    def _validate_data(data: dict):
        """Validate a full data dict against structural requirements."""
        required = [
            "memory_id", "source", "created_at", "updated_at",
            "confidence", "provenance", "tags", "project_scope",
            "semantic_summary", "status",
        ]
        for field in required:
            if field not in data:
                raise ValueError(f"Missing required field: {field}")

        # ID format
        if not MEMORY_ID_PATTERN.match(data["memory_id"]):
            raise ValueError(f"Invalid memory_id format: {data['memory_id']}")

        # Status
        if data["status"] not in VALID_STATUSES:
            raise ValueError(f"Invalid status: {data['status']}")

        # Provenance
        prov = data.get("provenance", {})
        if "type" not in prov or "rule" not in prov:
            raise ValueError("Provenance must include 'type' and 'rule'")
        if prov["type"] not in VALID_PROVENANCE_TYPES:
            raise ValueError(f"Invalid provenance type: {prov['type']}")

        # Confidence
        conf = data.get("confidence")
        if conf is not None and not (0.0 <= conf <= 1.0):
            raise ValueError(f"Confidence must be 0.0–1.0, got {conf}")

        # Tags
        tags = data.get("tags", [])
        if not tags:
            raise ValueError("At least one tag is required")

        # Semantic summary
        summary = data.get("semantic_summary", "")
        if not summary or len(summary) > 4096:
            raise ValueError(f"semantic_summary must be 1–4096 chars, got {len(summary)}")

        # Superseded_by — only set when status is 'superseded'
        if data.get("superseded_by") and data["status"] != "superseded":
            raise ValueError("superseded_by can only be set when status is 'superseded'")

        # Contradiction refs — validate structure
        for ref in data.get("contradiction_refs", []):
            if "conflicting_memory_id" not in ref or "conflict_type" not in ref:
                raise ValueError("contradiction_refs must have conflicting_memory_id and conflict_type")
            if ref["conflict_type"] not in VALID_CONTRADICTION_TYPES:
                raise ValueError(f"Invalid conflict_type: {ref['conflict_type']}")

    def __repr__(self):
        return (
            f"MemoryRecord(id={self.memory_id}, status={self.status}, "
            f"scope={self.project_scope}, summary={self.semantic_summary[:60]}...)"
        )