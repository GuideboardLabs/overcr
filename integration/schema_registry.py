"""
OverCR v2.9.0 — Schema Registry

Centralized discovery and verification of all JSON schemas
across the OverCR v2 system. Every schema is registered,
versioned, and validated for internal consistency.

Design constraints:
  - Filesystem-first: schemas live in their packages
  - No runtime schema generation
  - Schema registry is read-only discovery, not a schema authoring tool
  - Schema references are validated for referential integrity
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class SchemaEntry:
    """A registered schema with metadata."""
    schema_id: str
    path: Path
    version: str
    description: str
    schema_type: str  # "workflow", "composite", "memory", "ingestion", "sandbox", "knowledge"
    raw_schema: Optional[dict] = None
    dependent_schemas: list[str] = field(default_factory=list)

    def load(self) -> dict:
        """Load and cache the raw JSON schema."""
        if self.raw_schema is None:
            with open(self.path, "r") as f:
                self.raw_schema = json.load(f)
        return self.raw_schema


class SchemaRegistry:
    """
    Centralized schema discovery and verification.

    Scans known schema locations and maintains an index of all
    JSON schemas in the OverCR system.
    """

    # Known schema locations relative to OVERCR_ROOT
    KNOWN_SCHEMAS = {
        "workflow_template": {
            "path": "workflow_library/schema/workflow_template.schema.json",
            "version": "2.3.0",
            "description": "Base workflow template schema",
            "schema_type": "workflow",
        },
        "composite_workflow": {
            "path": "workflow_composition/schema/composite_workflow.schema.json",
            "version": "2.8.0",
            "description": "Composite workflow schema with conditional routing",
            "schema_type": "composite",
        },
        "memory_schema": {
            "path": "memory/schema/memory_record.schema.json",
            "version": "2.1.0",
            "description": "Memory record schema",
            "schema_type": "memory",
        },
        "knowledge_schema": {
            "path": "knowledge/schema/source_record.schema.json",
            "version": "2.4.0",
            "description": "Knowledge source schema",
            "schema_type": "knowledge",
        },
        "sandbox_schema": {
            "path": "sandbox/schema/execution_receipt.schema.json",
            "version": "2.6.0",
            "description": "Sandbox execution schema",
            "schema_type": "sandbox",
        },
        "web_ingestion_schema": {
            "path": "web_ingestion/schema/url_request.schema.json",
            "version": "2.5.0",
            "description": "Web ingestion request schema",
            "schema_type": "ingestion",
        },
    }

    def __init__(self, overcr_root: str):
        """
        Args:
            overcr_root: Path to the OverCR core directory.
        """
        self.root = Path(overcr_root)
        self.schemas: dict[str, SchemaEntry] = {}

    def discover_all(self) -> dict[str, SchemaEntry]:
        """
        Discover all known schemas. Returns the index dict.

        Schemas that don't exist on disk are recorded as missing
        but discovery continues.
        """
        for schema_id, info in self.KNOWN_SCHEMAS.items():
            schema_path = self.root / info["path"]
            entry = SchemaEntry(
                schema_id=schema_id,
                path=schema_path,
                version=info["version"],
                description=info["description"],
                schema_type=info["schema_type"],
            )
            self.schemas[schema_id] = entry

        return self.schemas

    def get_schema(self, schema_id: str) -> Optional[SchemaEntry]:
        """Get a schema entry by ID. Auto-discovers if needed."""
        if not self.schemas:
            self.discover_all()
        return self.schemas.get(schema_id)

    def list_schemas(self) -> list[dict]:
        """List all known schemas with metadata."""
        if not self.schemas:
            self.discover_all()
        return [
            {
                "schema_id": sid,
                "path": str(e.path.relative_to(self.root)),
                "version": e.version,
                "description": e.description,
                "schema_type": e.schema_type,
                "exists": e.path.exists(),
            }
            for sid, e in sorted(self.schemas.items())
        ]

    def verify_referential_integrity(self) -> tuple[bool, list[str]]:
        """
        Verify that all schema $ref references resolve to existing
        schemas or files in the system.
        """
        if not self.schemas:
            self.discover_all()

        errors = []
        for schema_id, entry in self.schemas.items():
            if not entry.path.exists():
                errors.append(f"Schema '{schema_id}' not found at {entry.path}")
                continue

            try:
                schema = entry.load()
            except (json.JSONDecodeError, OSError) as e:
                errors.append(f"Schema '{schema_id}' is invalid JSON: {e}")
                continue

            # Check for internal $ref references
            refs = self._extract_refs(schema)
            for ref in refs:
                if ref.startswith("#"):
                    # Local ref — fine
                    continue
                ref_path = self.root / ref
                if not ref_path.exists():
                    errors.append(
                        f"Schema '{schema_id}' references non-existent "
                        f"file: {ref}"
                    )

        return len(errors) == 0, errors

    def _extract_refs(self, schema: dict, path: str = "$") -> list[str]:
        """Recursively extract all $ref values from a JSON schema."""
        refs = []
        if isinstance(schema, dict):
            for key, value in schema.items():
                if key == "$ref" and isinstance(value, str):
                    refs.append(value)
                else:
                    refs.extend(self._extract_refs(value, f"{path}.{key}"))
        elif isinstance(schema, list):
            for i, item in enumerate(schema):
                refs.extend(self._extract_refs(item, f"{path}[{i}]"))
        return refs

    def validate_schema_completeness(self) -> tuple[bool, list[str]]:
        """
        Check that all required schemas are present and parseable.
        Returns (pass, errors).
        """
        if not self.schemas:
            self.discover_all()

        errors = []
        for schema_id, entry in self.schemas.items():
            if not entry.path.exists():
                errors.append(f"MISSING: {schema_id} at {entry.path}")
                continue
            try:
                schema = entry.load()
                if not isinstance(schema, dict):
                    errors.append(f"INVALID: {schema_id} is not a JSON object")
            except json.JSONDecodeError as e:
                errors.append(f"INVALID JSON: {schema_id}: {e}")
            except Exception as e:
                errors.append(f"ERROR loading {schema_id}: {e}")

        return len(errors) == 0, errors
