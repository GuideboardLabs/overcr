# OverCR Semantic Memory Layer — v2.1.0

## What This Is

A **governed semantic memory layer** for the OverCR substrate that provides
advisory context to operational decisions — without compromising the
filesystem-first canonical state model.

## Core Invariant

> **Semantic memory INFORMS but does NOT AUTHOR.**
> Canonical filesystem state remains the authoritative truth.
> Memory cannot directly mutate operational state.
> Memory cannot override task truth.

## Architecture

```
memory/
├── README.md                        ← You are here
├── __init__.py                       ← Package init
├── memory_record.py                  ← Data model + validation
├── memory_manager.py                 ← Filesystem CRUD (create/load/search/list)
├── memory_promoter.py                ← Governed promotion from artifacts
├── memory_retriever.py               ← Keyword/tag retrieval + deterministic fallback
├── memory_conflict.py                ← Contradiction detection (review artifacts only)
├── schema/
│   └── memory_record.schema.json    ← JSON Schema for memory records
└── (runtime)
    ├── records/
    │   └── mem-XXXXXXXX.json         ← One file per memory record
    ├── conflicts/
    │   └── conflict-XXXXXXXX.json    ← Review artifacts (never auto-resolved)
    └── index.jsonl                   ← Append-only audit index
```

## Memory Record Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `memory_id` | string | yes | Unique ID: `mem-` + 8 hex chars |
| `source` | string | yes | Origin: operator, subagent, or rule ID |
| `created_at` | ISO 8601 | yes | Creation timestamp |
| `updated_at` | ISO 8601 | yes | Last status change timestamp |
| `confidence` | float | yes | 0.0–1.0, set by provenance rule |
| `provenance` | object | yes | `{type, rule, operator_id?, task_id?, artifact_path?}` |
| `tags` | string[] | yes | ≥1 searchable tag |
| `project_scope` | string | yes | Project/domain for scoped retrieval |
| `semantic_summary` | string | yes | Human-readable summary (1–4096 chars) |
| `supporting_artifacts` | object[] | no | `[{path, description}]` |
| `canonical_state_refs` | object[] | no | `[{path, field, as_of?}]` |
| `contradiction_refs` | object[] | no | `[{conflicting_memory_id, conflict_type, detected_at?, note?}]` |
| `status` | enum | yes | `active` `stale` `rejected` `superseded` |
| `superseded_by` | string? | no | Set when status=`superseded` |
| `stale_reason` | string? | no | Set when status=`stale` |

## Status Lifecycle

```
  active ──→ stale ──→ active  (refresh)
    │          │
    │          └──→ superseded
    │          │
    │          └──→ rejected    ← TERMINAL
    │
    └──→ superseded           ← TERMINAL
    │
    └──→ rejected             ← TERMINAL
```

- **Rejected memories are never deleted.** They remain on disk.
- **Stale memories are recoverable.** They can be refreshed back to `active`.
- **Superseded memories** point to their replacement via `superseded_by`.

## Promotion Rules

Promotion is rule-gated. No autonomous promotion from arbitrary model output.

| Rule | Source | Confidence | Description |
|------|--------|------------|-------------|
| `task_completion_insight` | subagent_output | 0.7 | Insights from completed tasks |
| `operator_observation` | operator_direct | 0.9 | Direct operator observations |
| `filesystem_artifact_promotion` | filesystem_artifact | 0.6 | Observations from filesystem artifacts |
| `validation_lesson` | promotion_rule | 0.8 | Lessons from L1–L6 validation failures |

Governance gates on promotion:
1. Rule must exist in `PROMOTION_RULES`
2. Confidence cannot exceed rule ceiling
3. `operator_direct` requires explicit `operator_id`

## Retrieval Fallback Cascade

```
1. tags + project + status=active  → exact
2. any tag + project + active      → relaxed
3. project + active                → scope-only
4. project + any status            → broad
5. text_query across all           → last resort
6. all active                      → widest
```

Every retrieval includes `canonical_state_refs` — the consumer MUST verify
against actual filesystem state before acting on semantic memory.

## Conflict Detection

- Detects: factual contradictions, temporal contradictions, scope overlaps
- Creates: review artifacts in `conflicts/` directory
- Creates: bidirectional `contradiction_refs` on both records
- **Does NOT auto-resolve.** Operators review and decide.

## What This Is NOT

- Not a vector DB or embedding store (v2.2+ may add optional embedding)
- Not a RAG pipeline (v2.2+ may add retrieval augmentation)
- Not autonomous — no self-modifying prompts or learning loops
- Not authoritative — filesystem state is always canonical
- Not cloud-dependent — fully local, markdown/JSON friendly