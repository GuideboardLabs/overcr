# OverCR — Changelog

All notable changes to OverCR are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

OverCR is a **portable AI orchestration substrate** — not a product or vertical.
It provides persistent contextual continuity, governance, and state management
for AI agent operations. Workloads run inside it; they are examples, not its identity.

---

## [2.11.1] — 2026-06-10

### Added

- **Negative facts (rejected approaches)** — bullet-format facts can now carry a `kind:rejected` prefix. These get injected into task context as `_vault_rejected_approaches`, telling agents what approaches are known to fail so they don't retry dead ends.
- **Next-action tracking** — bullet-format facts can carry a `kind:next_action` prefix. These get injected as `_vault_next_actions`, bridging the "what should I do next?" gap between sessions.
- `fact_parser.py`: optional `kind:` prefix in bullet format (e.g., `- [domain::key] kind:rejected This approach failed`). Backward compatible — existing facts without the prefix get `kind="n/a"`.
- `vault_adapter.py`: `VaultIndex.search()` accepts a `kind` parameter for filtering by fact kind.
- `overcr_runtime.py`: `create_task()` enriches context with `_vault_guidance`, `_vault_rejected_approaches`, and `_vault_next_actions` when vault facts of those kinds exist for the task domain.
- Vault seeds: 4 rejected facts in `5-Research/overcr/index.md`, 2 next-action facts in `1-Projects/cammander/index.md`.

### Changed

- `fact_parser.py`: bullet format now extracts `kind` from `kind:<value>` prefix in the claim text.
- `vault_adapter.py`: `VaultIndex.search()` signature extended with optional `kind` parameter.

### Testing

- `tests/test_fact_parser.py`: new test file covering kind prefix parsing, missing kind fallback, and kind-filtered search.

## [2.11.0] — 2026-06-08

### Added

- **Vault-Grounded Memory** (`knowledge/vault/`) — OverCR reads structured facts fences from an Obsidian vault and injects relevant knowledge into every task's constructed context
- `vault_adapter.py` — walks vault directories, discovers facts fences (gbrain/cammander/overcr format), builds a JSONL index, exposes domain/tag/keyword search with relevance ranking
- `fact_parser.py` — parses both pipe-table format (legacy) and bullet-list format (`- [domain::key] claim`) from `<!--- overcr:facts:begin -->` fences
- `wikilink_resolver.py` — resolves `[[wikilinks]]` to filesystem paths, builds adjacency lists, walks the graph (symlink-safe)
- Runtime integration: optional `vault_path` parameter on `OverCRRuntime`, lazy-loaded `vault_index` (zero cost if not set), automatic enrichment of `input_context._vault_facts` during `create_task()`
- 18 vault notes seeded with 203 structured facts across projects, research, tools, people, and household context (no personal specifics exposed)

### Changed

- `overcr_runtime.py`: `create_task()` now enriches context with vault facts when `vault_path` is configured. Facts ranked by domain → tag → keyword match.
- `knowledge/vault/__init__.py`: exports `VaultIndex` as single entry point

### Configuration

```python
# Single line to enable:
r = OverCRRuntime(root, vault_path="/path/to/ObsidianVault")
```

## [1.0.0] — 2026-05-11

### Changed

- Documentation and install polish for v1.0.0 stabilization
- README.md: updated substrate framing (Hermes-first), added runtime boundary statement, Safety & Governance section, v1.0.0 version history
- INSTALL.md: added Hermes-first framing, Safety & Governance section
- RELEASE.md: rewritten for v1.0.0 stabilization
- docs/REPO_STRUCTURE.md: added governance framing notes
- docs/HERMES_REFERENCE_RUNTIME.md: added Substrate Framing section (Hermes-first, Open WebUI, filesystem-first, no autonomous outbound/fs mutation, workflow choreography)
- docs/GOVERNANCE_BOUNDARIES.md: added Substrate Identity section (Hermes-first, Open WebUI, filesystem-first), PypER/CodER Advisory Boundaries, and workflow choreography guarantees
- docs/RUNTIME_BOUNDARY.md: added Substrate Framing section (Hermes-first, Open WebUI, filesystem-first, no autonomous outbound/fs mutation), bumped version to v1.0.0

