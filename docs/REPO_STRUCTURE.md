# OverCR — Repository Structure

```
overcr/
├── .gitignore                        # Excludes runtime state, __pycache__, task files, audit logs
├── LICENSE.md                         # Internal use only
├── README.md                          # Overview, quick start, architecture principles
├── INSTALL.md                         # Installation guide, prerequisites
├── RELEASE.md                         # Release notes for current version
├── CHANGELOG.md                       # Full version history
├── boot.sh                            # Cold-start boot script
├── soul.md                            # Identity, personality, rules, workflow (authoritative)
├── soul_reference.md                  # Integrity-check copy of soul.md
├── test_deterministic.py              # Deterministic mode integration test
│
├── config/                            # Active configuration
│   ├── inference_routing.yaml         # Inference routing rules
│   ├── model_policy.yaml              # Model policy: capability/class/sovereignty/approval rules
│   ├── model_routing.yaml             # Model routing: domain-to-model mapping
│   └── workflow_choreography.yaml     # Workflow DAG definitions with node/edge specs
│
├── configs/                           # Deployable templates (fill {{PLACEHOLDER}} values)
│   ├── cag-memory-config.json.tpl      # CAG integration schema
│   ├── release-preservation-config.txt.tpl  # Archive policy
│   └── session-ingestion-config.json.tpl    # Session ingestion schema
│
├── demo/                              # Demo scripts
│   ├── demo_hermes_cli_adapter.py     # Hermes CLI adapter demo
│   └── demo_real_inference_v043.py    # Real inference pipeline demo
│
├── docs/                              # Documentation
│   ├── GOVERNANCE_BOUNDARIES.md       # Governance/runtime hard boundaries
│   ├── HERMES_REFERENCE_RUNTIME.md    # How Hermes drives OverCR
│   ├── REPO_STRUCTURE.md             # This file
│   ├── RUNTIME_BOUNDARY.md           # What OverCR owns vs does NOT own
│   ├── v0.4.2-reference.md           # v0.4.2 historical reference
│   └── v0.4.2-report.md              # v0.4.2 historical report
│
├── examples/                          # Runnable demos and test scripts
│   ├── runtime_demo_coder_patch_plan.py
│   ├── runtime_demo_cryer_real_inference.py
│   ├── runtime_demo_cryer_to_pyper.py
│   ├── runtime_demo_knower_claim_review.py
│   ├── runtime_demo_knower_inference_claim_review.py
│   ├── runtime_demo_knower_myth_fact.py
│   ├── runtime_demo_knower_real_inference.py
│   ├── runtime_demo_live_coder.py
│   ├── runtime_demo_live_knower.py
│   ├── runtime_demo_pyper_execution_plan.py
│   ├── test_approval_boundary.py
│   ├── test_audit_integration.py
│   ├── test_audit_integrity.py
│   ├── test_cold_start_reconstruction.py
│   ├── test_direct_subagent_routing.py
│   ├── test_doctrine_conflict.py
│   ├── test_failure_governance_approval_bypass.py
│   ├── test_live_coder_worker.py
│   ├── test_malformed_packet.py
│   ├── test_model_router.py
│   ├── test_rejection_loop.py
│   ├── test_v021.py
│   ├── test_v021_routing_policy_violations.py
│   ├── workflow_demo_coder_to_pyper.py
│   ├── workflow_demo_cryer_to_pyper.py
│   └── workflow_demo_knower_to_cryer.py
│
├── orchestration/                     # Task orchestration spec and examples
│   ├── examples/
│   │   ├── packet_cryer_booking_friction.json
│   │   ├── packet_cryer_directory_completeness.json
│   │   ├── packet_cryer_engagement_signal.json
│   │   ├── packet_cryer_hiring_growth.json
│   │   ├── packet_cryer_reputation_signal.json
│   │   ├── task_coder_patch_flow.json
│   │   ├── task_cryer_to_pyper_flow.json
│   │   └── task_knower_to_pyper_flow.json
│   ├── packet_validation_rules.md
│   ├── subagent_packet_lifecycle.md
│   ├── task_counter.json
│   ├── task_orchestration_v0.0.5.md
│   └── tasks/
│       └── .gitkeep
│
├── prompts/                           # Boot and session prompts
│   └── hq_compact_boot.md
│
├── references/                        # Architecture and design references
│   ├── architecture-overcr-substrate-v0.2.1.md
│   ├── coder-live-inference-v0.6.0.md
│   ├── cryer-live-inference-v0.5.0.md
│   ├── knower-inference-v0.4.1.md
│   ├── knower-v0.3.0.md
│   ├── model-policy-v0.2.1.md
│   ├── model-routing-quickstart.md
│   ├── model-routing-v0.2.1.md
│   ├── pyper-live-execution-v0.7.0.md
│   ├── release-candidate-v0.9.0.md
│   ├── runtime-v0.2.0-architecture.md
│   ├── runtime-v0.2.1-worker-architecture.md
│   ├── testing-v0.2.3.md
│   └── workflow-choreography-v0.8.0.md
│
├── runtime/                           # Executable runtime modules
│   ├── __init__.py                    # Version marker (1.0.0)
│   ├── approval_gate.py               # Approval-required gates + outbound blocking
│   ├── audit_integrity.py             # Audit log cross-reference verifier
│   ├── audit_writer.py                # Append-only JSONL audit log
│   ├── execution_bridge.py            # Execution bridge for live workers
│   ├── hermes_inference_adapter.py    # Hermes-specific inference adapter
│   ├── inference_adapter.py           # Generic inference adapter interface
│   ├── inference_result.py           # Inference result data types
│   ├── model_policy.py                # Model policy validation
│   ├── model_router.py                # Config-driven model selection
│   ├── output_sanitizer.py            # Control char stripping
│   ├── overcr_runtime.py              # Main runtime driver
│   ├── replay_runner.py               # Deterministic read-only replay
│   ├── subagent_adapter.py            # Bridges runtime to worker processes
│   ├── task_store.py                  # Filesystem-backed task CRUD + state machine
│   ├── worker_capabilities.py         # Capability flag validation
│   ├── worker_healthcheck.py          # Worker probe: launch/response/schema/caps
│   ├── worker_registry.py             # Centralized registration + compatibility checks
│   ├── worker_runner.py               # Subprocess execution with timeout + audit summaries
│   ├── workflow_graph.py              # DAG model for cross-worker choreography
│   ├── workflow_policy.py             # Governance engine enforcing workflow rules
│   ├── workflow_runner.py             # Orchestration engine executing workflow DAGs
│   └── README.md                      # Runtime documentation
│
├── scripts/                           # Build, check, and release scripts
│   ├── check_docs_consistency.py      # Verifies docs reference real files
│   ├── check_release_clean.py         # Verifies no forbidden paths/artifacts
│   ├── check_security.py             # Security controls checker
│   ├── check_version_consistency.py   # Version identifiers match across files
│   ├── package_release.sh             # Creates clean tar.gz and zip
│   └── release_candidate_check.py     # Master RC gate — runs all checks
│
├── security/                          # Security documentation
│   ├── THREAT_MODEL.md               # Threat model with attack vectors and mitigations
│   └── SECURITY_REVIEW_v0.9.0.md     # v0.9.0 hardening security review
│
├── skeleton/                          # Directory scaffold (copy into root on deploy)
│   ├── logs/.gitkeep
│   ├── memory/routes/hq/.gitkeep
│   ├── tasks/.gitkeep
│   ├── tui/.gitkeep
│   └── workspace/.gitkeep
│
├── subagents/                         # Governed subagent workers
│   ├── coder/
│   │   ├── inference_prompt.md        # CodER inference prompt template
│   │   ├── inference_worker.py        # CodER inference worker
│   │   ├── worker.py                  # CodER live worker (stdin/stdout JSON)
│   │   └── worker_README.md          # Worker contract documentation
│   ├── cryer/
│   │   ├── agent_runtime.md           # CryER agent runtime notes
│   │   ├── inference_prompt.md        # CryER inference prompt template
│   │   ├── inference_worker.py        # CryER inference worker
│   │   ├── worker.py                  # CryER live worker (stdin/stdout JSON)
│   │   └── worker_README.md           # Worker contract documentation
│   ├── knower/
│   │   ├── agent_runtime.md           # KnowER agent runtime notes
│   │   ├── examples/
│   │   │   ├── claim_review_response.json
│   │   │   └── myth_fact_response.json
│   │   ├── inference_prompt.md        # KnowER inference prompt template
│   │   ├── inference_worker.py        # KnowER inference worker
│   │   ├── worker.py                  # KnowER live worker (3 packet types)
│   │   └── worker_README.md           # Worker contract documentation
│   └── pyper/
│       ├── inference_prompt.md        # PypER inference prompt template
│       ├── inference_worker.py         # PypER inference worker
│       └── memory/                    # PypER execution memory
│
├── tests/                             # Consolidated test suite
│   ├── __init__.py
│   ├── hermes_cli_adapter.json        # Hermes CLI adapter test data
│   ├── run_all.py                     # Unified runner
│   ├── test_coder_patch_plan.py
│   ├── test_cryer_real_inference.py
│   ├── test_cryer_worker.py
│   ├── test_hermes_cli_adapter.py
│   ├── test_knower_claim_review.py
│   ├── test_knower_inference_mode.py
│   ├── test_knower_myth_fact.py
│   ├── test_manifest.json             # Test registry
│   ├── test_output_sanitizer.py
│   ├── test_pyper_execution_plan.py
│   ├── test_real_inference_v043.py
│   ├── test_routing_verification.py
│   ├── test_workflow_graph.py         # 15 workflow graph tests
│   ├── test_workflow_policy.py        # 36 workflow policy tests
│   └── test_workflow_runner.py        # 12 workflow runner tests
│
└── tools/                             # Standalone tools
    └── validate_packet.py             # 6-level packet validator (CLI)
```

