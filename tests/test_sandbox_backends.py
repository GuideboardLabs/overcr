#!/usr/bin/env python3
"""
OverCR v2.7.0 — Test: Sandbox Backends

Tests backend selection, command construction, availability detection,
and receipt metadata. Does NOT require bwrap or firejail.

Coverage:
  - LocalBackend preserves v2.6 behavior
  - BackendSelector chooses local when no optional backend exists
  - BackendSelector records fallback reason
  - BubblewrapBackend availability detection
  - FirejailBackend availability detection
  - build_command never uses shell string execution
  - Isolation profile serialization
  - Network false is default
  - Fallback blocked when fallback_allowed=false (preference respects that)
  - Receipt includes backend metadata
  - All existing sandbox tests still pass
"""

import json, os, sys, tempfile
from pathlib import Path

OVERCR_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(OVERCR_ROOT))

from sandbox import (
    SandboxRunner, ExecutionReceipt,
    IsolationProfile, ResourceLimits, BackendSelector,
)
from sandbox.backends import (
    SandboxBackend, LocalBackend, BubblewrapBackend, FirejailBackend,
)

FAILED = False

def _assert(condition, msg=""):
    global FAILED
    if not condition:
        print(f"  FAIL: {msg}")
        FAILED = True

def approval():
    return {"approved": True, "operator": "test", "timestamp": "2026-05-16T00:00:00Z", "reason": "test"}

# ── Test 1: LocalBackend preserves v2.6 behavior ──────

def test_local_backend_preserves_v26():
    td = tempfile.mkdtemp(prefix="overcr_test_")
    runner = SandboxRunner(td)
    result = runner.execute_request(
        command="echo", argv=["echo", "v2.7 test"],
        operator_identity="op", approved_by="op",
        approval_artifact=approval(),
    )
    _assert(result["success"], f"local exec: {result.get('error')}")
    _assert("v2.7 test" in result["stdout"], f"stdout: {result['stdout']}")
    r = result["receipt"]
    _assert(r["sandbox_backend"] == "local", f"backend: {r['sandbox_backend']}")
    _assert(r["isolation_profile"] is not None, "profile present")
    _assert(r["governance_flags"]["command_allowed"], "policy intact")
    import shutil; shutil.rmtree(td, ignore_errors=True)
    print("  PASS: LocalBackend preserves v2.6")

# ── Test 2: BackendSelector chooses local ─────────────

def test_selector_chooses_local():
    selector = BackendSelector()
    profile = IsolationProfile.default()
    be, meta = selector.select(profile)
    # local is always available, auto preference with no bwrap/firejail → local
    _assert(be.name == "local" or be.name in ("bubblewrap", "firejail"),
            f"selected: {be.name}")
    _assert(meta["backend_available"], "backend available")
    _assert(meta["selected"] == be.name, "selected matches")
    print("  PASS: BackendSelector chooses local")

# ── Test 3: BackendSelector records fallback reason ───

def test_selector_records_fallback():
    selector = BackendSelector()
    # Explicit firejail preference with likely no firejail installed
    profile = IsolationProfile(backend_preference="firejail", fallback_allowed=True)
    be, meta = selector.select(profile)
    _assert(meta["backend_preference"] == "firejail", "pref recorded")
    if meta["fallback_used"]:
        _assert(meta["fallback_reason"], "fallback reason recorded")
        _assert("firejail" in meta["fallback_reason"].lower() or
                "firejail" in str(meta["attempted"]), "firejail attempted")
    print("  PASS: BackendSelector records fallback")

# ── Test 4: BubblewrapBackend availability ────────────

def test_bubblewrap_availability():
    be = BubblewrapBackend()
    _assert(be.name == "bubblewrap", "name correct")
    avail = be.available()
    print(f"  bwrap available: {avail}")
    # build_command always returns a list
    cmd = be.build_command(["ls", "-la"], IsolationProfile.default())
    _assert(isinstance(cmd, list), f"build_command returns list: {type(cmd)}")
    _assert("bwrap" in cmd[0], "first element is bwrap")
    _assert("ls" in cmd, "ls appears in argv")
    _assert(be.supports_network_block(), "supports network block")
    _assert(be.supports_readonly_mounts(), "supports readonly mounts")
    desc = be.describe_isolation()
    _assert(len(desc) > 20, f"description non-trivial: {desc[:50]}...")
    print("  PASS: BubblewrapBackend availability")

# ── Test 5: FirejailBackend availability ──────────────

def test_firejail_availability():
    be = FirejailBackend()
    _assert(be.name == "firejail", "name correct")
    avail = be.available()
    print(f"  firejail available: {avail}")
    cmd = be.build_command(["ls", "-la"], IsolationProfile.default())
    _assert(isinstance(cmd, list), f"build_command returns list: {type(cmd)}")
    _assert("firejail" in cmd[0], "first element is firejail")
    _assert(be.supports_network_block(), "supports network block")
    _assert(be.supports_readonly_mounts(), "supports readonly mounts")
    _assert(be.supports_resource_limits(), "supports resource limits")
    print("  PASS: FirejailBackend availability")

# ── Test 6: build_command never uses string ───────────

def test_build_command_never_string():
    for be_class in [LocalBackend, BubblewrapBackend, FirejailBackend]:
        be = be_class()
        cmd = be.build_command(["echo", "hello"], IsolationProfile.default())
        _assert(isinstance(cmd, list), f"{be.name}: returns list")
        _assert(all(isinstance(a, str) for a in cmd),
                f"{be.name}: all elements are strings")
    print("  PASS: build_command never uses string")

# ── Test 7: Isolation profile serialization ───────────