### Substrate Guarantees (v1.0.0)

- OverCR is a Hermes-first portable orchestration substrate
- Hermes is the reference execution runtime; Open WebUI is optional secondary visual layer
- Other runtimes are possible but not guaranteed
- Filesystem-first source of truth
- Model output is untrusted until sanitized and validated (6-level validation)
- No autonomous outbound contact
- No autonomous filesystem mutation
- PypER and CodER are advisory-only boundaries
- Workflow choreography is bounded, audited, and approval-aware

---

## [0.8.0] — 2026-05-11

### Added

- **Workflow Graph** (`runtime/workflow_graph.py`): explicit DAG model for cross-worker choreography — `WorkflowNode`, `WorkflowEdge`, `WorkflowGraph` with validation, cycle detection, sovereignty enforcement, topological ordering, JSON serialization, and 3 factory methods (KnowER→CryER, CryER→PypER, CodER→PypER)
- **Workflow Policy** (`runtime/workflow_policy.py`): governance engine enforcing all workflow rules — node execution checks, edge handoff sovereignty, approval gates, retry limits, deterministic fallback policy, packet content safety (shell/network patterns), full workflow pre-flight checks
- **Workflow Runner** (`runtime/workflow_runner.py`): orchestration engine executing workflow DAGs with topological ordering, deterministic output generation (L1-L6 valid packets), append-only JSONL audit traces, replay from filesystem, transformation rules for edge handoffs
- **Workflow Configuration** (`config/workflow_choreography.yaml`): YAML definitions for demo workflows with node/edge specs, handoff paths, approval policies
- **3 Demo Workflow Examples** (`examples/workflow_demo_*.py`): KnowER→CryER (classify claims → governed recon), CryER→PypER (public signal → execution plan), CodER→PypER (advisory patch plan → execution plan simulation)
- **Workflow Graph Tests** (`tests/test_workflow_graph.py`): 15 tests — node/edge validation, cycle detection, sovereignty, packet type compatibility, serialization, factory methods
- **Workflow Runner Tests** (`tests/test_workflow_runner.py`): 12 tests — successful execution across all 3 demo workflows, validation/policy/approval stop conditions, audit trace completeness, replay, deterministic fallback
- **Workflow Policy Tests** (`tests/test_workflow_policy.py`): 36 tests — node execution, edge handoff, approval gates, retry limits, deterministic fallback, content safety, full workflow check, PolicyDecision semantics
- **Workflow Choreography Reference** (`references/workflow-choreography-v0.8.0.md`): v0.8.0 reference documentation covering execution model, stop conditions, all 3 runtime modules, configuration, audit/trace, deterministic mode, safety guarantees
- Test manifest updated to v0.8.0 (26 tests: 23 inherited + 3 workflow)

---

## [0.7.0] — 2026-05-11

### Added

- PypER live execution planning mode via Hermes-backed inference pipeline
- `pyper_execution_plan`, `pyper_execution_receipt`, `pyper_execution_refusal` packet types
- PypER execution plan tests (13 scenarios)
- PypER execution plan reference documentation

---

## [0.2.4] — 2026-05-10

### Added

- `.gitignore` excluding runtime state, task files, audit logs, config fills, packaging artifacts
- `LICENSE.md` (internal use only)
- `INSTALL.md` with quick start, configuration templates, runtime compatibility
- `RELEASE.md` with packaging release notes
- `CHANGELOG.md` (this file)
- `docs/REPO_STRUCTURE.md` — annotated directory tree
- `docs/HERMES_REFERENCE_RUNTIME.md` — how Hermes drives OverCR
- `scripts/package_release.sh` — creates clean tar.gz and zip packages
- `scripts/check_release_clean.py` — verifies no forbidden paths/artifacts in release

### Changed

- Path cleanup (v0.2.2): all machine-specific absolute paths replaced with `$OVERCR_ROOT` or dynamic `Path(__file__)` resolution
- README.md: OVERCR_ROOT and ARCHIVE_ROOT examples updated to use `$HOME` instead of machine-specific paths