## Governance Framing

OverCR is a **Hermes-first portable orchestration substrate**. Hermes is the
reference execution runtime. Open WebUI is an optional secondary visual layer.
Other runtimes may drive OverCR if they implement the host runtime contract,
but compatibility is not guaranteed.

The filesystem is the canonical source of truth. Model output is untrusted
until sanitized and validated. No autonomous outbound contact or filesystem
mutation is permitted. PypER and CodER operate within advisory boundaries.
Workflow choreography is bounded, audited, and approval-aware.

## What Gets Generated at Runtime (Not in Repo)

These files and directories are created when OverCR boots. They must not be committed:

- `overcr_state.json` — instance ID, boot timestamp, runtime config
- `HQ_BOOT_MANIFEST.md` — instance boot record
- `HQ_ROUTE_MARKER` — session route declaration
- `HQ_BOOT_VERIFICATION.txt` — integrity check script
- `prompts/hq_boot_context_bundle.txt` — generated boot briefing
- `prompts/hq_raw_boot_context.txt` — raw boot instructions
- `sessions/hq/` — session logs
- `logs/` — runtime logs
- `orchestration/tasks/task-*.json` — per-task state records
- `runtime/audit.jsonl` — append-only audit log
- `runtime/workflow_trace_*.jsonl` — workflow execution traces
- `configs/cag-memory-config.json` — filled config (from .tpl)
- `configs/session-ingestion-config.json` — filled config (from .tpl)
- `configs/release-preservation-config.txt` — filled config (from .tpl)