#!/usr/bin/env python3
"""
OverCR Runtime — Worker Healthcheck Tests

Tests the check_worker_health and check_all_workers functions.
"""

import sys
import tempfile
from pathlib import Path

OVERCR_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(OVERCR_ROOT))

from runtime.worker_healthcheck import (
    check_worker_health,
    check_all_workers,
    HealthcheckResult,
)
from runtime.worker_registry import WorkerRegistration, WorkerRegistry
from runtime.worker_capabilities import CAP_NO_OUTBOUND

FAILED = False

def _assert(condition, msg=""):
    global FAILED
    if not condition:
        print(f"  FAIL: {msg}")
        FAILED = True


# ── Test 1: Successful healthcheck ───────────────────────

def test_successful_healthcheck():
    """
    Verify a worker that responds correctly passes all healthchecks.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        worker_script = Path(tmpdir) / "test_worker.py"
        
        worker_code = '''import sys, json
try:
    data = json.load(sys.stdin)
    response = {
        "packet_type": "healthcheck_response",
        "version": "1.0",
        "timestamp": "2024-01-01T00:00:00Z",
        "source": "test_worker",
        "target": "overcr",
        "task_id": "healthcheck-0000",
        "summary": "Healthcheck response from test_worker",
        "status": "ok"
    }
    print(json.dumps(response))
    sys.exit(0)
except Exception as e:
    print(json.dumps({"error": str(e)}))
    sys.exit(1)
'''
        worker_script.write_text(worker_code)
        
        reg = WorkerRegistration(
            subagent="test_worker",
            version="1.0.0",
            supported_packet_types=frozenset({"healthcheck"}),
            capability_flags=frozenset({CAP_NO_OUTBOUND}),
            runtime_compat_version="0.2.1",
            worker_path="test_worker.py"
        )
        
        result = check_worker_health(
            worker_path=worker_script.resolve(),
            registration=reg,
            timeout=10.0
        )
        
        _assert(result.launch_ok, "Worker launched")
        _assert(result.response_ok, "Worker responded")
        _assert(result.schema_ok, "Response schema valid")
        _assert(result.healthy, "Worker is healthy")
        _assert(result.exit_code == 0, "Exit code is 0")
        _assert(len(result.errors) == 0, "No errors")
        
        print("  PASS: Successful healthcheck")


# ── Test 2: Worker times out ─────────────────────────────

def test_worker_times_out():
    """
    Verify a worker that takes too long is detected as timed out.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        worker_script = Path(tmpdir) / "slow_worker.py"
        
        worker_code = '''import sys, json, time
try:
    time.sleep(10)
    data = json.load(sys.stdin)
    response = {
        "packet_type": "healthcheck_response",
        "version": "1.0",
        "timestamp": "2024-01-01T00:00:00Z",
        "source": "slow_worker",
        "target": "overcr",
        "task_id": "healthcheck-0000",
        "summary": "Healthcheck response",
        "status": "ok"
    }
    print(json.dumps(response))
    sys.exit(0)
except Exception as e:
    print(json.dumps({"error": str(e)}))
    sys.exit(1)
'''
        worker_script.write_text(worker_code)
        
        reg = WorkerRegistration(
            subagent="slow_worker",
            version="1.0.0",
            supported_packet_types=frozenset({"healthcheck"}),
            capability_flags=frozenset({CAP_NO_OUTBOUND}),
            runtime_compat_version="0.2.1",
            worker_path="slow_worker.py"
        )
        
        result = check_worker_health(
            worker_path=worker_script.resolve(),
            registration=reg,
            timeout=2.0
        )
        
        _assert(result.timed_out, "Worker timed out")
        _assert(result.launch_ok, "Launch ok (started but timed out)")
        _assert(not result.response_ok, "Response failed")
        _assert(not result.healthy, "Not healthy")
        _assert(result.exit_code == -1, "Exit code is -1")
        
        print("  PASS: Worker times out")


# ── Test 3: Worker returns invalid JSON ──────────────────

