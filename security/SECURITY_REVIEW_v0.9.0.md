# OverCR Security Review — v0.9.0

**Date:** 2026-05-11
**Reviewer:** OverCR HQ (automated hardening pass)
**Scope:** v0.9.0 hardening — no new features

---

## 1. Review Summary

This is a hardening-only review for v0.9.0. No new features, no architecture
changes. The review focuses on: threat documentation, governance/runtime boundary
documentation, consistency checkers, and release candidate gate.

**Verdict:** PASS with conditions (see findings below).

---

## 2. Findings

### F1: workflow_trace_*.jsonl not in .gitignore [MEDIUM]

**File:** `.gitignore`
**Issue:** `runtime/workflow_trace_*.jsonl` files are generated at runtime by
`workflow_runner.py` but are not excluded by `.gitignore`. At time of review, 20+
trace files exist in `runtime/`.
**Fix:** Add `runtime/workflow_trace_*.jsonl` to `.gitignore`.
**Status:** OPEN (fix requires .gitignore update)

### F2: Phantom $HOME directory in repo [LOW]

**File:** `$HOME/overcr` directory exists inside the repo root
**Issue:** A directory literally named `$HOME` was created at some point, likely
by a script that didn't expand `$HOME` correctly. It contains nested
`overcr/security` subdirectory.
**Fix:** Remove `$HOME/` directory from repo.
**Status:** OPEN (fix requires directory removal)

### F3: Version drift across files [LOW]

**File:** `runtime/__init__.py` shows `__version__ = "0.6.0"` but `CHANGELOG.md`
records through v0.8.0 and project is in v0.9.0 hardening.
**Issue:** `runtime/__init__.py` version was not updated through v0.7.0/v0.8.0.
**Fix:** Update `__version__` in `runtime/__init__.py` to `"0.9.0"`.
**Status:** OPEN (fix requires version update)

### F4: Four docs/scripts are empty stubs [INFO]

**Files:** `docs/GOVERNANCE_BOUNDARIES.md`, `docs/RUNTIME_BOUNDARY.md`,
`scripts/check_security.py`, `scripts/check_version_consistency.py`,
`scripts/check_docs_consistency.py`, `scripts/release_candidate_check.py`
**Issue:** These files exist as 0-byte stubs from a previous session that timed out.
**Fix:** This review fills them.
**Status:** FIXED (this review)

---

## 3. Security Controls Verified

| Control | Module | Status |
|---|---|---|
| 6-level packet validation | `tools/validate_packet.py` | PASS — all levels operational |
| Approval gate enforcement | `runtime/approval_gate.py` | PASS — hard blocks, no advisory bypass |
| Workflow sovereignty | `runtime/workflow_policy.py` | PASS — cross-subagent paths validated |
| Content safety scan | `runtime/workflow_policy.py` | PASS — shell/network patterns blocked |
| Audit integrity check | `runtime/audit_integrity.py` | PASS — cross-reference + tamper detection |
| Output sanitization | `runtime/output_sanitizer.py` | PASS — control chars stripped |
| Retry limit enforcement | `runtime/approval_gate.py`, `workflow_policy.py` | PASS — hard limits (3/2) |
| Release cleanliness | `scripts/check_release_clean.py` | PASS — forbidden paths/content checked |
| Worker isolation | `runtime/worker_runner.py` | PASS — stdout/stderr capture, no file handle pass-through |

---

## 4. Attack Surface Assessment

### Network Surface: NONE

OverCR has no network stack. No HTTP listener, no API server, no socket connections.
All network interaction (if any) is delegated to the host runtime.

### Filesystem Surface: CONSTRAINED

- Reads: config YAML, task JSON, audit JSONL
- Writes: task JSON, audit JSONL, workflow traces
- No writes to user home directories, /tmp, or arbitrary paths
- All paths derived from `OVERCR_ROOT` or `Path(__file__)`

### Process Surface: ISOLATED

- Subagent workers run as subprocesses via `WorkerRunner`
- Communication: stdin JSON → stdout JSON only
- No PTY, no terminal access, no shell pipes
- Failed/timed workers: output discarded, task stays safe state

### Privilege Model: OPERATOR-GATED

- No autonomous outbound actions — all require operator approval
- Approval records include operator identity, timestamp, reason
- PypER packets ALWAYS require approval (no exceptions)
- Outreach domains ALWAYS require approval (no exceptions)

---

## 5. Recommendations for v1.0

1. **File integrity monitoring:** Hash audit log entries for tamper-proof chain
2. **Config signing:** Sign YAML configs to detect unauthorized modifications
3. **Worker sandboxing:** Mandatory container/chroot isolation for worker processes
4. **Rate limiting:** Task creation rate limits to prevent audit log flooding
5. **Penetration testing:** External review once substrate stabilizes at v1.0

---

## 6. Sign-off

This review confirms v0.9.0 hardening scope is complete once findings F1-F3
are resolved. No new features introduced. No architecture changes. No security
regressions from v0.8.0.

**Gate:** PASS (conditional on F1-F3 fixes before RC tag)