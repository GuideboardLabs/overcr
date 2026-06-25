# OverCR 
(v2.11.1 — Negative Facts & Next-Action Tracking)

![Python](https://img.shields.io/badge/Python-3.11%2B-blue)
![Runtime](https://img.shields.io/badge/Runtime-Hermes--first-purple)
![Architecture](https://img.shields.io/badge/Architecture-Filesystem--first-green)
![Validation](https://img.shields.io/badge/Validation-L1--L6-critical)
![Tests](https://img.shields.io/badge/Tests-27_suites_passing-brightgreen)
![Release](https://img.shields.io/badge/Release-v2.11.1-gold)
![License](https://img.shields.io/badge/License-MIT-yellow)
![Status](https://img.shields.io/badge/Status-Stable-success)

---

OverCR (Operational Vigilance, Execution, Recovery, Command & Routing) is a **Hermes-first portable AI orchestration substrate**.

It is not a chatbot, a SaaS wrapper, or a vertical product. It is the governed operating layer that AI workloads run inside.

OverCR provides identity, doctrine, boot continuity, filesystem-first state, subagent routing, packet validation (L1-L6), workflow choreography, audit trails, approval gates, semantic memory, operator TUI, knowledge management, controlled web ingestion, execution sandboxing with kernel isolation, integration hardening, release validation, and vault-grounded guidance facts (negative facts + next-action tracking).

## Capability Layers

| Version | Layer | Description |
|---------|-------|-------------|
| v1.0.0 | Substrate Core | Identity, doctrine, boot, subagent routing, L1-L6 packet validation, task lifecycle, approval gates, audit trails |
| v2.1.0 | Semantic Memory | Governed advisory memory — informs but never authorizes. Rule-gated promotion, conflict detection, deterministic retrieval |
| v2.2.0 | Operator TUI | Terminal-first observatory — task views, DAG visualization, packet inspection, audit streaming, approval queue. Reads from FS, never mutates |
| v2.3.0 | Workflow Library | Template-based reusable workflows with registry, loader, executor, isolated contexts |
| v2.4.0 | Knowledge Layer | Governed research subsystem — source registry, classification, document ingestion, knowledge index, provenance tracking, contradiction detection |
| v2.5.0 | Web Ingestion | Operator-auditable single-page fetches with URL validation, prompt injection scanning, content normalization, robots policy |
| v2.6.0 | Execution Sandbox | Approval-gated command execution — 14-command allowlist, 9-check policy, filesystem guard, network guard (default-deny), rollback snapshots, execution receipts |
| v2.7.0 | Kernel Isolation | Backend abstraction with LocalBackend, BubblewrapBackend, FirejailBackend. Auto-selects strongest available. Isolation profiles, resource limits |
| v2.8.0 | Workflow Composition | Composite DAGs — condition evaluation, branching, escalation policy, retry policy, routing policy, subworkflow loading with cycle detection, state machine |
| v2.9.0 | Integration Hardening | 8 validators — schema registry, system validation, replay determinism, state consistency, release integrity, migration checking, compatibility matrix, recovery verification |
| v2.10.0 | Stable Release | Release preparation — semantic compatibility, install validation, reproducible builds, operator readiness, version matrix, release manifests |
| v2.11.0 | Vault Memory | Obsidian vault integration — reads structured facts fences, builds index, injects relevant knowledge into task context at creation time. No vector DB. No embeddings. Pure CAG. |
| v2.11.1 | Guidance Facts | Negative facts (`kind:rejected`) and next-action tracking (`kind:next_action`) — agents stop retrying dead ends and know what to do next. Optional fact kind prefix, backward compatible. |

## Directory Structure

```
overcr/
  README.md                              # This file
  CHANGELOG.md                           # Full change history v0.1 → v2.10.0
  INSTALL.md                             # Installation and quick start
  RELEASE.md                             # Release notes
  LICENSE.md                             # MIT license
  soul.md                                # Identity, personality, rules, workflow
  soul_reference.md                      # Integrity-check copy of soul.md
  boot.sh                                # Cold-start boot script

  config/                                # YAML configuration
    inference_routing.yaml               # Inference routing policy
    model_policy.yaml                    # Model capability/class/sovereignty policy
    model_routing.yaml                   # Model routing configuration
    workflow_choreography.yaml           # Workflow choreography definitions

  configs/                               # Config templates (v1-era, fill placeholders)
  prompts/                               # Boot prompt templates
  skeleton/                              # Directory scaffold for new instances

  memory/                                # v2.1.0 — Semantic memory layer
  tui/                                   # v2.2.0 — Operator interface (observatory)
  workflow_library/                      # v2.3.0 — Reusable workflow templates
  knowledge/                             # v2.4.0 — Governed research subsystem
  web_ingestion/                         # v2.5.0 — Controlled web ingestion gateway
  sandbox/                               # v2.6.0-v2.7.0 — Execution sandbox + kernel isolation
  workflow_composition/                  # v2.8.0 — Composite DAGs, branching, escalation
  integration/                           # v2.9.0 — Integration hardening & validators
  release/                               # v2.10.0 — Release preparation & validation
  validation/                            # v2.10.1 — Soak tests, perf baselines, fuzzing

  subagents/
    coder/                               # Advisory code analysis & patch planning
    cryer/                               # Reconnaissance & signal intelligence
    knower/                              # Knowledge, research, observation, evaluation
    pyper/                               # Execution planning & safety review

  runtime/                               # Core runtime (v1.0.0 foundation)
  orchestration/                         # Task lifecycle, packet examples
  tools/                                 # validate_packet CLI validator

  tests/                                 # 27 test suites
  examples/                              # 30+ demo scripts
  scripts/                               # 15+ check/build/release scripts
  docs/                                  # Governance, runtime, repo docs
  security/                              # Threat model, security review
  references/                            # 35+ architecture reference docs
  dist/                                  # Release archives
```

## Core Guarantees

- **Filesystem truth is authoritative.** Chat history is ephemeral; filesystem state is canonical.
- **Model output is untrusted.** Outputs must be sanitized and validated (L1-L6) before state advancement.
- **OverCR is sovereign.** Subagents never route directly to each other. All routing passes through OverCRRuntime.
- **No autonomous outbound contact.** External contact requires explicit operator approval.
- **No autonomous filesystem mutation.** CodER and PypER produce plans, not unsupervised host actions.
- **Semantic memory is advisory.** Memory informs decisions but never authorizes state mutation.
- **TUI is an observatory.** The operator interface reflects truth from disk; it never creates it.
- **Hermes-first, runtime-agnostic.** Hermes is the validated reference runtime.

## Subagents

| Subagent | Purpose | Packet Types |
|----------|---------|-------------|
| **KnowER** | Knowledge, Observation, Wisdom, Evaluation & Research | claim_review, myth_fact, research, assessment |
| **CryER** | Reconnaissance & signal intelligence | engagement_signal, recon, reputation_signal, hiring_growth |
| **CodER** | Code analysis, patch planning, diagnostics | patch_plan, diagnostic, completion, blocked |
| **PypER** | Execution planning, safety review, receipts | execution_plan, execution_receipt, execution_refusal |

PypER always operates with `approval_required=true` and `execution_authority="none"`. All PypER output routes to the operator, never to another subagent.

## Quick Start

1. Copy `overcr/` to your desired location (e.g., `$HOME/overcr`)
2. Copy skeleton contents and fill config templates:
   ```bash
   cp -r skeleton/* .
   sed -i 's|{{OVERCR_ROOT}}|/your/path/to/overcr|g' configs/*.tpl
   # Replace remaining {{PLACEHOLDER}} values, then:
   for f in configs/*.tpl; do mv "$f" "${f%.tpl}"; done
   ```
3. Run `./boot.sh` and launch Hermes with the printed command.

## Testing

```bash
cd tests && python run_all.py
```

27 test suites covering every v2.x subsystem: memory, TUI, workflows, knowledge, web ingestion, sandbox backends, integration hardening, release candidate, workflow composition, and more.

## Version History

| Version | Date | Type | Notes |
|---------|------|------|-------|
| v0.0.3–v0.0.5 | 2026-05-09/10 | Core | Clean core, subagents, orchestration |
| v0.1.0 | 2026-05-10 | Runtime | Filesystem task runtime, approval gates, audit trail |
| v0.2.0–v0.2.4 | 2026-05-10 | Workers | First live workers, routing, testing, packaging |
| v0.3.0–v0.4.3 | 2026-05-10 | KnowER | KnowER live worker, inference governance, real inference |
| v0.5.0–v0.6.0 | 2026-05-10 | CryER, CodER | CryER live inference, CodER advisory patch planning |
| v0.7.0–v0.8.0 | 2026-05-10/11 | PypER, Workflows | Execution planning, cross-worker workflow choreography |
| v0.9.0-rc1 | 2026-05-11 | RC | Threat model, security review |
| v1.0.0 | 2026-05-11 | Stable | Hermes-first portable orchestration substrate |
| v2.1.0 | 2026-05-11 | Memory | Governed semantic memory layer |
| v2.2.0 | 2026-05-11 | TUI | Terminal-first operator observatory |
| v2.3.0 | 2026-05-11 | Workflows | Template-based workflow library |
| v2.4.0 | 2026-05-11 | Knowledge | Governed research & knowledge subsystem |
| v2.5.0 | 2026-05-11 | Web Ingestion | Controlled web ingestion gateway |
| v2.6.0 | 2026-05-11 | Sandbox | Controlled execution sandbox |
| v2.7.0 | 2026-05-11 | Isolation | Kernel isolation backends (bubblewrap, firejail) |
| v2.8.0 | 2026-05-11 | Composition | Composite workflow DAGs, branching, escalation |
| v2.9.0 | 2026-05-11 | Hardening | Integration validators, replay, state consistency |
| v2.10.0 | 2026-05-16 | Stable RC | Release preparation, semantic compatibility, reproducibility |
| v2.11.0 | 2026-06-08 | Stable | Vault-grounded memory — reads Obsidian vault facts fences, injects relevant knowledge into every task context. No vector DB. No embeddings. |
| v2.11.1 | 2026-06-10 | Stable | Negative facts & next-action tracking — `kind:` prefix on bullet facts, agents stop retrying dead ends. |

## License

MIT License. See LICENSE.md.
