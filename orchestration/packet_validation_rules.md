# Packet Validation Rules

## Purpose

Every subagent response packet must pass validation before OverCR routes it. Validation is shape-based — it checks that required fields exist, have correct types, and conform to value constraints. It does NOT evaluate the semantic quality or factual accuracy of the packet content.

## Validation Pipeline

`tools/validate_packet.py <packet_file>` runs the following checks in order:

### Level 1: Structural Integrity

Every packet, regardless of type, must have:

| Field | Type | Constraint |
|-------|------|------------|
| `packet_type` | string | Must match a known packet type (see Level 2) |
| `version` | string | Must be `"1.0"` |
| `timestamp` | string | Must be valid ISO 8601 |
| `source` | string | Must match a known subagent: `"cryer"`, `"pyper"`, `"coder"`, `"knower"` |
| `target` | string | Must be `"overcr"` |
| `task_id` | string | Must match pattern `task-\d{4}` |
| `summary` | string | Must be non-empty |

### Level 2: Packet Type Registration

The `packet_type` must be one of the registered types for the given `source`:

| Source | Allowed packet_types |
|--------|----------------------|
| `cryer` | `cryer_recon`, `cryer_update`, `cryer_alert` |
| `pyper` | `pyper_approval`, `pyper_revision`, `pyper_objection_response` |
| `coder` | `coder_completion`, `coder_blocked`, `coder_diagnostic` |
| `knower` | `knower_research`, `knower_assessment`, `knower_myth_separation` |

If `packet_type` does not match the registered types for `source`, validation fails.

### Level 3: Source-Packet Consistency

| Source | Must have | Must not have |
|--------|-----------|---------------|
| `cryer` | `recon_data` (for recon/update) or `alert_type` (for alert) | Fields from other subagent schemas |
| `pyper` | `draft_data` with at least one prospect, `approval_required: true` | `recon_data`, `completion_data` |
| `coder` | `completion_data` (for completion) or `blockers` (for blocked) or `diagnostics` (for diagnostic) | Fields from other subagent schemas |
| `knower` | `research_data` (for research) or `assessment` (for assessment) or `myths` (for myth_separation) | Fields from other subagent schemas |

### Level 4: Approval Gate Enforcement

| Rule | Check |
|------|-------|
| PypER packets ALWAYS have `approval_required: true` | If `source == "pyper"` and `approval_required` is missing or `false`, validation fails |
| CodER completion packets with `breaking_changes: true` should have `approval_required: true` | Warning (not failure) if missing |
| CodER completion packets with `reversible: false` should have `approval_required: true` | Warning (not failure) if missing |
| All other packets default `approval_required` to `false` if absent | No failure |

### Level 5: Forbidden Action Flags

The validator checks for these forbidden patterns in any packet:

| Forbidden Pattern | Check |
|-------------------|-------|
| Outbound contact instructions | No field value may contain strings matching `/contact|email|call|reach.out|dm|message/i` UNLESS the packet is a PypER draft (where the draft body itself is permitted to contain outreach language — but it still requires approval) |
| Direct subagent addressing | `target` must be `"overcr"`, never another subagent name |
| Governance modification | No field may instruct governance or doctrine changes |
| Self-escalation | No field may assign the subagent a new task or expand its scope |

Note: The outbound contact check is a structural sanity check, not a content filter. It catches accidental instructions to "contact the business" in non-draft packet types. PypER draft packets are exempt because their purpose is to draft outreach (which always requires operator approval).

### Level 6: Required Payload Fields by Packet Type

#### cryer_recon

| Field | Required | Type | Constraint |
|-------|----------|------|------------|
| `recon_data.targets` | yes | array | At least 1 target |
| `recon_data.targets[].entity` | yes | string | Non-empty |
| `recon_data.targets[].type` | yes | string | One of: `business`, `person`, `domain`, `directory` |
| `recon_data.targets[].signals.reputation.yield_score` | yes | integer | 0-100 |
| `recon_data.targets[].signals.reputation.confidence` | yes | integer | 0-100 |
| `recon_data.targets[].raw_sources` | yes | array | At least 1 source per target |
| `audit_trail.collection_timestamps` | yes | array | At least 1 timestamp |
| `audit_trail.methods_used` | yes | array | At least 1 method |

#### cryer_update

All `cryer_recon` requirements, plus:

| Field | Required | Type | Constraint |
|-------|----------|------|------------|
| `upstream_task_id` | yes | string | Must reference a prior task |
| `changes_summary` | yes | string | Non-empty |

#### cryer_alert

| Field | Required | Type | Constraint |
|-------|----------|------|------------|
| `alert_type` | yes | string | One of: `hiring_surge`, `reputation_drop`, `listing_change`, `major_event` |
| `severity` | yes | string | One of: `high`, `medium`, `low` |
| `entity` | yes | string | Non-empty |
| `description` | yes | string | Non-empty |
| `evidence` | yes | array | At least 1 source |
| `recommended_action` | yes | string | Non-empty |

#### pyper_approval

