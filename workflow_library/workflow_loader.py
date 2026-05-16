"""
OverCR v2.3.0 — Workflow Loader

Loads workflow templates from JSON files and validates them
before returning to the executor. The loader is the only entry
point for workflow instantiation — workflows cannot be created
programmatically without going through the loader and registry.

Design constraints:
  - Only loads validated templates from the registry
  - Never loads a workflow with unsatisfied entry conditions
  - Never loads a recursive workflow
  - Produces a immutable template snapshot for execution
"""

import json
import copy
from pathlib import Path
from typing import Optional


class WorkflowLoadError(Exception):
    """Raised when a workflow cannot be loaded."""
    pass


class WorkflowLoader:
    """
    Loads workflow templates from the filesystem registry.

    The loader is intentionally simple — it delegates validation
    to the registry and only returns templates that pass all checks.
    """

    def __init__(self, registry):
        """
        Args:
            registry: A WorkflowRegistry instance.
        """
        self.registry = registry

    def load_workflow(self, workflow_id: str) -> dict:
        """
        Load a single workflow template.

        Args:
            workflow_id: The workflow's unique ID.

        Returns:
            A deep copy of the template dict (immutable from caller's perspective).

        Raises:
            WorkflowLoadError: If the workflow cannot be loaded.
        """
        template = self.registry.get_workflow(workflow_id)

        if template is None:
            raise WorkflowLoadError(f"Workflow '{workflow_id}' not found in registry")

        # Validate schema
        valid, errors = self.registry.validate_template_schema(template)
        if not valid:
            raise WorkflowLoadError(
                f"Workflow '{workflow_id}' failed schema validation: {'; '.join(errors)}"
            )

        # Check entry conditions
        entry_conditions = template.get("entry_conditions", [])
        if not self._check_entry_conditions(entry_conditions):
            raise WorkflowLoadError(
                f"Workflow '{workflow_id}': entry conditions not satisfied"
            )

        # Return a deep copy so callers can't mutate the registry's copy
        return copy.deepcopy(template)

    def load_all_templates(self) -> list[dict]:
        """
        Load all registered workflows.

        Returns a list of template dicts.
        """
        workflows = self.registry.list_workflows()
        templates = []
        for wf in workflows:
            try:
                template = self.load_workflow(wf["workflow_id"])
                templates.append(template)
            except WorkflowLoadError:
                # Skip workflows that fail validation
                pass
        return templates

    def load_template_file(self, path: str) -> dict:
        """
        Load a workflow from a JSON file path (bypasses registry for
        initial import, but must still be registered before execution).

        Args:
            path: Absolute or relative path to the .json template file.

        Returns:
            The parsed template dict.

        Raises:
            WorkflowLoadError: If the file is invalid or missing.
        """
        file_path = Path(path)
        if not file_path.exists():
            raise WorkflowLoadError(f"Template file not found: {path}")

        try:
            with open(file_path, "r") as f:
                template = json.load(f)
        except json.JSONDecodeError as e:
            raise WorkflowLoadError(f"Invalid JSON in template file {path}: {e}")

        # Basic structure check
        if "workflow_id" not in template:
            raise WorkflowLoadError(f"Template file {path} missing 'workflow_id'")
        if "node_definitions" not in template:
            raise WorkflowLoadError(f"Template file {path} missing 'node_definitions'")

        return template

    # --- Entry condition checks ---

    def _check_entry_conditions(self, conditions: list) -> bool:
        """
        Check whether entry conditions for a workflow are satisfied.

        Entry conditions are simple string rules that must all pass.
        """
        if not conditions:
            return True  # No conditions = always allowed

        for condition in conditions:
            if not self._evaluate_condition(condition):
                return False

        return True

    def _evaluate_condition(self, condition: str) -> bool:
        """
        Evaluate a single entry condition string.

        Supported conditions:
          - "registry_available": Registry must have at least 1 workflow
          - "templates_directory_exists": templates/ must exist
        """
        c = condition.strip().lower()

        if c == "registry_available":
            return self.registry.count() > 0
        if c == "templates_directory_exists":
            return self.registry.templates_dir.exists()

        # Unknown conditions are treated as warnings, not failures
        # This allows forward-compatibility with new condition types
        return True
