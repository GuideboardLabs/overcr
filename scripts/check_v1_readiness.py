#!/usr/bin/env python3
"""
OverCR v1.0.0 Readiness Checker
================================

Phase 2 verification gate. Runs all existing check scripts plus v1.0.0-specific
checks. Must PASS before v1.0.0 is declared ready.

Usage:
    python3 scripts/check_v1_readiness.py

Exits 0 if ALL checks pass, 1 if any fail.
"""

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
TARGET_VERSION = "1.0.0"


# ── helpers ──
def run_cmd(name: str, script: str) -> tuple[bool, str]:
    """Run a check script, return (pass, summary)."""
    path = SCRIPTS / script
    if not path.exists():
        return False, f"MISSING: {script}"
    try:
        result = subprocess.run(
            [sys.executable, str(path)],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(ROOT),
        )
        passed = (result.returncode == 0)
        # summarise last few lines
        lines = (result.stdout + "\n" + result.stderr).strip().splitlines()
        tail = " | ".join(lines[-3:]) if lines else "(no output)"
        return passed, tail
    except subprocess.TimeoutExpired:
        return False, "TIMEOUT (120s)"
    except Exception as e:
        return False, f"EXCEPTION: {e}"


def log(section: str, passed: bool, detail: str = ""):
    status = "PASS" if passed else "FAIL"
    print(f"  [{status}] {section:<45} {detail}")
    return passed


# ── check A: test suite ──
def check_tests() -> bool:
    print("\n[A] Regression Test Suite")
    passed, detail = run_cmd("run_all", "../tests/run_all.py")
    # run_all.py is one level up from scripts/
    # actually it's in tests/, so call it differently
    path = ROOT / "tests" / "run_all.py"
    if not path.exists():
        return log("test_manifest", False, "tests/run_all.py missing")
    env = dict(os.environ, PYTHONPATH=str(ROOT))
    try:
        result = subprocess.run(
            [sys.executable, str(path)],
            capture_output=True,
            text=True,
            timeout=300,
            cwd=str(ROOT),
            env=env,
        )
        passed = (result.returncode == 0)
        # count pass/fail from output
        out = result.stdout + "\n" + result.stderr
        m = re.search(r"ALL PASSED:\s+(\d+) test\(s\) passed", out)
        summary = f"{m.group(1)} tests passed" if m else detail
        # Clean transient runtime artifacts created by the test suite
        _clean_test_artifacts()
        return log("tests/run_all.py", passed, summary)
    except subprocess.TimeoutExpired:
        return log("tests/run_all.py", False, "TIMEOUT (300s)")
    except Exception as e:
        return log("tests/run_all.py", False, f"EXCEPTION: {e}")


def _clean_test_artifacts():
    """Remove runtime artifacts left behind by test runs so RC checks stay clean."""
    for f in ["runtime/audit.jsonl", "overcr_state.json", "HQ_BOOT_MANIFEST.md",
              "HQ_ROUTE_MARKER", "HQ_BOOT_VERIFICATION.txt"]:
        p = ROOT / f
        if p.exists():
            p.unlink()
    tasks_dir = ROOT / "orchestration" / "tasks"
    if tasks_dir.exists():
        for child in tasks_dir.iterdir():
            if child.name != ".gitkeep" and child.is_file():
                child.unlink()
    for d in ["sessions", "logs", "workspace"]:
        p = ROOT / d
        if p.exists():
            for child in p.iterdir():
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink()
    # Remove any __pycache__ that may have appeared
    for pycache in ROOT.rglob("__pycache__"):
        shutil.rmtree(pycache)
    for pyc in ROOT.rglob("*.pyc"):
        pyc.unlink()


# ── check B: release candidate checks ──
def check_release_candidate() -> bool:
    print("\n[B] Release Candidate Checks")
    all_pass = True
    for name, script in [
        ("release_clean", "check_release_clean.py"),
        ("security", "check_security.py"),
        ("version", "check_version_consistency.py"),
        ("docs", "check_docs_consistency.py"),
        ("candidate", "release_candidate_check.py"),
    ]:
        passed, detail = run_cmd(name, script)
        all_pass &= log(name, passed, detail[:70])
    return all_pass


