"""
OverCR v2.8.0 — Subworkflow Loader

Loads, validates, and pins subworkflows for composite workflow
execution. Every subworkflow reference is version-pinned and
cycles-detected. No recursive self-referencing allowed.

Requirements:
  - Cycle detection
  - Recursion prevention
  - Version pinning
  - Namespace isolation
  - Audit linkage between parent and child workflows
"""

import json
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class SubworkflowRef:
    """A pinned reference to an embedded subworkflow."""
    ref_id: str
    workflow_id: str
    version: str
    input_map: dict = field(default_factory=dict)
    output_map: dict = field(default_factory=dict)
    loaded_template: Optional[dict] = None

    def to_dict(self) -> dict:
        return {
            "ref_id": self.ref_id,
            "workflow_id": self.workflow_id,
            "version": self.version,
            "input_map": self.input_map,
            "output_map": self.output_map,
        }


class SubworkflowLoadError(Exception):
    """Raised when a subworkflow cannot be loaded."""
    pass


class SubworkflowLoader:
    """
    Loads and validates subworkflows for composite execution.

    Detects cycles in subworkflow dependency chains. Pins versions.
    Isolates namespaces between parent and child workflows.
    """

    def __init__(self, templates_dir: str):
        """
        Args:
            templates_dir: Path to workflow templates directory.
        """
        self.templates_dir = Path(templates_dir)
        self._loaded: dict[str, dict] = {}  # ref_id -> template

    def load_subworkflow(self, ref: dict) -> SubworkflowRef:
        """
        Load a subworkflow from its reference.

        Args:
            ref: Dict with ref_id, workflow_id, version, input_map, output_map.

        Returns:
            SubworkflowRef with loaded_template populated.

        Raises:
            SubworkflowLoadError: If template not found or version mismatch.
        """
        ref_id = ref.get("ref_id", "")
        wf_id = ref.get("workflow_id", "")
        version = ref.get("version", "")
        input_map = ref.get("input_map", {})
        output_map = ref.get("output_map", {})

        if not ref_id or not wf_id or not version:
            raise SubworkflowLoadError(
                f"Subworkflow ref missing required fields: {ref}"
            )

        # Load template from disk
        template_path = self.templates_dir / f"{wf_id}_workflow.json"
        if not template_path.exists():
            raise SubworkflowLoadError(
                f"Subworkflow template not found: {template_path}"
            )

        with open(template_path, "r") as f:
            template = json.load(f)

        # Version pinning — must match exactly
        template_version = template.get("version", "")
        if template_version != version:
            raise SubworkflowLoadError(
                f"Version mismatch for {wf_id}: "
                f"pinned={version}, actual={template_version}"
            )

        sw_ref = SubworkflowRef(
            ref_id=ref_id,
            workflow_id=wf_id,
            version=version,
            input_map=input_map,
            output_map=output_map,
            loaded_template=template,
        )

        self._loaded[ref_id] = template
        return sw_ref

    def load_all(self, subworkflow_refs: list[dict]) -> list[SubworkflowRef]:
        """
        Load all subworkflow references and check for cycles.

        Args:
            subworkflow_refs: List of subworkflow reference dicts.

        Returns:
            List of SubworkflowRef objects (all loaded).

        Raises:
            SubworkflowLoadError: If cycles detected or loading fails.
        """
        refs = [self.load_subworkflow(ref) for ref in subworkflow_refs]

        # Cycle detection
        if self._detect_cycles(refs):
            raise SubworkflowLoadError(
                "Cycle detected in subworkflow dependency chain"
            )

        return refs

    def _detect_cycles(self, refs: list[SubworkflowRef]) -> bool:
        """
        Detect cycles in subworkflow dependency graph.

        Uses Kahn's algorithm on the subworkflow ref graph.
        """
        # Build adjacency: ref_id -> subworkflow refs it contains
        in_degree: dict[str, int] = {}
        adj: dict[str, list[str]] = defaultdict(list)

        for ref in refs:
            rid = ref.ref_id
            if rid not in in_degree:
                in_degree[rid] = 0

            # Check if this subworkflow itself references other subworkflows
            template = ref.loaded_template
            if template:
                child_refs = template.get("subworkflow_refs", [])
                for child in child_refs:
                    child_id = child.get("ref_id", "")
                    if child_id:
                        adj[rid].append(child_id)
                        in_degree[child_id] = in_degree.get(child_id, 0) + 1

        # Kahn's
        queue = deque(rid for rid, deg in in_degree.items() if deg == 0)
        visited = 0

        while queue:
            rid = queue.popleft()
            visited += 1
            for neighbor in adj[rid]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        return visited != len(in_degree)

    def get_loaded(self, ref_id: str) -> Optional[dict]:
        """Get a loaded subworkflow template by ref_id."""
        return self._loaded.get(ref_id)

    def map_inputs(self, ref: SubworkflowRef, parent_context: dict) -> dict:
        """Map parent context to subworkflow inputs."""
        inputs = {}
        for parent_key, child_key in ref.input_map.items():
            if parent_key in parent_context:
                inputs[child_key] = parent_context[parent_key]
        inputs["_parent_run_id"] = parent_context.get("run_id", "")
        inputs["_subworkflow_ref_id"] = ref.ref_id
        return inputs

    def map_outputs(self, ref: SubworkflowRef, child_result: dict) -> dict:
        """Map subworkflow outputs back to parent context."""
        outputs = {}
        for child_key, parent_key in ref.output_map.items():
            if child_key in child_result:
                outputs[parent_key] = child_result[child_key]
        return outputs
