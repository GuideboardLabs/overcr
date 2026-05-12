#!/usr/bin/env python3
"""
OverCR Model Policy (v0.2.1) — Governance Hardening Layer

Validates model routing decisions against governance constraints.
This is a **policy layer only** — it does not execute or spawn subagents.

What it does:
  - Load model_policy.yaml configuration
  - Validate model capabilities against route/subagent policies
  - Enforce minimum model class requirements
  - Verify downgrade constraints (fallback never gains authority)
  - Check approval gate requirements
  - Validate sovereignty constraints
  - Log all policy decisions to audit trail

What it does NOT do:
  - No model execution (runtime handles that)
  - No new subagent spawning (existing runtime handles that)
  - No network contact (policy is config-only)
  - No approval action (runtime handles approval flow)
  - No provider API calls (only name selection)
"""

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# OverCR root detection
OVERCR_ROOT = Path(__file__).resolve().parent.parent

# Import path helpers
TOOLS_DIR = OVERCR_ROOT / "tools"
CONFIG_DIR = OVERCR_ROOT / "config"


def _load_validator():
    """Dynamically load the existing validate_packet module from tools/."""
    spec = importlib.util.spec_from_file_location(
        "validate_packet", TOOLS_DIR / "validate_packet.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PolicyValidationError(Exception):
    """Raised when policy validation fails."""
    pass


class PolicyResult:
    """Result of policy validation."""

    def __init__(
        self,
        valid: bool,
        route: str,
        subagent: Optional[str] = None,
        model_selected: Optional[str] = None,
        model_class: Optional[str] = None,
        errors: List[str] = None,
        warnings: List[str] = None,
        policy_facts: Dict[str, Any] = None,
    ):
        self.valid = valid
        self.route = route
        self.subagent = subagent
        self.model_selected = model_selected
        self.model_class = model_class
        self.errors = errors or []
        self.warnings = warnings or []
        self.policy_facts = policy_facts or {}

    def to_dict(self) -> dict:
        result = {
            "valid": self.valid,
            "route": self.route,
            "errors": self.errors,
            "warnings": self.warnings,
        }
        if self.subagent:
            result["subagent"] = self.subagent
        if self.model_selected:
            result["model_selected"] = self.model_selected
        if self.model_class:
            result["model_class"] = self.model_class
        if self.policy_facts:
            result["policy_facts"] = self.policy_facts
        return result


class ModelPolicy:
    """Governance policy layer for model routing."""

    # Model class hierarchy (increasing capability)
    MODEL_CLASSES = {
        "secure": 0,
        "basic": 1,
        "standard": 2,
        "advanced": 3,
        "expert": 4,
    }

    def __init__(self, root: str = str(OVERCR_ROOT)):
        self.root = Path(root)
        self.policy_path = self.root / "config" / "model_policy.yaml"
        self._policy: Optional[dict] = None
        self._validator = None
        self._audit_log: List[dict] = []

    @property
    def policy(self) -> dict:
        """Load and parse model_policy.yaml configuration."""
        if self._policy is None:
            self._policy = self._load_policy()
        return self._policy

    @property
    def validator(self):
        """Lazy-load the validator module."""
        if self._validator is None:
            self._validator = _load_validator()
        return self._validator

    def _load_policy(self) -> dict:
        """Load YAML policy (simple parser to avoid external deps)."""
        if not self.policy_path.exists():
            return self._default_policy()

        content = self.policy_path.read_text()
        lines = content.splitlines()

        policy: Dict[str, Any] = {
            "_routes": {},
            "_subagents": {},
            "_model_classes": {},
            "approval_gate": {
                "tasks_requiring_approval": [],
                "tasks_allowed_without_approval": [],
            },
            "audit_policy": {
                "required_fields": [],
                "log_fallback_decisions": True,
                "log_capability_check": True,
                "log_sovereignty_violation": True,
            },
            "validation": {"default_level": 4, "enforce_on_fallback": True},
        }

        current_section = None
        current_route = None
        current_subagent = None
        current_approval_section = None

        for line in lines:
            stripped = line.strip()

            # Skip comments and empty lines
            if not stripped or stripped.startswith("#"):
                continue

            # Detect section headers
            if stripped == "_routes:":
                current_section = "_routes"
                current_route = None
                current_subagent = None
                continue
            elif stripped == "_subagents:":
                current_section = "_subagents"
                current_route = None
                current_subagent = None
                continue
            elif stripped == "_model_classes:":
                current_section = "_model_classes"
                current_route = None
                current_subagent = None
                continue
            elif stripped == "approval_gate:":
                current_section = "approval_gate"
                current_approval_section = None
                current_route = None
                current_subagent = None
                continue
            elif stripped == "audit_policy:":
                current_section = "audit_policy"
                current_route = None
                current_subagent = None
                continue
            elif stripped == "validation:":
                current_section = "validation"
                current_route = None
                current_subagent = None
                continue
            elif current_section == "approval_gate" and stripped == "tasks_requiring_approval:":
                current_approval_section = "tasks_requiring_approval"
                continue
            elif current_section == "approval_gate" and stripped == "tasks_allowed_without_approval:":
                current_approval_section = "tasks_allowed_without_approval"
                continue
            elif stripped == "audit_policy:":
                current_section = "audit_policy"
                current_approval_section = None
                current_route = None
                current_subagent = None
                continue

            # Parse key: value pairs
            if ":" in stripped:
                key, value = stripped.split(":", 1)
                key = key.strip()
                value = value.strip()

                # Determine where to store this value
                if current_section == "_routes":
                    if not value:
                        current_route = key
                        policy["_routes"][current_route] = {}
                    elif current_route:
                        policy["_routes"][current_route][key] = self._parse_value(value)

                elif current_section == "_subagents":
                    if not value:
                        current_subagent = key
                        policy["_subagents"][current_subagent] = {}
                    elif current_subagent:
                        policy["_subagents"][current_subagent][key] = self._parse_value(value)

                elif current_section == "_model_classes":
                    if not value:
                        current_model_class = key
                        policy["_model_classes"][current_model_class] = {}
                    elif current_model_class:
                        if key == "capabilities":
                            # Parse list format [a, b, c]
                            items = value.strip("[]").replace(" ", "").split(",")
                            policy["_model_classes"][current_model_class][key] = items
                        else:
                            policy["_model_classes"][current_model_class][key] = self._parse_value(value)

                elif current_section == "approval_gate":
                    if current_approval_section == "tasks_requiring_approval":
                        # Parse list item format "- key"
                        if value.startswith("- "):
                            val = value[2:].strip()
                            policy["approval_gate"].setdefault(current_approval_section, []).append(val)
                    elif current_approval_section == "tasks_allowed_without_approval":
                        if value.startswith("- "):
                            val = value[2:].strip()
                            policy["approval_gate"].setdefault(current_approval_section, []).append(val)

                elif current_section == "audit_policy":
                    policy["audit_policy"][key] = self._parse_value(value)

                elif current_section == "validation":
                    policy["validation"][key] = self._parse_value(value)

        return policy

    def _parse_value(self, value: str) -> Any:
        """Parse a YAML-like value string."""
        if isinstance(value, str):
            if value.startswith("[") and value.endswith("]"):
                # List format [a, b, c]
                items = value.strip("[]").replace(" ", "").split(",")
                return [self._parse_value(v) for v in items if v]
            elif value.startswith(""") and value.endswith("""):
                return value[1:-1]
            elif value.startswith("'") and value.endswith("'"):
                return value[1:-1]
            elif value.isdigit():
                return int(value)
            elif value == "true":
                return True
            elif value == "false":
                return False
            elif value.lower() == "none":
                return None
        return value

    def _default_policy(self) -> dict:
        """Return default policy if file not found."""
        return {
            "_routes": {},
            "_subagents": {},
            "_model_classes": {
                "secure": {
                    "capabilities": ["readonly"],
                    "max_token_output": 1000,
                    "max_context": 4096,
                    "network_allowed": False,
                },
                "basic": {
                    "capabilities": ["readonly", "local_only"],
                    "max_token_output": 2000,
                    "max_context": 8192,
                    "network_allowed": False,
                },
                "standard": {
                    "capabilities": ["readonly", "local_only", "analysis"],
                    "max_token_output": 4000,
                    "max_context": 16384,
                    "network_allowed": False,
                },
                "advanced": {
                    "capabilities": ["readonly", "local_only", "analysis", "research", "diagnostics"],
                    "max_token_output": 8000,
                    "max_context": 32768,
                    "network_allowed": False,
                },
                "expert": {
                    "capabilities": ["readonly", "local_only", "analysis", "research", "diagnostics", "code_generation", "outreach", "recon"],
                    "max_token_output": 16000,
                    "max_context": 65536,
                    "network_allowed": True,
                },
            },
            "approval_gate": {
                "tasks_requiring_approval": [],
                "tasks_allowed_without_approval": [],
            },
            "audit_policy": {
                "required_fields": [],
                "log_fallback_decisions": True,
                "log_capability_check": True,
                "log_sovereignty_violation": True,
            },
            "validation": {"default_level": 4, "enforce_on_fallback": True},
        }

    # ── Public Validation API ────────────────────────────────────

    def validate_routing(
        self,
        model: str,
        route: str,
        subagent: Optional[str] = None,
        model_class: Optional[str] = None,
        preferred_class: Optional[str] = None,
        fallback_class: Optional[str] = None,
    ) -> PolicyResult:
        """
        Validate a routing decision against policy constraints.

        Args:
            model: Selected model name
            route: Route name
            subagent: Subagent name (optional)
            model_class: Class of selected model (optional, auto-detected if not provided)
            preferred_class: Class of preferred model (for downgrade check)
            fallback_class: Class of fallback model (for downgrade check)

        Returns:
            PolicyResult with validation status and details
        """
        # Auto-detect model class if not provided
        if not model_class:
            model_class = self._get_model_class_for_model(model, route, subagent)

        # Get route policy
        route_policy = self.policy.get("_routes", {}).get(route, {})
        subagent_policy = self.policy.get("_subagents", {}).get(subagent, {}) if subagent else {}

        # Build combined policy (subagent overrides route)
        combined_policy = {}
        combined_policy.update(route_policy)
        if subagent_policy:
            combined_policy.update(subagent_policy)

        errors = []
        warnings = []

        # R1: Check capability overlap
        allowed_caps = set(route_policy.get("allowed_capabilities", []))
        forbidden_caps = set(route_policy.get("forbidden_capabilities", []))

        # Get model capabilities from its class
        model_caps = set(self._get_capabilities_for_class(model_class))

        # Check if model capabilities violate forbidden
        conflict = model_caps & forbidden_caps
        if conflict:
            errors.append(f"Model capabilities conflict with route: {sorted(conflict)}")
            warnings.append(f"Forbidden capabilities: {sorted(conflict)}")

        # Check if model capabilities are all allowed
        if allowed_caps and not model_caps.issubset(allowed_caps):
            missing = model_caps - allowed_caps
            errors.append(f"Model capabilities not in allowed set: {sorted(missing)}")
            warnings.append(f"Missing allowed capability: {sorted(missing)}")

        # R2: Check downgrade constraint (prefer >= fallback)
        if preferred_class and fallback_class:
            pref_level = self.MODEL_CLASSES.get(preferred_class, 0)
            fall_level = self.MODEL_CLASSES.get(fallback_class, 0)
            if fall_level > pref_level:
                errors.append(
                    f"Downgrade would increase authority: "
                    f"{preferred_class} ({pref_level}) → {fallback_class} ({fall_level})"
                )
            elif fall_level < pref_level:
                removed = set(self._get_capabilities_for_class(preferred_class)) - set(self._get_capabilities_for_class(fallback_class))
                if removed:
                    warnings.append(f"Downgrade removed capabilities: {sorted(removed)}")

        # R3: Check minimum model class
        min_class = combined_policy.get("minimum_model_class", "standard")
        min_level = self.MODEL_CLASSES.get(min_class, 2)
        current_level = self.MODEL_CLASSES.get(model_class, 2)
        if current_level < min_level:
            errors.append(
                f"Model class below minimum for route: "
                f"{model_class} ({current_level}) < {min_class} ({min_level})"
            )

        # R4: Check approval gate
        approval_required = combined_policy.get("approval_required", False)
        if approval_required:
            warnings.append("Route requires approval but approval status not verified")

        # R5: Check sovereignty
        sovereignty = combined_policy.get("sovereignty", "local")
        if sovereignty == "local" and "network" in model_caps:
            errors.append("Local model cannot perform network operations")

        # Build policy facts
        policy_facts = {
            "model_class": model_class,
            "minimum_class_required": combined_policy.get("minimum_model_class"),
            "maximum_class_allowed": combined_policy.get("preferred_model_class"),
            "approval_required": approval_required,
            "sovereignty": sovereignty,
            "capabilities_allowed": list(allowed_caps),
            "capabilities_forbidden": list(forbidden_caps),
            "capabilities_actual": list(model_caps),
        }

        return PolicyResult(
            valid=len(errors) == 0,
            route=route,
            subagent=subagent,
            model_selected=model,
            model_class=model_class,
            errors=errors,
            warnings=warnings,
            policy_facts=policy_facts,
        )

    def _get_model_class_for_model(
        self, model: str, route: str, subagent: Optional[str]
    ) -> str:
        """Auto-detect model class based on model name and route policy."""
        # Basic heuristics based on known models
        # In production, this would map to actual model registry

        route_policy = self.policy.get("_routes", {}).get(route, {})
        subagent_policy = self.policy.get("_subagents", {}).get(subagent, {}) if subagent else {}

        # Prefer subagent policy if available
        preferred_class = subagent_policy.get("preferred_model_class") or route_policy.get("preferred_model_class")
        if preferred_class:
            return preferred_class

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

    def _get_capabilities_for_class(self, model_class: str) -> List[str]:
        """Get the capabilities for a given model class."""
        classes = self.policy.get("_model_classes", {})
        if model_class in classes:
            return classes[model_class].get("capabilities", [])
        return ["readonly"]  # Default safest capability

    def _get_class_level(self, model_class: str) -> int:
        """Get numeric level for a model class."""
        return self.MODEL_CLASSES.get(model_class, 0)

    # ── Batch Validation ─────────────────────────────────────────

    def validate_fallback(
        self,
        preferred_model: str,
        fallback_model: str,
        route: str,
        subagent: Optional[str] = None,
    ) -> PolicyResult:
        """
        Validate a fallback decision (preferred → fallback).

        Ensures downgrade never gains authority.
        """
        preferred_class = self._get_model_class_for_model(preferred_model, route, subagent)
        fallback_class = self._get_model_class_for_model(fallback_model, route, subagent)

        result = self.validate_routing(
            model=fallback_model,
            route=route,
            subagent=subagent,
            model_class=fallback_class,
            preferred_class=preferred_class,
            fallback_class=fallback_class,
        )

        # Add downgrade-specific info
        result.policy_facts["downgrade_check"] = {
            "preferred_model": preferred_model,
            "fallback_model": fallback_model,
            "preferred_class": preferred_class,
            "fallback_class": fallback_class,
            "downgrade_valid": self._get_class_level(fallback_class) <= self._get_class_level(preferred_class),
        }

        return result

    # ── Debug/Utility ───────────────────────────────────────────

    def get_policy_summary(self) -> dict:
        """Return summary of loaded policy."""
        return {
            "routes": list(self.policy.get("_routes", {}).keys()),
            "subagents": list(self.policy.get("_subagents", {}).keys()),
            "model_classes": list(self.policy.get("_model_classes", {}).keys()),
            "model_class_levels": self.MODEL_CLASSES,
            "approval_gate": self.policy.get("approval_gate", {}),
        }

    def get_audit_entries(self) -> List[dict]:
        """Return audit log entries."""
        return self._audit_log

    def log_policy_decision(self, decision_type: str, result: PolicyResult):
        """Log a policy decision to audit trail."""
        entry = {
            "entry_type": f"policy_{decision_type}",
            "timestamp": None,  # Set by audit layer
            "policy_result": result.to_dict(),
        }
        self._audit_log.append(entry)

    def reset(self):
        """Reset policy and audit logs."""
        self._audit_log = []


# ── Self-test / Demo ───────────────────────────────────────────

def main():
    """Demo: validate sample routing decisions against policy."""
    policy = ModelPolicy()

    test_cases = [
        ("task-001", "glm-5.1:cloud", "research", "knower"),
        ("task-002", "qwen3-coder-next", "code", "coder"),
        ("task-003", "glm-5.1:cloud", "recon", "cryer"),
        ("task-004", "qwen3:4b", "local_boot", "pyper"),
    ]

    print("Model Policy Validation (v0.2.1)")
    print("=" * 60)

    for task_id, model, route, subagent in test_cases:
        print("")
        print(f"{task_id}: {model} on {route} ({subagent})")

        result = policy.validate_routing(
            model=model,
            route=route,
            subagent=subagent,
        )

        print(f"  Policy valid: {result.valid}")
        if result.model_class:
            print(f"  Model class: {result.model_class}")
        if result.policy_facts:
            print(f"  Minimum class: {result.policy_facts.get('minimum_class_required')}")
            print(f"  Approval required: {result.policy_facts.get('approval_required')}")

        if result.warnings:
            print(f"  Warnings: {result.warnings}")
        if result.errors:
            print(f"  Errors: {result.errors}")

    print("")
    print("=" * 60)
    print(f"Total validations: {len(policy._audit_log)}")

    # Show policy summary
    print("")
    print("Policy Summary:")
    print("-" * 60)
    summary = policy.get_policy_summary()
    for key, value in summary.items():
        if isinstance(value, list):
            print(f"  {key}: {value}")
        elif isinstance(value, dict):
            print(f"  {key}: {list(value.keys())}")


if __name__ == "__main__":
    main()
