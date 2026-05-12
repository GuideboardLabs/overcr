# OverCR — Release Notes

## v1.0.0 — Stabilization Release

**Date:** 2026-05-11
**Type:** Stabilization

### What This Release Means

This is the v1.0.0 stabilization release. It does not add features. It freezes the
substrate surface, hardens documentation, and establishes the baseline for
production-ready operation.

### What Changed

- Documentation polish across all entry-point files (README.md, INSTALL.md,
  RELEASE.md, CHANGELOG.md)
- docs/REPO_STRUCTURE.md updated with governance framing
- docs/HERMES_REFERENCE_RUNTIME.md updated with trust boundary and advisory
  boundary sections
- docs/GOVERNANCE_BOUNDARIES.md updated with PypER/CodER advisory boundaries
  and workflow choreography guarantees
- docs/RUNTIME_BOUNDARY.md updated with model output trust boundary and
  advisory boundaries

### What Did NOT Change

- No runtime behavior changes
- No new packet types
- No new workers
- No model routing changes
- No workflow engine changes

### Compatibility

- Runtime version: 1.0.0
- `__version__` in `runtime/__init__.py`: `"1.0.0"`
- All regression tests pass

### Substrate Guarantees

- OverCR is a Hermes-first portable orchestration substrate
- Hermes is the reference execution runtime
- Open WebUI is an optional secondary visual layer
- Other runtimes are possible but compatibility is not guaranteed
- Filesystem is the canonical source of truth
- Model output is untrusted until sanitized and validated
- No autonomous outbound contact
- No autonomous filesystem mutation
- PypER and CodER operate within advisory boundaries
- Workflow choreography is bounded, audited, and approval-aware