| Field | Required | Type | Constraint |
|-------|----------|------|------------|
| `draft_data.prospects` | yes | array | At least 1 prospect |
| `draft_data.prospects[].entity` | yes | string | Non-empty |
| `draft_data.prospects[].approach_type` | yes | string | One of: `cold_email`, `warm_intro`, `follow_up`, `proposal`, `objection_response` |
| `draft_data.prospects[].drafts` | yes | array | At least 1 draft per prospect |
| `draft_data.prospects[].drafts[].body` | yes | string | Non-empty |
| `draft_data.prospects[].drafts[].evidence_citations` | yes | array | At least 1 citation per draft |
| `approval_required` | yes | boolean | Must be `true` |
| `audit_trail.upstream_sources` | yes | array | At least 1 source task ID |

#### pyper_revision

All `pyper_approval` requirements, plus:

| Field | Required | Type | Constraint |
|-------|----------|------|------------|
| `revision_of` | yes | string | Must reference a prior task |
| `revision_reason` | yes | string | Non-empty |

#### pyper_objection_response

| Field | Required | Type | Constraint |
|-------|----------|------|------------|
| `prospect_entity` | yes | string | Non-empty |
| `objection` | yes | string | Non-empty |
| `response_draft` | yes | string | Non-empty |
| `evidence_citations` | yes | array | At least 1 citation |
| `approval_required` | yes | boolean | Must be `true` |

#### coder_completion

| Field | Required | Type | Constraint |
|-------|----------|------|------------|
| `completion_data.deliverables` | yes | array | At least 1 deliverable |
| `completion_data.deliverables[].type` | yes | string | One of: `code`, `script`, `test`, `fix`, `config`, `automation`, `documentation` |
| `completion_data.deliverables[].path` | yes | string | Non-empty |
| `completion_data.deliverables[].reversible` | yes | boolean | — |
| `audit_trail.files_modified` | yes | array | At least 1 path |
| `audit_trail.rollback_instructions` | yes | string | Non-empty |

#### coder_blocked

| Field | Required | Type | Constraint |
|-------|----------|------|------------|
| `blockers` | yes | array | At least 1 blocker |
| `blockers[].type` | yes | string | One of: `missing_dependency`, `unclear_spec`, `needs_research`, `scope_ambiguity`, `permission_denied` |
| `blockers[].description` | yes | string | Non-empty |

#### coder_diagnostic

| Field | Required | Type | Constraint |
|-------|----------|------|------------|
| `diagnostics` | yes | array | At least 1 diagnostic |
| `diagnostics[].issue` | yes | string | Non-empty |
| `diagnostics[].severity` | yes | string | One of: `critical`, `high`, `medium`, `low` |

#### knower_research

| Field | Required | Type | Constraint |
|-------|----------|------|------------|
| `research_data.topic` | yes | string | Non-empty |
| `research_data.findings` | yes | array | At least 1 finding |
| `research_data.findings[].claim` | yes | string | Non-empty |
| `research_data.findings[].confidence` | yes | integer | 1, 2, 3, or 4 |
| `research_data.findings[].sources` | yes | array | At least 1 source per finding |
| `research_data.findings[].gaps` | yes | array | May be empty, but field must exist |
| `audit_trail.sources_consulted` | yes | array | At least 1 source |

#### knower_assessment

| Field | Required | Type | Constraint |
|-------|----------|------|------------|
| `claim` | yes | string | Non-empty |
| `assessment.confidence` | yes | integer | 1, 2, 3, or 4 |
| `assessment.verdict` | yes | string | One of: `confirmed`, `likely`, `possible`, `speculative`, `debunked` |
| `assessment.gaps` | yes | array | May be empty, but field must exist |

#### knower_myth_separation

| Field | Required | Type | Constraint |
|-------|----------|------|------------|
| `topic` | yes | string | Non-empty |
| `myths` | yes | array | At least 1 myth |
| `myths[].claim` | yes | string | Non-empty |
| `myths[].status` | yes | string | One of: `debunked`, `unverified`, `partially_supported` |
| `myths[].confidence` | yes | integer | 1, 2, 3, or 4 |

## Validation Output Format

The validator produces a JSON report:

```json
{
  "valid": true,
  "packet_type": "cryer_recon",
  "source": "cryer",
  "task_id": "task-0001",
  "timestamp": "ISO8601 of validation run",
  "errors": [],
  "warnings": []
}
```

On failure:

```json
{
  "valid": false,
  "packet_type": "cryer_recon",
  "source": "cryer",
  "task_id": "task-0001",
  "timestamp": "ISO8601 of validation run",
  "errors": [
    "Level 1: missing required field 'summary'",
    "Level 4: PypER packet must have approval_required=true"
  ],
  "warnings": [
    "Level 4: CodER packet with breaking_changes=true should have approval_required=true"
  ]
}
```

Errors cause validation failure. Warnings are advisory and do not cause failure.

## Version

These validation rules are for packet schema version `1.0`. If `version` in a packet is not `"1.0"`, validation fails at Level 1.