## [0.2.3] — 2026-05-10

### Added

- `tests/run_all.py` — unified test runner (single entry point, pass/fail/duration/category reporting)
- `tests/test_manifest.json` — test registry with module, callable, category, and signal type
- `references/testing-v0.2.3.md` — testing reference documentation

### Changed

- Test scripts remain in `examples/` (individually runnable); runner imports them via manifest

## [0.2.2] — 2026-05-10

### Changed

- Replaced all machine-specific absolute paths with `$OVERCR_ROOT` or `Path(__file__)` dynamic resolution
- Removed legacy machine-specific path references from README.md, example docstrings, worker README
- Updated skill SKILL.md canonical root to `$HOME/overcr`
- `examples/test_v021_routing_policy_violations.py` and `test_audit_integration.py`: hardcoded absolute path in `sys.path.insert()` replaced with dynamic path resolution

## [0.2.1] — 2026-05-10

### Added

- Worker Registry: centralized registration with compatibility checks, duplicate/conflict rejection
- Worker Capabilities: validated capability flags per subagent (known, required, expected sets)
- Worker Healthcheck: launch/response/schema/capability verification for registered workers
- Replay Runner: deterministic read-only replay from filesystem state with tamper detection
- KnowER live worker (3 packet types: research, assessment, myth_separation)
- Model Routing Layer: config-driven model selection with policy governance
- Model Policy Layer: capability, class, sovereignty, and approval validation
- Audit Integrity Verifier: cross-reference audit log against filesystem task records

### Fixed

- v0.2.0 pitfalls documented: OUTBOUND_PATTERN false positives, GOVERNANCE_OVERRIDE_PATTERN in worker text, worker path resolution, adapter vs runtime separation

## [0.2.0] — 2026-05-10

### Added

- Live subagent worker execution via local subprocess
- CodER live worker (stdin/stdout JSON contract)
- SubagentAdapter: bridges OverCRRuntime to worker processes
- WorkerRunner: subprocess invocation with timeout, capture, kill
- Worker safety: failed/timed-out output never advances task state
- Governance override claim rejection at Level 5
- Audit-safe stdout/stderr summaries (truncated, control-char stripped)

## [0.1.0] — 2026-05-09

### Added

- OverCRRuntime: minimal executable runtime driver for v0.0.5 task lifecycle
- TaskStore: filesystem-backed CRUD with 12-state state machine
- AuditWriter: append-only JSONL audit log
- ApprovalGate: enforces approval_required gates, outbound blocking
- Operator summary trust boundary: runtime-authenticated governance, untrusted packet claims isolated
- Cold-start reconstruction: task state, audit trail, governance all recover from filesystem
- Direct subagent routing sovereignty test (L1+L5 rejection, defense-in-depth)
- Rejection loop test (3 revision cycles, abandonment)
- Malformed packet test (L1 structural rejection)
- Approval boundary test (51 assertions, 15 phases)
- Governance bypass test (24 assertions, 3 enforcement layers)
- Audit integrity test (17 assertions, tamper detection, cross-reference)

## [0.0.5] — 2026-05-10

### Added

- Task orchestration lifecycle: 12 states, filesystem-first task records
- 6-level packet validation (structural, type registration, source-packet, approval gate, forbidden actions, type-specific payload)
- 3 validated example flows (CryER→PypER, KnowER→PypER, CodER patch)
- `tools/validate_packet.py` CLI validator

## [0.0.4] — 2026-05-10

### Fixed

- CodER doctrine: added "Direct handoff | No | Never" row to governance matrix
- All workload-specific example data replaced with generic placeholders
- JSON escaping pitfall documented in skill reference

## [0.3-core] — 2026-05-09

### Added

- Clean separation: doctrine only, no live contamination
- soul.md, soul_reference.md, boot.sh
- Config templates (CAG memory, session ingestion, release preservation)
- Skeleton directory structure with .gitkeep placeholders

## [0.2] — 2026-05-09

### Added

- Full workspace including live state

## [0.1] — 2026-05-08

### Added

- Initial skeleton + soul.md