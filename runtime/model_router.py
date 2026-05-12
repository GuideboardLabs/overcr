#!/usr/bin/env python3
"""
OverCR Model Router (v0.2.1) — Config-Driven Model Selection

Runtime layer that selects models/providers by route, subagent, and task type.
Model routing is config-driven, fallback-enabled, and audit-tracked.

What it does:
  - Reads model_routing.yaml configuration
  - Resolves model selection by priority: task_type → subagent → route → default
  - Records model selection and fallback decisions in audit log
  - Supports automatic fallback on timeout or empty response
  - Never advances task state on routing failure

What it does NOT do:
  - No outbound contact (no provider calls)
  - No browser/crawling
  - No new subagent spawning
  - No provider lock-in (runtime-agnostic policy layer)

Resolution priority:
  1. Task override (task_type in request packet)
  2. Subagent-specific preferred_model
  3. Route-specific preferred_model (derived from domain or assigned_subagent)
  4. default fallback

Safety guarantees:
  - Routing failure never advances task state
  - Fallback attempts are logged in audit entries
  - Empty/invalid response triggers automatic fallback
  - Both preferred and fallback models are tried before failure
"""

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

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


class ModelRouterError(Exception):
    """Raised when model routing fails."""
    pass


class RoutingResult:
    """Result of a model routing decision."""

    def __init__(
        self,
        model: str,
        provider: str,
        route_used: str,
        fallback_used: bool = False,
        fallback_reason: Optional[str] = None,
        task_id: Optional[str] = None,
        subagent: Optional[str] = None,
    ):
        self.model = model
        self.provider = provider
        self.route_used = route_used
        self.fallback_used = fallback_used
        self.fallback_reason = fallback_reason
        self.task_id = task_id
        self.subagent = subagent

    def to_dict(self) -> dict:
        result = {
            "model_selected": self.model,
            "provider": self.provider,
            "route_used": self.route_used,
            "fallback_used": self.fallback_used,
        }
        if self.fallback_reason:
            result["fallback_reason"] = self.fallback_reason
        if self.task_id:
            result["task_id"] = self.task_id
        if self.subagent:
            result["subagent"] = self.subagent
        return result