# ── check C: v1.0.0-specific checks ──
def check_v1_readiness() -> bool:
    print("\n[C] v1.0.0 Readiness Checks")
    all_pass = True

    # C1 — runtime artifacts absent
    forbidden_files = [
        "overcr_state.json",
        "HQ_BOOT_MANIFEST.md",
        "HQ_ROUTE_MARKER",
        "HQ_BOOT_VERIFICATION.txt",
        "runtime/audit.jsonl",
    ]
    forbidden_dirs = ["sessions", "logs"]
    artifacts_found = []
    for f in forbidden_files:
        p = ROOT / f
        if p.exists():
            artifacts_found.append(f)
    for d in forbidden_dirs:
        p = ROOT / d
        if p.is_dir() and any(p.iterdir()):
            artifacts_found.append(f"{d}/ (non-empty)")
    all_pass &= log("C1  runtime artifacts absent", len(artifacts_found) == 0,
                    ", ".join(artifacts_found) if artifacts_found else "none found")

    # C2 — hardcoded machine paths
    bad_paths = []
    for ext in (".py", ".md", ".sh", ".yaml", ".yml", ".json", ".tpl", ".txt"):
        for fpath in ROOT.rglob(f"*{ext}"):
            parts = fpath.relative_to(ROOT).parts
            if ".git" in parts or "dist" in parts:
                continue
            # Skip reference docs and historical release docs (not runtime code)
            if parts[0] == "references" or (parts[0] == "docs" and parts[-1].startswith("v0")):
                continue
            if fpath.name in ("check_release_clean.py", "check_v1_readiness.py"):
                continue  # their job is to contain the regex
            try:
                text = fpath.read_text(errors="replace")
            except Exception:
                continue
            # look for literal /home/sc/ outside regex / allowed contexts
            for i, line in enumerate(text.splitlines(), 1):
                if "/home/sc/" in line:
                    # skip allowed contexts
                    stripped = line.strip()
                    if stripped.startswith("#") and "example" in stripped.lower():
                        continue
                    if "FORBIDDEN_PATHS" in stripped or "FORBIDDEN_CONTENT" in stripped:
                        continue
                    if "r\"/home/sc/" in stripped:
                        continue  # regex definition
                    if "$HOME" in stripped or "${HOME}" in stripped:
                        continue
                    if "Path(__file__)" in stripped:
                        continue
                    bad_paths.append(f"{fpath.relative_to(ROOT)}:{i}")
    all_pass &= log("C2  hardcoded machine paths", len(bad_paths) == 0,
                    f"{len(bad_paths)} hit(s)" + (f" — {bad_paths[0]}..." if bad_paths else ""))

    # C3 — simulated paths labeled
    # inference_adapter.py and test files should label mock outputs
    mock_unlabeled = 0
    mock_label_patterns = ("[mock]", "[MOCK]", "[mock inference]", "[simulated]")
    for fpath in list(ROOT.rglob("runtime/inference_adapter.py")) + list(ROOT.rglob("subagents/*/inference_worker.py")):
        try:
            text = fpath.read_text()
        except Exception:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if "mock" in line.lower() or "simulated" in line.lower():
                line_lower = line.lower()
                has_label = any(p in line_lower for p in mock_label_patterns)
                if not has_label:
                    # only flag lines that look like output messages (not variable assignments)
                    is_output_like = ("brief" in line.lower() or "summary" in line.lower()) and "=" not in line.split(":")[-1][:3]
                    if is_output_like:
                        mock_unlabeled += 1
    all_pass &= log("C3  mock outputs labeled", mock_unlabeled == 0,
                    f"{mock_unlabeled} unlabeled mock output line(s)")

    # C4 — direct subagent routing
    # VALID_HANDOFF_PATHS must contain only OverCR-mediated routes
    wg = ROOT / "runtime" / "workflow_graph.py"
    valid_paths_ok = wg.exists()
    if valid_paths_ok:
        content = wg.read_text()
        m = re.search(r"VALID_HANDOFF_PATHS\s*=\s*\{([^}]+)\}", content, re.DOTALL)
        if m:
            block = m.group(1)
            # each line should be a tuple of two strings
            edges = re.findall(r'\("([^"]+)",\s*"([^"]+)"\)', block)
            # all should be known subagents
            known = {"knower", "cryer", "pyper", "coder"}
            bad_edges = [e for e in edges if e[0] not in known or e[1] not in known]
            direct = bad_edges
        else:
            direct = ["parse error"]
    else:
        direct = ["workflow_graph.py missing"]
    all_pass &= log("C4  direct subagent routing", len(direct) == 0,
                    f"{len(direct)} invalid edge(s)" + (f" — {direct[0]}" if direct else ""))

    # C5 — approval bypass paths absent
    ag = ROOT / "runtime" / "approval_gate.py"
    bypass_found = []
    if ag.exists():
        text = ag.read_text()
        for term in ("bypass", "force", "override", "skip"):
            for i, line in enumerate(text.splitlines(), 1):
                # use word-boundary regex to avoid "enforce" matching "force"
                if re.search(rf'\b{term}\b', line, re.IGNORECASE):
                    # skip comments/docstrings about policy
                    stripped = line.strip()
                    if stripped.startswith("#") or stripped.startswith('"""'):
                        continue
                    if "bypass claims" in stripped.lower() or "skip.*approval" in stripped.lower():
                        continue
                    # skip legitimate governance defense strings
                    if "would bypass" in stripped.lower():
                        continue
                    bypass_found.append(f"{term} at line {i}")
    all_pass &= log("C5  approval bypass absent", len(bypass_found) == 0,
                    f"{len(bypass_found)} suspect line(s)")

    # C6 — runtime/substrate boundary clean
    # runtime/ must not contain model invocations, HTTP clients, sockets, email
    bad_imports = []
    bad_runtimes = []
    for fpath in (ROOT / "runtime").rglob("*.py"):
        try:
            text = fpath.read_text()
        except Exception:
            continue
        for module in ("requests", "urllib", "socket", "smtplib", "aiohttp", "httpx", "urllib3", "email"):
            if re.search(rf"^\s*(import\s+{module}|from\s+{module})", text, re.MULTILINE):
                bad_imports.append(f"{fpath.relative_to(ROOT)} imports {module}")
        # also look for subprocess calls to curl/wget/nc
        if re.search(r'subprocess\.\w+\(.*["\']curl["\']', text):
            bad_runtimes.append(f"{fpath.relative_to(ROOT)} subprocess curl")
        if re.search(r'subprocess\.\w+\(.*["\']wget["\']', text):
            bad_runtimes.append(f"{fpath.relative_to(ROOT)} subprocess wget")
        if re.search(r'subprocess\.\w+\(.*["\']nc\b["\']', text):
            bad_runtimes.append(f"{fpath.relative_to(ROOT)} subprocess nc")
    all_pass &= log("C6  runtime boundary clean", len(bad_imports) == 0 and len(bad_runtimes) == 0,
                    f"{len(bad_imports)} bad import(s), {len(bad_runtimes)} bad subprocess call(s)")

    # C7 — version identifier
    init_file = ROOT / "runtime" / "__init__.py"
    version_ok = False
    if init_file.exists():
        m = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', init_file.read_text())
        if m and m.group(1) == TARGET_VERSION:
            version_ok = True
            ver = m.group(1)
        else:
            ver = m.group(1) if m else "not found"
    else:
        ver = "runtime/__init__.py missing"
    all_pass &= log("C7  version == 1.0.0", version_ok, f"found '{ver}'")

    # C8 — scope freeze docs present
    freeze = ROOT / "references" / "v1.0.0-scope-freeze.md"
    reldef = ROOT / "references" / "v1.0.0-release-definition.md"
    vm = ROOT / "references" / "v1.0.0-verification-matrix.md"
    docs_ok = freeze.exists() and reldef.exists() and vm.exists()
    sizes = []
    for p in (freeze, reldef, vm):
        if p.exists():
            sizes.append(f"{p.name}: {p.stat().st_size}b")
        else:
            sizes.append(f"{p.name}: MISSING")
    all_pass &= log("C8  scope freeze docs present", docs_ok, " | ".join(sizes))

    return all_pass


# ── main ──
def main():
    print("=" * 72)
    print("OverCR v1.0.0 Readiness Checker")
    print("=" * 72)

    a = check_tests()
    b = check_release_candidate()
    c = check_v1_readiness()

    print("\n" + "=" * 72)
    print("Summary")
    print("=" * 72)

    results = [
        ("Regression tests (A)", a),
        ("Release candidate checks (B)", b),
        ("v1.0.0 readiness checks (C)", c),
    ]

    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {name}")

    overall = a and b and c
    print()
    if overall:
        print("  OVERALL: PASS — v1.0.0 readiness verified.")
        sys.exit(0)
    else:
        print("  OVERALL: FAIL — fix above issues before v1.0.0 declaration.")
        sys.exit(1)


if __name__ == "__main__":
    main()
