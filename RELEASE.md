# OverCR — Release Notes

## v2.10.0 — Stable Release Candidate

**Date:** 2026-05-16
**Type:** Stable Release Candidate
**Tests:** 27 suites passing

### What This Release Means

This is the v2.10.0 stable release candidate. It culminates the v2 roadmap —
10 capability layers built on the v1.0.0 substrate, each with full test suites,
documentation, and governance enforcement.

### v2 Roadmap — What Was Built

| Version | Layer | Key Deliverables |
|---------|-------|-----------------|
| v2.1.0 | Semantic Memory | MemoryRecord, MemoryManager, MemoryPromoter, MemoryRetriever, MemoryConflictResolver. Advisory-only model. 5 promotion rules. 6-level deterministic fallback. 31 tests. |
| v2.2.0 | Operator TUI | Dashboard, TaskView, WorkflowView, PacketInspector, AuditView, ApprovalQueue, StatusBar, KeyBindings. Observatory not cockpit. `render_plain()` fallback on all views. 81 assertions across 10 phases. |
| v2.3.0 | Workflow Library | WorkflowRegistry, WorkflowLoader, WorkflowExecutor, WorkflowContext. 5 template workflows. Isolated per-execution state. |
| v2.4.0 | Knowledge Layer | SourceRegistry, SourceClassifier, DocumentIngestor, KnowledgeIndex, ProvenanceTracker, ContradictionDetector, ResearchPacketBuilder. Append-only provenance JSONL. |
| v2.5.0 | Web Ingestion | URLRequest, FetchGateway (injectable mock), ContentNormalizer, RobotsPolicy (advisory), PromptInjectionScanner (6 categories, 20+ patterns), WebSourceBuilder. Zero network calls in tests. |
| v2.6.0 | Execution Sandbox | 14-command allowlist, CommandPolicy (9 checks), FilesystemGuard, NetworkGuard (default-deny), RollbackSnapshot, ExecutionReceipt (20+ fields), SandboxRunner. Approval-gated. |
| v2.7.0 | Kernel Isolation | SandboxBackend ABC, LocalBackend, BubblewrapBackend, FirejailBackend. BackendSelector auto-picks strongest. IsolationProfile. ResourceLimits. shell=False enforced. |
| v2.8.0 | Workflow Composition | WorkflowStateMachine, ConditionEvaluator, BranchTrace, EscalationPolicy, RetryPolicy, RoutingPolicy, SubworkflowLoader (cycle-safe). Composite DAG model. |
| v2.9.0 | Integration Hardening | SchemaRegistry, SystemValidator, ReplayValidator, StateConsistency, ReleaseIntegrity, MigrationChecker, CompatibilityMatrix, RecoveryVerifier. 8 read-only validators. 77 assertions. |
| v2.10.0 | Stable Release | SemanticCompatibility, InstallValidator, ReleaseBuilder, ReleaseManifest, VersionMatrix, ReproducibilityChecker, OperatorReadiness. Clean tar.gz with SHA256 manifest. |

### Additional Components

- **validation/** (v2.10.1): SoakTester, PerformanceBaseline, SecurityFuzzer, OperatorAcceptance, PlatformReport
- **release/**: 7 release preparation tools
- **scripts/**: 15+ check/build/release scripts
- **examples/**: 30+ demo scripts
- **references/**: 35+ architecture reference documents

### What Did NOT Change

- Core substrate guarantees from v1.0.0 remain intact
- No runtime behavior regressions
- Backward compatible with all v2 lineage versions
- Memory remains advisory (never authoritative)
- TUI remains read-only (observatory, not cockpit)

### Compatibility

- All v2.x subsystem versions: memory 2.1.0, tui 2.2.0, workflow_library 2.3.0, knowledge 2.4.0, web_ingestion 2.5.0, sandbox 2.7.0, workflow_composition 2.8.0, integration 2.9.0, release 2.10.0, validation 2.10.1
- Semantic compatibility verified across full v2 lineage
- Install validation: clean extraction → dependency check → runtime startup → test parseability
- Reproducibility: deterministic builds with SHA256 manifests

### Substrate Guarantees (unchanged from v1.0.0)

- OverCR is a Hermes-first portable orchestration substrate
- Hermes is the reference execution runtime
- Filesystem is the canonical source of truth
- Model output is untrusted until sanitized and validated (L1-L6)
- No autonomous outbound contact
- No autonomous filesystem mutation
- PypER and CodER operate within advisory boundaries
- Workflow choreography is bounded, audited, and approval-aware
- Semantic memory informs but never authorizes
- TUI reflects truth, never creates it
