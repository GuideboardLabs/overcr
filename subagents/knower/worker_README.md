# KnowER Worker — Live Worker for the OverCR Substrate

## Overview

KnowER (Knowledge, Observation, Wisdom, Evaluation & Research) is OverCR's
research and reasoning subagent. This worker provides live execution for
KnowER tasks via the standard OverCR worker contract.

## Worker Contract

| Aspect | Specification |
|--------|--------------|
| Input | JSON request packet on stdin |
| Output | JSON response packet on stdout |
| Exit code 0 | Success — stdout contains a valid response packet |
| Exit code nonzero | Failure — caller must NOT trust stdout |
| Timeout | Configurable (default 30s), subprocess killed on timeout |
| Side effects | None — workers produce analysis only, not filesystem changes |
| Network | No network access |
| Shell | No shell execution |
| Outbound | No outbound capability |

## Packet Types

### knower_research
Full research report with findings, source evaluation, and evidence gaps.

Required fields:
- `research_data.topic` — non-empty string
- `research_data.findings` — at least 1 finding
- `research_data.findings[].claim` — non-empty string
- `research_data.findings[].confidence` — integer 1-4
- `research_data.findings[].sources` — at least 1 source
- `research_data.findings[].gaps` — array (may be empty)
- `audit_trail.sources_consulted` — at least 1 source

### knower_assessment
Focused claim verification with verdict and confidence.

Required fields:
- `claim` — non-empty string (top-level)
- `assessment.confidence` — integer 1-4
- `assessment.verdict` — one of: confirmed, likely, possible, speculative, debunked
- `assessment.gaps` — array (may be empty)

### knower_myth_separation
Myth/rumor debunking report with verified facts.

Required fields:
- `topic` — non-empty string (top-level)
- `myths` — at least 1 myth
- `myths[].claim` — non-empty string
- `myths[].status` — one of: debunked, unverified, partially_supported
- `myths[].confidence` — integer 1-4

## Confidence Scale

| Level | Label | Meaning |
|-------|-------|---------|
| 4 | Confirmed | Multiple independent sources; direct evidence |
| 3 | Likely | Strong evidence from at least one reliable source |
| 2 | Possible | Some evidence; contradictions or gaps present |
| 1 | Speculative | Minimal evidence; primarily inference |

## Safety Guarantees

1. Worker output is NEVER trusted — always validated by 6-level validator
2. No outbound contact — worker produces analysis only
3. No shell execution — no subprocess calls within the worker
4. No filesystem mutation — worker reads input and writes to stdout only
5. No network access — worker does not import or use any networking modules
6. Governance override claims caught at Level 5 — any "no approval needed"
   or "authorized to bypass" language in worker output is rejected
7. L5 OUTBOUND_PATTERN catches phrases like "contact", "reach.out", "dm"
   — worker text must use "No external action needed" instead

## Invocation

```bash
cd $OVERCR_ROOT
echo '{"task_id":"task-0001","domain":"research","instruction":"Evaluate claims about X","input_context":{}}' \
  | python3 subagents/knower/worker.py
```

Or via SubagentAdapter:
```python
from runtime.subagent_adapter import SubagentAdapter
import os
adapter = SubagentAdapter(os.environ.get("OVERCR_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
result = adapter.invoke("knower", request_packet, task_id, timeout=30.0)
```

## Capability Flags

| Flag | Meaning |
|------|---------|
| `no_network` | Worker makes no network calls |
| `no_shell` | Worker executes no shell commands |
| `no_fs_write` | Worker writes nothing outside temp |
| `no_outbound` | Worker has no outbound capability |
| `readonly_analysis` | Worker produces analysis only |

### knower_claim_review
Structured claim classification with fact/inference/assumption/rumor separation.

Required fields:
- `claim_review_data.topic` — non-empty string (top-level)
- `claim_review_data.claims` — at least 1 claim object
- `claim_review_data.claims[].text` — non-empty string
- `claim_review_data.claims[].classification` — one of: fact, inference, assumption, rumor
- `claim_review_data.claims[].confidence` — integer 1-4
- `claim_review_data.claims[].source_quality` — one of: primary, secondary, tertiary, unverified
- `claim_review_data.claims[].evidence` — array (may be empty) of source references
- `claim_review_data.claims[].unknowns` — array (may be empty) of verification needs
- `claim_review_data.operator_brief` — non-empty string, operator-facing research summary

### knower_myth_fact
Simplified myth/fact classification with source quality ratings and explanations.

Required fields:
- `myth_fact_data.topic` — non-empty string (top-level)
- `myth_fact_data.items` — at least 1 item
- `myth_fact_data.items[].statement` — non-empty string
- `myth_fact_data.items[].classification` — one of: myth, fact, partial_truth, unverified
- `myth_fact_data.items[].confidence` — integer 1-4
- `myth_fact_data.items[].source_quality` — one of: primary, secondary, tertiary, unverified
- `myth_fact_data.items[].explanation` — non-empty string
- `myth_fact_data.items[].unknowns` — array (may be empty) of verification needs
- `myth_fact_data.operator_brief` — non-empty string, operator-facing research brief

## Source Quality Scale (v0.3.0)

| Level | Meaning |
|-------|---------|
| `primary` | Direct first-party evidence |
| `secondary` | Second-party reporting |
| `tertiary` | Third-party synthesis |
| `unverified` | Source quality cannot be verified |

## Domain Map (v0.3.0)

| Domain | Packet Type |
|--------|-------------|
| `research` | `knower_research` |
| `analysis` | `knower_assessment` |
| `myth_separation` (via required_packet_type) | `knower_myth_separation` |
| `claim_review` | `knower_claim_review` |
| `myth_fact` | `knower_myth_fact` |

## Version

0.3.0 — claim review and myth/fact packet types, source quality scale, operator briefs