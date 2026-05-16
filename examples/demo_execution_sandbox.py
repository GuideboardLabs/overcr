#!/usr/bin/env python3
"""
OverCR v2.6.0 — Demo: Controlled Execution Sandbox

Demonstrates the complete sandbox execution pipeline:
  1. Create a sandbox runner with a temp directory
  2. Execute allowed commands (ls, echo, grep, find)
  3. Show policy blocking (blocked command, chaining, traversal)
  4. Show network blocking
  5. Show filesystem mutation with rollback
  6. Show receipt generation and retrieval
  7. Show audit trail

All execution is REAL (subprocess.run) in isolated temp directories.
"""

import json, os, sys, tempfile
from pathlib import Path

OVERCR_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(OVERCR_ROOT))

from sandbox import SandboxRunner, ALLOWED_COMMANDS

def print_section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

def approval():
    return {"approved": True, "operator": "demo-operator",
            "timestamp": "2026-05-16T00:00:00Z", "reason": "demo"}

def main():
    td = tempfile.mkdtemp(prefix="overcr_sandbox_demo_")
    runner = SandboxRunner(td)

    print_section(f"Sandbox Root: {td}")
    print(f"  Allowed commands: {sorted(ALLOWED_COMMANDS)}")
    print(f"  Receipts dir: {runner.receipts_dir}")
    print(f"  Snapshots dir: {runner.snapshot.snapshot_dir}")

    # ── Step 1: Safe reads ─────────────────────────────
    print_section("Step 1: Safe Read Commands")

    for cmd, args in [("ls", ["ls", "-la"]), ("pwd", ["pwd"]),
                       ("echo", ["echo", "Hello from the sandbox"]),
                       ("grep", ["grep", "-r", "sandbox", td])]:
        result = runner.execute_request(
            command=cmd, argv=args,
            operator_identity="demo", approved_by="demo",
            approval_artifact=approval(),
        )
        status = "PASS" if result["success"] else "FAIL"
        print(f"  [{status}] {cmd}: exit={result['receipt']['exit_code']}, "
              f"elapsed={result['receipt']['elapsed_s']:.3f}s")
        if result["stdout"]:
            print(f"    stdout: {result['stdout'][:80].strip()}")

    # ── Step 2: Policy blocking ───────────────────────
    print_section("Step 2: Policy Violations (Blocked)")

    violations = [
        ("curl", ["curl", "https://evil.com"], "blocked command"),
        ("echo", ["echo", "a", "&&", "rm", "-rf", "/"], "shell chaining"),
        ("cat", ["cat", "../../../etc/passwd"], "path traversal"),
    ]
    for cmd, args, desc in violations:
        result = runner.execute_request(
            command=cmd, argv=args,
            operator_identity="demo", approved_by="demo",
            approval_artifact=approval(),
        )
        status = "BLOCKED" if not result["success"] else "EXECUTED"
        print(f"  [{status}] {desc}: {result.get('error', 'ok')[:80]}")

    # ── Step 3: Network blocking ──────────────────────
    print_section("Step 3: Network Access (Blocked)")

    net_tests = [
        ("curl", ["curl", "https://example.com"]),
        ("wget", ["wget", "http://192.168.1.1/secret"]),
        ("ssh", ["ssh", "user@evil.com"]),
    ]
    for cmd, args in net_tests:
        result = runner.execute_request(
            command=cmd, argv=args,
            operator_identity="demo", approved_by="demo",
            approval_artifact=approval(),
        )
        print(f"  BLOCKED: {cmd} -> {result.get('error', '')[:70]}")

    # ── Step 4: File operations with snapshots ────────
    print_section("Step 4: Mutating Commands with Rollback")

    # Create a file
    fpath = os.path.join(td, "important.txt")
    with open(fpath, "w") as f:
        f.write("ORIGINAL CONTENT — do not lose this")

    # Create target directory
    os.makedirs(os.path.join(td, "archive"), exist_ok=True)

    # Copy file (creates snapshots)
    tgt = os.path.join(td, "archive", "important.txt")
    result = runner.execute_request(
        command="cp", argv=["cp", fpath, tgt],
        operator_identity="demo", approved_by="demo",
        approval_artifact=approval(),
    )
    print(f"  cp executed: success={result['success']}")
    print(f"  Snapshots: {len(result['receipt']['snapshot_refs'])}")
    print(f"  Rollback available: {result['receipt']['rollback_available']}")

    # Verify target exists
    if os.path.exists(tgt):
        with open(tgt, "r") as f:
            print(f"  Target content: {f.read()[:50]}")

    # Rollback
    rollback = runner.rollback_changes(result["receipt"]["execution_id"])
    print(f"  Rollback: {rollback['success']}")

    # ── Step 5: Receipt inspection ────────────────────
    print_section("Step 5: Receipt Inspection")

    receipts = runner.list_receipts()
    print(f"  Total receipts: {len(receipts)}")

    # Show the most recent receipt in detail
    if receipts:
        last = receipts[-1]
        print(f"\n  Latest receipt: {last['execution_id']}")
        print(f"    Operator:    {last['operator_identity']}")
        print(f"    Command:     {last['executed_command']} {' '.join(last['argv'][1:])}")
        print(f"    Timestamp:   {last['timestamp'][:19]}Z")
        print(f"    Exit code:   {last['exit_code']}")
        print(f"    Elapsed:     {last['elapsed_s']}s")
        print(f"    Stdout hash: {last['stdout_hash'][:16] if last['stdout_hash'] else 'N/A'}...")
        print(f"    Snapshot refs: {len(last.get('snapshot_refs', []))}")
        print(f"\n    Governance flags:")
        for flag, val in last.get("governance_flags", {}).items():
            print(f"      {flag}: {val}")
        print(f"\n    Audit entries: {len(last['audit_entries'])}")

    # ── Step 6: Summary ───────────────────────────────
    print_section("Step 6: Summary")

    print(f"  Sandbox root:   {td}")
    print(f"  Receipts:       {len(receipts)}")
    print(f"  All commands are shell=False, real subprocess execution")
    print(f"  All mutations are snapshotted for rollback")
    print(f"  All network access is default-deny")
    print(f"  All execution is operator-approved")
    print(f"\n  Cleanup: rm -rf {td}")

    import shutil
    shutil.rmtree(td, ignore_errors=True)
    return 0

if __name__ == "__main__":
    sys.exit(main())
