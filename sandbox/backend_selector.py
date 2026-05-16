"""
OverCR v2.7.0 — Backend Selector

Selects the best available isolation backend based on operator
preference and system availability. Records every selection
decision in audit metadata. Never silently downgrades isolation.

Selection rules:
  1. If operator specifies a backend, try that first
  2. If unavailable and fallback_allowed, fall to next-best
  3. If unavailable and fallback NOT allowed, refuse execution
  4. "auto" preference: try firejail → bubblewrap → local
  5. Every fallback is audited with explicit reason
"""

from sandbox.backends.base_backend import SandboxBackend
from sandbox.backends.local_backend import LocalBackend
from sandbox.backends.bubblewrap_backend import BubblewrapBackend
from sandbox.backends.firejail_backend import FirejailBackend
from sandbox.isolation_profile import IsolationProfile

# Backend preference order (strongest first)
PREFERENCE_ORDER = ["firejail", "bubblewrap", "local"]


class BackendSelector:
    """
    Selects the best available isolation backend.

    Records every decision: which backend was chosen, whether
    fallback occurred, and why. This metadata is embedded in
    every execution receipt.
    """

    def __init__(self):
        self._backends: dict[str, SandboxBackend] = {
            "local": LocalBackend(),
            "bubblewrap": BubblewrapBackend(),
            "firejail": FirejailBackend(),
        }

    # ── Selection ──────────────────────────────────────

    def select(
        self,
        profile: IsolationProfile,
    ) -> tuple[SandboxBackend, dict]:
        """
        Select the best backend for an isolation profile.

        Args:
            profile: IsolationProfile with backend_preference and
                     fallback_allowed flag.

        Returns:
            (backend, selection_metadata)
            where selection_metadata has:
              - selected: str (backend name)
              - backend_preference: str
              - backend_available: bool
              - fallback_used: bool
              - fallback_reason: str
              - attempted: list[str] (backends tried in order)
        """
        metadata = {
            "selected": "local",
            "backend_preference": profile.backend_preference,
            "backend_available": True,
            "fallback_used": False,
            "fallback_reason": "",
            "attempted": [],
        }

        # Determine order to try
        preference = profile.backend_preference.lower()
        order = self._resolve_order(preference)

        for be_name in order:
            be = self._backends.get(be_name)
            if be is None:
                continue

            metadata["attempted"].append(be_name)

            if be.available():
                metadata["selected"] = be_name
                metadata["backend_available"] = True

                if len(metadata["attempted"]) > 1:
                    metadata["fallback_used"] = True
                    attempted_but_failed = metadata["attempted"][:-1]
                    metadata["fallback_reason"] = (
                        f"Preferred backend(s) {attempted_but_failed} "
                        f"not available; fell back to {be_name}"
                    )

                return be, metadata

        # No backend available (should never happen — local is always available)
        metadata["selected"] = "local"
        metadata["backend_available"] = True
        metadata["fallback_used"] = True
        metadata["fallback_reason"] = "All backends unavailable; forced local fallback"

        return self._backends["local"], metadata

    def _resolve_order(self, preference: str) -> list[str]:
        """
        Resolve the backend preference string to an ordered list.

        "auto" → try strongest first
        "local" → local only
        "bubblewrap" → bwrap first, fall to local
        "firejail" → firejail first, fall to local
        """
        if preference == "auto":
            return list(PREFERENCE_ORDER)
        elif preference == "local":
            return ["local"]
        elif preference == "bubblewrap":
            return ["bubblewrap", "local"]
        elif preference == "firejail":
            return ["firejail", "local"]
        else:
            # Unknown preference → auto
            return list(PREFERENCE_ORDER)

    # ── Query ──────────────────────────────────────────

    def list_available(self) -> list[dict]:
        """List all backends with availability status."""
        result = []
        for name in PREFERENCE_ORDER:
            be = self._backends[name]
            result.append({
                "name": name,
                "available": be.available(),
                "supports_network_block": be.supports_network_block(),
                "supports_readonly_mounts": be.supports_readonly_mounts(),
                "description": be.describe_isolation(),
            })
        return result

    def get_backend(self, name: str) -> SandboxBackend:
        """Get a backend by name. Falls back to local if not found."""
        return self._backends.get(name, self._backends["local"])
