"""
OverCR v2.3.0 — Workflow Registry

Central registry for workflow templates. All workflows must be
registered here before execution. The registry enforces:
  - Schema validation on registration
  - No duplicate workflow IDs
  - No recursive workflow references
  - Version tracking

Filesystem-first: workflows are loaded from templates/ JSON files.
"""

import json
import uuid
from pathlib import Path
from typing import Optional


class WorkflowRegistry:
    """
    Registers, lists, and retrieves workflow templates.

    All templates are validated against the JSON schema before
    registration. The registry is filesystem-backing — templates
    live as .json files in templates/, and the registry maintains
    an in-memory index.
    """

    def __init__(self, root: str):
        """
        Args:
            root: OverCR root directory (contains workflow_library/)
        """
        self.root = Path(root)
        self.templates_dir = self.root / "workflow_library" / "templates"
        self.schema_dir = self.root / "workflow_library" / "schema"
        self.templates_dir.mkdir(parents=True, exist_ok=True)
        self.schema_dir.mkdir(parents=True, exist_ok=True)

        # In-memory index: workflow_id -> template dict
        self._workflows: dict[str, dict] = {}

        # Load the schema
        self._schema: Optional[dict] = None
        self._load_schema()

    # --- Schema ---

    def _load_schema(self):
        """Load the JSON schema for workflow templates."""
        schema_path = self.schema_dir / "workflow_template.schema.json"
        if schema_path.exists():
            with open(schema_path, "r") as f:
                self._schema = json.load(f)

    def _get_schema(self) -> dict:
        """Return the schema, loading if necessary."""
        if self._schema is None:
            self._load_schema()
        if self._schema is None:
            raise RuntimeError("Workflow template schema not found. "
                               "Ensure workflow_library/schema/workflow_template.schema.json exists.")
        return self._schema

    # --- Validation ---

    def validate_template_schema(self, template: dict) -> tuple[bool, list[str]]:
        """
        Validate a workflow template against the JSON schema.

        Returns: (valid, errors)
        """
        errors = []
        schema = self._get_schema()

        # Check required top-level fields
        required_fields = schema.get("required", [])
        for field in required_fields:
            if field not in template:
                errors.append(f"Missing required field: '{field}'")

        if errors:
            return False, errors

        # Validate field types
        properties = schema.get("properties", {})
        for field, prop in properties.items():
            if field in template:
                expected_type = prop.get("type", "")
                actual = template[field]
                if expected_type == "string" and not isinstance(actual, str):
                    errors.append(f"Field '{field}' must be string, got {type(actual).__name__}")
                elif expected_type == "array" and not isinstance(actual, list):
                    errors.append(f"Field '{field}' must be array, got {type(actual).__name__}")
                elif expected_type == "object" and not isinstance(actual, dict):
                    errors.append(f"Field '{field}' must be object, got {type(actual).__name__}")
                elif expected_type == "boolean" and not isinstance(actual, bool):
                    errors.append(f"Field '{field}' must be boolean, got {type(actual).__name__}")
                elif expected_type == "integer" and not isinstance(actual, int):
                    errors.append(f"Field '{field}' must be integer, got {type(actual).__name__}")

        # Validate node_definitions
        if "node_definitions" in template and isinstance(template["node_definitions"], list):
            node_ids = set()
            for i, node in enumerate(template["node_definitions"]):
                if not isinstance(node, dict):
                    errors.append(f"node_definitions[{i}] must be an object")
                    continue
                if "node_id" not in node:
                    errors.append(f"node_definitions[{i}]: missing 'node_id'")
                else:
                    nid = node["node_id"]
                    if not isinstance(nid, str) or not nid.strip():
                        errors.append(f"node_definitions[{i}]: 'node_id' must be non-empty string")
                    elif nid in node_ids:
                        errors.append(f"node_definitions[{i}]: duplicate node_id '{nid}'")
                    else:
                        node_ids.add(nid)
                if "subagent" not in node:
                    errors.append(f"node_definitions[{i}] ('{node.get('node_id', '?')}'): missing 'subagent'")
                if "packet_type" not in node:
                    errors.append(f"node_definitions[{i}] ('{node.get('node_id', '?')}'): missing 'packet_type'")

        # Validate edge_definitions
        if "edge_definitions" in template and isinstance(template["edge_definitions"], list):
            edge_ids = set()
            for i, edge in enumerate(template["edge_definitions"]):
                if not isinstance(edge, dict):
                    errors.append(f"edge_definitions[{i}] must be an object")
                    continue
                if "edge_id" not in edge:
                    errors.append(f"edge_definitions[{i}]: missing 'edge_id'")
                else:
                    eid = edge["edge_id"]
                    if not isinstance(eid, str) or not eid.strip():
                        errors.append(f"edge_definitions[{i}]: 'edge_id' must be non-empty string")
                    elif eid in edge_ids:
                        errors.append(f"edge_definitions[{i}]: duplicate edge_id '{eid}'")
                    else:
                        edge_ids.add(eid)

        # Validate approval_points format
        if "approval_points" in template and isinstance(template["approval_points"], list):
            for i, ap in enumerate(template["approval_points"]):
                if not isinstance(ap, str):
                    errors.append(f"approval_points[{i}] must be string")

        # Validate stop_conditions format
        if "stop_conditions" in template and isinstance(template["stop_conditions"], list):
            for i, sc in enumerate(template["stop_conditions"]):
                if not isinstance(sc, str):
                    errors.append(f"stop_conditions[{i}] must be string")

        return len(errors) == 0, errors

    # --- Registration ---

    def register_workflow(self, template: dict) -> dict:
        """
        Register a workflow template.

        Args:
            template: The workflow template dict. Must include workflow_id.

        Returns:
            The registered template dict (with registration timestamp).

        Raises:
            ValueError: If validation fails or workflow_id exists.
        """
        # Validate schema
        valid, errors = self.validate_template_schema(template)
        if not valid:
            raise ValueError(f"Schema validation failed: {'; '.join(errors)}")

        wf_id = template["workflow_id"]

        # No duplicate IDs
        if wf_id in self._workflows:
            raise ValueError(f"Workflow '{wf_id}' is already registered")

        # No recursive self-reference
        if "depends_on" in template:
            deps = template["depends_on"]
            if isinstance(deps, list) and wf_id in deps:
                raise ValueError(f"Workflow '{wf_id}' cannot depend on itself (recursive reference)")

        # Add registration metadata
        from datetime import datetime, timezone
        template["_registered_at"] = datetime.now(timezone.utc).isoformat()
        template["_registered_version"] = template.get("version", "2.3.0")

        # Store in memory
        self._workflows[wf_id] = template

        # Write to disk
        self._save_to_disk(wf_id, template)

        return template

    def _save_to_disk(self, workflow_id: str, template: dict):
        """Save a template to the filesystem."""
        path = self.templates_dir / f"{workflow_id}.json"
        with open(path, "w") as f:
            json.dump(template, f, indent=2)

    # --- Retrieval ---

    def get_workflow(self, workflow_id: str) -> Optional[dict]:
        """
        Retrieve a registered workflow template by ID.

        Returns None if not found.
        """
        # Check in-memory index first
        if workflow_id in self._workflows:
            return dict(self._workflows[workflow_id])

        # Try loading from disk
        path = self.templates_dir / f"{workflow_id}.json"
        if path.exists():
            with open(path, "r") as f:
                template = json.load(f)
            self._workflows[workflow_id] = template
            return dict(template)

        return None

    def list_workflows(self) -> list[dict]:
        """
        List all registered workflow templates.

        Returns a list of summary dicts with id, name, version, description.
        """
        # Ensure disk templates are loaded
        self._load_all_from_disk()

        return [
            {
                "workflow_id": wf_id,
                "workflow_name": wf.get("workflow_name", ""),
                "version": wf.get("version", ""),
                "description": wf.get("description", ""),
            }
            for wf_id, wf in sorted(self._workflows.items())
        ]

    def _load_all_from_disk(self):
        """Load all templates from the templates/ directory."""
        if not self.templates_dir.exists():
            return

        for path in sorted(self.templates_dir.glob("*.json")):
            try:
                with open(path, "r") as f:
                    template = json.load(f)
                wf_id = template.get("workflow_id")
                if wf_id and wf_id not in self._workflows:
                    self._workflows[wf_id] = template
            except (json.JSONDecodeError, KeyError):
                # Skip invalid files
                pass

    # --- Lifecycle ---

    def unregister_workflow(self, workflow_id: str) -> bool:
        """
        Remove a workflow from the registry.

        Returns True if removed, False if not found.
        """
        if workflow_id not in self._workflows:
            return False

        del self._workflows[workflow_id]

        # Remove from disk
        path = self.templates_dir / f"{workflow_id}.json"
        if path.exists():
            path.unlink()

        return True

    def count(self) -> int:
        """Return the number of registered workflows."""
        self._load_all_from_disk()
        return len(self._workflows)