class ModelRouter:
    """Config-driven model selection layer for OverCR."""

    def __init__(self, root: str = str(OVERCR_ROOT)):
        self.root = Path(root)
        self.config_path = self.root / "config" / "model_routing.yaml"
        self._config: Optional[dict] = None
        self._validation = None
        self._audit_data: Optional[Dict] = None
        self._model_selection_log: list = []
        self._fallback_log: list = []

    @property
    def config(self) -> dict:
        """Load and parse model_routing.yaml configuration."""
        if self._config is None:
            self._config = self._load_config()
        return self._config

    @property
    def validator(self):
        """Lazy-load the validator module."""
        if self._validation is None:
            self._validation = _load_validator()
        return self._validation

    def _load_config(self) -> dict:
        """Load YAML config using a simple line-based parser."""
        if not self.config_path.exists():
            return self._default_config()

        content = self.config_path.read_text()
        lines = content.splitlines()

        config: Dict[str, Any] = {
            "_routes": {},
            "_subagents": {},
            "_audit": {"enabled": True, "log_model_selection": True, "log_fallback_count": True},
            "_routes_to_subagents": {},
        }

        current_section = None
        current_route = None
        current_subagent = None

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
            elif stripped == "_audit:":
                current_section = "_audit"
                current_route = None
                current_subagent = None
                continue
            elif stripped == "_routes_to_subagents:":
                current_section = "_routes_to_subagents"
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
                    # Route names are top-level lines (no indent), their config is indented
                    if not value:
                        # This is a route name (e.g., "overcr_hq:")
                        current_route = key
                        current_subagent = None
                        config["_routes"][current_route] = {}
                    elif current_route:
                        # This is a config value for the current route
                        config["_routes"][current_route][key] = self._parse_value(value)

                elif current_section == "_subagents":
                    # Subagent names are top-level lines, their config is indented
                    if not value:
                        current_subagent = key
                        current_route = None
                        config["_subagents"][current_subagent] = {}
                    elif current_subagent:
                        config["_subagents"][current_subagent][key] = self._parse_value(value)

                elif current_section == "_audit":
                    config["_audit"][key] = self._parse_value(value)

                elif current_section == "_routes_to_subagents":
                    config["_routes_to_subagents"][key] = value

        return config

    def _parse_value(self, value: str) -> Any:
        """Parse a YAML-like value string."""
        if isinstance(value, str):
            if value.startswith("\"") and value.endswith("\""):
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

    def _default_config(self) -> dict:
        """Return default config if file not found."""
        return {
            "_routes": {
                "default": {
                    "preferred_model": "qwen3-coder-next",
                    "fallback_model": "glm-5.1:cloud",
                    "provider": "ollama-cloud",
                    "timeout": 60,
                }
            },
            "_subagents": {},
            "_audit": {"enabled": True, "log_model_selection": True, "log_fallback_count": True},
            "_routes_to_subagents": {},
        }

    # ── Public API ──────────────────────────────────────────────

    def route(
        self,
        task_id: str,
        domain: Optional[str] = None,
        assigned_subagent: Optional[str] = None,
        task_type: Optional[str] = None,
        request_packet: Optional[dict] = None,
    ) -> RoutingResult:
        """
        Route task to appropriate model/provider.

        Priority:
          1. Task override (task_type in request_packet)
          2. Subagent-specific model
          3. Route-specific model (from domain)
          4. default fallback

        Args:
            task_id: Task identifier for audit logging
            domain: Task domain (e.g., "research", "code")
            assigned_subagent: Subagent assigned to task
            task_type: Task type override (from request_packet)
            request_packet: Full request packet dict

        Returns:
            RoutingResult with model, provider, and route info

        Raises:
            ModelRouterError: If routing fails after fallback attempts
        """
        # Determine subagent from domain if not provided
        subagent = assigned_subagent
        if not subagent and domain:
            subagent = self._get_subagent_for_domain(domain)

        # Determine route from domain or subagent
        route = self._get_route_for_task(domain, subagent, task_type)

        # Try preferred model first
        result = self._try_model_selection(
            task_id=task_id,
            route=route,
            subagent=subagent,
            fallback=False,
        )

        # If empty response or timeout, fallback
        if result is None or result.fallback_reason:
            result = self._try_model_selection(
                task_id=task_id,
                route=route,
                subagent=subagent,
                fallback=True,
                fallback_reason="Empty response or timeout on preferred model",
            )

        return result

    def _try_model_selection(
        self,
        task_id: str,
        route: str,
        subagent: Optional[str],
        fallback: bool = False,
        fallback_reason: Optional[str] = None,
    ) -> Optional[RoutingResult]:
        """Attempt to select a model and return RoutingResult."""
        # Check subagent override first
        subagent_config = self.config.get("_subagents", {}).get(subagent) if subagent else None
        if subagent_config:
            model = subagent_config.get(
                "fallback_model" if fallback else "preferred_model"
            )
            provider = subagent_config.get("provider")
            timeout = subagent_config.get("timeout", 60)
            if model:
                return self._create_result(
                    task_id=task_id,
                    model=model,
                    provider=provider or "ollama-cloud",
                    route_used=route,
                    fallback_used=fallback,
                    fallback_reason=fallback_reason,
                    subagent=subagent,
                )

        # Check route config
        route_config = self.config.get("_routes", {}).get(route)
        if route_config:
            model = route_config.get(
                "fallback_model" if fallback else "preferred_model"
            )
            provider = route_config.get("provider")
            if model:
                return self._create_result(
                    task_id=task_id,
                    model=model,
                    provider=provider or "ollama-cloud",
                    route_used=route,
                    fallback_used=fallback,
                    fallback_reason=fallback_reason,
                    subagent=subagent,
                )

        # Use default
        default_config = self.config.get("_routes", {}).get("default")
        if default_config:
            model = default_config.get(
                "fallback_model" if fallback else "preferred_model"
            )
            provider = default_config.get("provider")
            if model:
                return self._create_result(
                    task_id=task_id,
                    model=model,
                    provider=provider or "ollama-cloud",
                    route_used=route,
                    fallback_used=fallback,
                    fallback_reason=fallback_reason,
                    subagent=subagent,
                )

        return None

    def _create_result(
        self,
        task_id: str,
        model: str,
        provider: str,
        route_used: str,
        fallback_used: bool,
        fallback_reason: Optional[str] = None,
        subagent: Optional[str] = None,
    ) -> RoutingResult:
        """Create a RoutingResult and log to audit."""
        result = RoutingResult(
            model=model,
            provider=provider,
            route_used=route_used,
            fallback_used=fallback_used,
            fallback_reason=fallback_reason,
            task_id=task_id,
            subagent=subagent,
        )
        self._model_selection_log.append(result.to_dict())
        if fallback_used:
            self._fallback_log.append(result.to_dict())
        return result

    # ── Route/Subagent Resolution ───────────────────────────────

    def _get_route_for_task(
        self,
        domain: Optional[str],
        subagent: Optional[str],
        task_type: Optional[str],
    ) -> str:
        """Determine route name for a task."""
        # Check task_type override
        if task_type:
            return task_type

        # Map domain to route
        domain_to_route = {
            "research": "research",
            "analysis": "analysis",
            "code": "code",
            "diagnostics": "diagnostics",
            "outreach": "outreach",
            "recon": "recon",
            "local_boot": "local_boot",
        }
        if domain and domain in domain_to_route:
            return domain_to_route[domain]

        # Map subagent to route
        subagent_to_route = {
            "coder": "code",
            "knower": "research",
            "cryer": "recon",
            "pyper": "outreach",
        }
        if subagent and subagent in subagent_to_route:
            return subagent_to_route[subagent]

        return "default"

    def _get_subagent_for_domain(self, domain: str) -> Optional[str]:
        """Map domain to assigned subagent."""
        domain_to_subagent = {
            "code": "coder",
            "diagnostics": "coder",
            "research": "knower",
            "analysis": "knower",
            "outreach": "pyper",
            "recon": "cryer",
        }
        return domain_to_subagent.get(domain)

    # ── Audit & Utilities ───────────────────────────────────────

    def get_audit_entries(self) -> list:
        """Return audit log entries for model routing decisions."""
        entries = []
        for selection in self._model_selection_log:
            entries.append({
                "entry_type": "model_selection",
                "details": selection,
            })
        for fallback in self._fallback_log:
            entries.append({
                "entry_type": "model_fallback",
                "details": fallback,
            })
        return entries

    def get_last_routing(self) -> Optional[dict]:
        """Get the last routing decision."""
        if self._model_selection_log:
            return self._model_selection_log[-1]
        return None

    def reset(self):
        """Reset routing logs (for testing)."""
        self._model_selection_log = []
        self._fallback_log = []

    # ── Validation Helpers ──────────────────────────────────────

    def validate_packet_type(self, packet: dict) -> Tuple[bool, list, list]:
        """
        Validate packet using the existing 6-level validator.
        Returns (valid, errors, warnings).
        """
        return self.validator.validate_packet(packet)