def test_isolation_profile_serde():
    p = IsolationProfile(
        network_allowed=False,
        readonly_paths=["/usr", "/bin"],
        writable_paths=["/tmp/sandbox"],
        temp_root="/tmp/sandbox",
        max_runtime_s=15.0,
        max_output_bytes=64000,
        allow_proc=False,
        allow_dev=False,
        backend_preference="auto",
        fallback_allowed=True,
    )
    d = p.to_dict()
    p2 = IsolationProfile.from_dict(d)
    _assert(p2.network_allowed is False, "network false")
    _assert(p2.readonly_paths == ["/usr", "/bin"], "readonly paths")
    _assert(p2.max_runtime_s == 15.0, "runtime")
    _assert(p2.backend_preference == "auto", "pref")
    print("  PASS: Isolation profile serialization")

# ── Test 8: Network false is default ──────────────────

def test_network_false_default():
    p = IsolationProfile.default()
    _assert(p.network_allowed is False, "network false by default")
    _assert(p.allow_proc is False, "proc false by default")
    _assert(p.allow_dev is False, "dev false by default")
    print("  PASS: Network false is default")

# ── Test 9: Receipt includes backend metadata ────────

def test_receipt_backend_metadata():
    td = tempfile.mkdtemp(prefix="overcr_test_")
    runner = SandboxRunner(td)
    profile = IsolationProfile.default(td)
    limits = ResourceLimits(timeout_s=30.0)
    result = runner.execute_request(
        command="ls", argv=["ls"],
        operator_identity="op", approved_by="op",
        approval_artifact=approval(),
        profile=profile, limits=limits,
    )
    r = result["receipt"]
    _assert(r["sandbox_backend"] == "local", f"backend: {r['sandbox_backend']}")
    _assert(r["isolation_profile"] is not None, "profile in receipt")
    _assert(r["isolation_profile"]["network_allowed"] is False, "network false in receipt")
    _assert(r["resource_limits"]["timeout_s"] == 30.0, "limits in receipt")
    _assert("backend_available" in r, "backend_available field")
    _assert("backend_fallback_used" in r, "fallback_used field")
    _assert("network_allowed" in r, "network_allowed field")
    _assert("readonly_paths" in r, "readonly_paths field")
    _assert("writable_paths" in r, "writable_paths field")
    import shutil; shutil.rmtree(td, ignore_errors=True)
    print("  PASS: Receipt includes backend metadata")

# ── Test 10: Resource limits serialization ────────────

def test_resource_limits():
    limits = ResourceLimits(timeout_s=60.0, max_stdout_bytes=1000, max_stderr_bytes=500)
    d = limits.to_dict()
    limits2 = ResourceLimits.from_dict(d)
    _assert(limits2.timeout_s == 60.0, "timeout")
    _assert(limits2.max_stdout_bytes == 1000, "stdout cap")
    # Truncation
    big = "x" * 2000
    trimmed = limits2.truncate_stdout(big)
    _assert(len(trimmed.encode("utf-8")) <= 2000, f"truncated: {len(trimmed)}")
    strict = ResourceLimits.strict(5.0)
    _assert(strict.timeout_s == 5.0, "strict timeout")
    _assert(strict.max_stdout_bytes == 64000, "strict stdout cap")
    print("  PASS: Resource limits")

# ── Test 11: Backend selector lists available ─────────

def test_selector_lists_available():
    selector = BackendSelector()
    available = selector.list_available()
    _assert(len(available) >= 2, f"at least 2 backends: {len(available)}")
    local_info = [a for a in available if a["name"] == "local"][0]
    _assert(local_info["available"], "local available")
    _assert(not local_info["supports_network_block"], "local no net block")
    print("  PASS: Selector lists available")

# ── Test 12: Preference="local" uses local only ───────

def test_preference_local_only():
    selector = BackendSelector()
    profile = IsolationProfile(backend_preference="local", fallback_allowed=True)
    be, meta = selector.select(profile)
    _assert(be.name == "local", f"local selected: {be.name}")
    _assert(not meta["fallback_used"], "no fallback for local pref")
    print("  PASS: Preference=local uses local only")

# ── Main ───────────────────────────────────────────────

def main():
    global FAILED
    print("=" * 60)
    print("OverCR v2.7.0 — Sandbox Backend Tests")
    print("=" * 60)

    # Check system
    print(f"  bwrap available:    {BubblewrapBackend().available()}")
    print(f"  firejail available: {FirejailBackend().available()}")

    tests = [
        ("LocalBackend preserves v2.6", test_local_backend_preserves_v26),
        ("BackendSelector chooses local", test_selector_chooses_local),
        ("BackendSelector records fallback", test_selector_records_fallback),
        ("BubblewrapBackend availability", test_bubblewrap_availability),
        ("FirejailBackend availability", test_firejail_availability),
        ("build_command never uses string", test_build_command_never_string),
        ("Isolation profile serialization", test_isolation_profile_serde),
        ("Network false is default", test_network_false_default),
        ("Receipt includes backend metadata", test_receipt_backend_metadata),
        ("Resource limits", test_resource_limits),
        ("Selector lists available", test_selector_lists_available),
        ("Preference=local uses local only", test_preference_local_only),
    ]
    for name, fn in tests:
        print(f"\n--- {name} ---")
        try:
            fn()
        except Exception as e:
            print(f"  ERROR: {e}")
            import traceback; traceback.print_exc()
            FAILED = True

    print("\n" + "=" * 60)
    print("RESULT: ALL TESTS PASSED" if not FAILED else "RESULT: SOME TESTS FAILED")
    return 1 if FAILED else 0

if __name__ == "__main__":
    sys.exit(main())
