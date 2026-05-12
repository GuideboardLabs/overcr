# KnowER Agent Runtime Specification — v0.3.0

## Overview

KnowER (Knowledge, Observation, Wisdom, Evaluation & Research) is OverCR's
research reasoning subagent. As of v0.3.0, KnowER is promoted to a **first-class
live worker** with enhanced packet types for structured research reasoning over
provided inputs.

KnowER operates **strictly on provided input text/snippets**. It makes no
network requests, no outbound contact, no crawling, and no database lookups.
All analysis derives from the input context supplied by OverCR.

## Packet Types (v0.3.0)

| Packet Type | Domain Trigger | Purpose |
|-------------|---------------|---------|
| `knower_research` | `research` | Full research report with findings, source evaluation, evidence gaps |
| `knower_assessment` | `analysis` | Focused claim verification with verdict and confidence |
| `knower_myth_separation` | `required_packet_type` override | Myth/rumor debunking with verified facts |
| **`knower_claim_review`** | `claim_review` | Structured claim classification with fact/inference/assumption/rumor separation |
| **`knower_myth_fact`** | `myth_fact` | Simplified myth-vs-fact classification with source quality rating |

New in v0.3.0 are marked in **bold**.

## New Packet Details

### knower_claim_review

Triggered by domain `claim_review`. Produces a structured claim classification
that separates factual claims from inferences, assumptions, and rumors. Each
claim gets a confidence rating, source quality rating, and explicit unknowns.

**Required fields:**

- `claim_review_data.topic` — non-empty string, the topic under review
- `claim_review_data.claims` — array of at least 1 claim object
  - `claim.text` — non-empty string, the claim statement
  - `claim.classification` — one of: `fact`, `inference`, `assumption`, `rumor`
  - `claim.confidence` — integer 1-4
  - `claim.source_quality` — one of: `primary`, `secondary`, `tertiary`, `unverified`
  - `claim.evidence` — array (may be empty) of source references
  - `claim.unknowns` — array (may be empty) of verification needs
- `claim_review_data.operator_brief` — non-empty string, operator-facing research summary

**Routing:** `("knower", "knower_claim_review")` → `[{"target": "operator", "condition": "claim review requires operator judgment"}]`

### knower_myth_fact

Triggered by domain `myth_fact`. Produces a simplified myth-vs-fact
classification with source quality ratings and explicit unknowns. Optimized
for operator-facing research briefs.

**Required fields:**

- `myth_fact_data.topic` — non-empty string, the topic under review
- `myth_fact_data.items` — array of at least 1 item
  - `item.statement` — non-empty string, the claim being classified
  - `item.classification` — one of: `myth`, `fact`, `partial_truth`, `unverified`
  - `item.confidence` — integer 1-4
  - `item.source_quality` — one of: `primary`, `secondary`, `tertiary`, `unverified`
  - `item.explanation` — non-empty string, why this classification was chosen
  - `item.unknowns` — array (may be empty) of verification needs
- `myth_fact_data.operator_brief` — non-empty string, operator-facing research brief

**Routing:** `("knower", "knower_myth_fact")` → `[{"target": "operator", "condition": "myth/fact classification always requires operator review"}]`

## Confidence Scale (Unchanged)

| Level | Label | Meaning |
|-------|-------|---------|
| 4 | Confirmed | Multiple independent sources; direct evidence |
| 3 | Likely | Strong evidence from at least one reliable source |
| 2 | Possible | Some evidence; contradictions or gaps present |
| 1 | Speculative | Minimal evidence; primarily inference |

## Source Quality Scale (New in v0.3.0)

| Level | Meaning |
|-------|---------|
| `primary` | Direct first-party evidence (original documents, official records) |
| `secondary` | Second-party reporting (news articles, review aggregators) |
| `tertiary` | Third-party synthesis (encyclopedias, secondary analysis) |
| `unverified` | Source quality cannot be verified from provided input |

## Domain Map (v0.3.0)

| Domain | Packet Type |
|--------|-------------|
| `research` | `knower_research` |
| `analysis` | `knower_assessment` |
| `myth_separation` | `knower_myth_separation` (via required_packet_type override) |
| `claim_review` | `knower_claim_review` |
| `myth_fact` | `knower_myth_fact` |

## Worker Contract (Unchanged)

| Aspect | Specification |
|--------|--------------|
| Input | JSON request packet on stdin |
| Output | JSON response packet on stdout |
| Exit 0 | Success — stdout contains valid response packet |
| Exit nonzero | Failure — caller must NOT trust stdout |
| Timeout | Configurable (default 30s), subprocess killed on timeout |
| Side effects | None — analysis only |
| Network | No network access |
| Shell | No shell execution |
| Outbound | No outbound capability |

## Capability Flags (Unchanged)

| Flag | Meaning |
|------|---------|
| `no_network` | Worker makes no network calls |
| `no_shell` | Worker executes no shell commands |
| `no_fs_write` | Worker writes nothing outside temp |
| `no_outbound` | Worker has no outbound capability |
| `readonly_analysis` | Worker produces analysis only |

## Safety Guarantees (Unchanged)

1. Worker output is NEVER trusted — always validated by 6-level validator
2. No outbound contact — worker produces analysis only
3. No shell execution, no filesystem mutation, no network access
4. Governance override claims caught at Level 5
5. L5 OUTBOUND_PATTERN catches "contact", "reach.out", "dm" — use "No external action needed" instead

## Version

0.3.0 — claim_review and myth_fact packet types, source quality scale, operator briefs