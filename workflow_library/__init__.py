"""
OverCR v2.3.0 — Workflow Library

A governed library of reusable workflow templates that operate
within the existing OverCR orchestration, validation, approval,
and audit boundaries.

This release is about reusable operational choreography, not
autonomous agent swarms. Every workflow is bounded, deterministic,
auditable, replayable, and operator-visible.

Exports:
  - WorkflowContext: Isolated per-execution context
  - WorkflowRegistry: Template registration and discovery
  - WorkflowLoader: Template loading with validation
  - WorkflowExecutor: Governed workflow execution engine
"""

from workflow_library.workflow_context import WorkflowContext
from workflow_library.workflow_registry import WorkflowRegistry
from workflow_library.workflow_loader import WorkflowLoader, WorkflowLoadError
from workflow_library.workflow_executor import WorkflowExecutor

__all__ = [
    "WorkflowContext",
    "WorkflowRegistry",
    "WorkflowLoader",
    "WorkflowLoadError",
    "WorkflowExecutor",
]

__version__ = "2.3.0"