def test_worker_returns_invalid_json():
    """
    Verify a worker that outputs non-JSON fails the healthcheck.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        worker_script = Path(tmpdir) / "bad_json_worker.py"
        
        worker_code = '''import sys
try:
    print("This is not valid JSON {{{")
    sys.exit(0)
except Exception as e:
    print(str(e))
    sys.exit(1)
'''
        worker_script.write_text(worker_code)
        
        reg = WorkerRegistration(
            subagent="bad_json_worker",
            version="1.0.0",
            supported_packet_types=frozenset({"healthcheck"}),
            capability_flags=frozenset({CAP_NO_OUTBOUND}),
            runtime_compat_version="0.2.1",
            worker_path="bad_json_worker.py"
        )
        
        result = check_worker_health(
            worker_path=worker_script.resolve(),
            registration=reg,
            timeout=10.0
        )
        
        _assert(result.launch_ok, "Launch ok (started)")
        _assert(not result.response_ok, "Response failed")
        _assert(not result.schema_ok, "Schema failed")
        _assert(len(result.errors) > 0, "Errors present")
        
        print("  PASS: Worker returns invalid JSON")


# ── Test 4: Worker returns valid packet but missing L1 fields ─

def test_worker_missing_l1_fields():
    """
    Verify a worker that returns valid JSON but missing required Level 1 fields fails.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        worker_script = Path(tmpdir) / "incomplete_worker.py"
        
        worker_code = '''import sys, json
try:
    data = json.load(sys.stdin)
    response = {
        "source": "incomplete_worker",
        "target": "overcr",
        "task_id": "healthcheck-0000",
        "summary": "Incomplete response"
    }
    print(json.dumps(response))
    sys.exit(0)
except Exception as e:
    print(json.dumps({"error": str(e)}))
    sys.exit(1)
'''
        worker_script.write_text(worker_code)
        
        reg = WorkerRegistration(
            subagent="incomplete_worker",
            version="1.0.0",
            supported_packet_types=frozenset({"healthcheck"}),
            capability_flags=frozenset({CAP_NO_OUTBOUND}),
            runtime_compat_version="0.2.1",
            worker_path="incomplete_worker.py"
        )
        
        result = check_worker_health(
            worker_path=worker_script.resolve(),
            registration=reg,
            timeout=10.0
        )
        
        _assert(result.launch_ok, "Worker launched")
        _assert(result.response_ok, "Response valid JSON")
        _assert(not result.schema_ok, "Schema validation failed")
        _assert(not result.healthy, "Not healthy")
        _assert(len(result.errors) > 0, "Errors present")
        
        print("  PASS: Worker missing L1 fields")


# ── Test 5: check_all_workers on multiple registrations ───

def test_check_all_workers():
    """
    Verify check_all_workers runs healthchecks on all registered workers.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        workers = ["worker_a", "worker_b", "worker_c"]
        
        for worker_name in workers:
            worker_script = Path(tmpdir) / f"{worker_name}.py"
            
            worker_code = f'''import sys, json
try:
    data = json.load(sys.stdin)
    response = {{
        "packet_type": "healthcheck_{worker_name}",
        "version": "1.0",
        "timestamp": "2024-01-01T00:00:00Z",
        "source": "{worker_name}",
        "target": "overcr",
        "task_id": "healthcheck-0000",
        "summary": "Healthcheck response from {worker_name}",
        "status": "ok"
    }}
    print(json.dumps(response))
    sys.exit(0)
except Exception as e:
    print(json.dumps({{"error": str(e)}}))
    sys.exit(1)
'''
            worker_script.write_text(worker_code)
        
        registry = WorkerRegistry()
        for idx, worker_name in enumerate(workers):
            packet_type = "healthcheck_" + worker_name
            registry.register(WorkerRegistration(
                subagent=worker_name,
                version="1.0.0",
                supported_packet_types=frozenset({packet_type}),
                capability_flags=frozenset({CAP_NO_OUTBOUND}),
                runtime_compat_version="0.2.1",
                worker_path=f"{worker_name}.py"
            ))
        
        results = check_all_workers(
            root=tmpdir,
            registry=registry,
            timeout=10.0
        )
        
        _assert(len(results) == 3, "All three workers checked")
        
        for worker_name in workers:
            result = results.get(worker_name)
            _assert(result is not None, f"{worker_name} result exists")
            _assert(result.launch_ok, f"{worker_name} launched")
            _assert(result.response_ok, f"{worker_name} responded")
            _assert(result.schema_ok, f"{worker_name} schema valid")
            _assert(result.healthy, f"{worker_name} is healthy")
        
        print("  PASS: check_all_workers")


# ── Main ──────────────────────────────────────────────────

def main():
    global FAILED
    print("=" * 60)
    print("OverCR v2.8.0 — Worker Healthcheck Tests")
    print("=" * 60)
    
    tests = [
        ("Successful healthcheck", test_successful_healthcheck),
        ("Worker times out", test_worker_times_out),
        ("Worker returns invalid JSON", test_worker_returns_invalid_json),
        ("Worker missing L1 fields", test_worker_missing_l1_fields),
        ("check_all_workers", test_check_all_workers),
    ]
    
    for name, fn in tests:
        print(f"\n--- {name} ---")
        try:
            fn()
        except Exception as e:
            print(f"  ERROR: {e}")
            import traceback
            traceback.print_exc()
            FAILED = True
    
    print("\n" + "=" * 60)
    print("RESULT: ALL TESTS PASSED" if not FAILED else "RESULT: SOME TESTS FAILED")
    return 1 if FAILED else 0

if __name__ == "__main__":
    sys.exit(main())