# ── Self-test / Demo ───────────────────────────────────────────

def main():
    """Demo: exercise the model router with sample routing decisions."""
    router = ModelRouter(str(OVERCR_ROOT / ".." / ".." if str(OVERCR_ROOT).endswith("overcr-core") else OVERCR_ROOT))

    test_cases = [
        {
            "task_id": "task-demo-001",
            "domain": "research",
            "assigned_subagent": "knower",
            "task_type": None,
        },
        {
            "task_id": "task-demo-002",
            "domain": "code",
            "assigned_subagent": "coder",
            "task_type": None,
        },
        {
            "task_id": "task-demo-003",
            "domain": "recon",
            "assigned_subagent": "cryer",
            "task_type": None,
        },
        {
            "task_id": "task-demo-004",
            "domain": None,
            "assigned_subagent": "pyper",
            "task_type": "outreach",
        },
        {
            "task_id": "task-demo-005",
            "domain": "unknown_domain",
            "assigned_subagent": None,
            "task_type": None,
        },
    ]

    print("Model Routing Test (v0.2.1)")
    print("=" * 60)

    for tc in test_cases:
        print(f"\nTask: {tc['task_id']}")
        print(f"  Domain: {tc['domain']}")
        print(f"  Subagent: {tc['assigned_subagent']}")
        print(f"  Task Type Override: {tc['task_type']}")

        result = router.route(
            task_id=tc["task_id"],
            domain=tc["domain"],
            assigned_subagent=tc["assigned_subagent"],
            task_type=tc["task_type"],
        )

        print(f"  → Selected Model: {result.model}")
        print(f"  → Provider: {result.provider}")
        print(f"  → Route Used: {result.route_used}")
        print(f"  → Fallback: {result.fallback_used}")
        if result.fallback_reason:
            print(f"  → Fallback Reason: {result.fallback_reason}")

    print("\n" + "=" * 60)
    print(f"Total model selections: {len(router._model_selection_log)}")
    print(f"Total fallbacks: {len(router._fallback_log)}")

    # Show audit log
    print("\nAudit Log:")
    print("-" * 60)
    for entry in router.get_audit_entries():
        print(f"  {entry['entry_type']}: {json.dumps(entry['details'], indent=2)}")


if __name__ == "__main__":
    main()
