# KnowER v0.3.0 Reference

## Version

**0.3.0** — Claim review and myth/fact classification as first-class live worker packet types.

## Summary of Changes

KnowER is promoted to a first-class live research reasoning worker. Two new packet
types are added alongside the existing three, expanding KnowER's capability from
general research/assessment/myth_separation to structured claim classification and
simplified myth/fact separation with source quality ratings and operator-facing
research briefs.

### New Packet Types

#### knower_claim_review (domain: `claim_review`)

Structured claim classification separating facts from inferences, assumptions, and
rumors. Each claim gets a confidence rating (1-4), source quality rating
(primary/secondary/tertiary/unverified), evidence citations, and explicit unknowns
with verification needs. Includes an operator-facing research brief.

**Required fields (L3):**
- `claim_review_data` — top-level payload container

**Required fields (L6):**
- `claim_review_data.topic` — non-empty string
- `claim_review_data.claims` — array of at least 1 claim object
  - `claim.text` — non-empty string
  - `claim.classification` — one of: `fact`, `inference`, `assumption`, `rumor`
  - `claim.confidence` — integer 1-4
  - `claim.source_quality` — one of: `primary`, `secondary`, `tertiary`, `unverified`
  - `claim.evidence` — array (may be empty) of source references
  - `claim.unknowns` — array (may be empty) of verification needs
- `claim_review_data.operator_brief` — non-empty string

**Routing:** `("knower", "knower_claim_review")` → operator (always requires judgment)

#### knower_myth_fact (domain: `myth_fact`)

Simplified myth/fact classification with source quality ratings and explanations.
Each statement is classified as myth, fact, partial truth, or unverified. Includes
an operator-facing research brief.

**Required fields (L3):**
- `myth_fact_data` — top-level payload container

**Required fields (L6):**
- `myth_fact_data.topic` — non-empty string
- `myth_fact_data.items` — array of at least 1 item
  - `item.statement` — non-empty string
  - `item.classification` — one of: `myth`, `fact`, `partial_truth`, `unverified`
  - `item.confidence` — integer 1-4
  - `item.source_quality` — one of: `primary`, `secondary`, `tertiary`, `unverified`
  - `item.explanation` — non-empty string
  - `item.unknowns` — array (may be empty) of verification needs
- `myth_fact_data.operator_brief` — non-empty string

**Routing:** `("knower", "knower_myth_fact")` → operator (always requires review)

### Source Quality Scale (New)

| Level | Meaning |
|-------|---------|
| `primary` | Direct first-party evidence |
| `secondary` | Second-party reporting |
| `tertiary` | Third-party synthesis |
| `unverified` | Source quality cannot be verified |

### Domain Map (v0.3.0)

| Domain | Packet Type |
|--------|-------------|
| `research` | `knower_research` |
| `analysis` | `knower_assessment` |
| `myth_separation` | `knower_myth_separation` (required_packet_type override) |
| **`claim_review`** | **`knower_claim_review`** |
| **`myth_fact`** | **`knower_myth_fact`** |

### Updated Files

| File | Change |
|------|--------|
| `subagents/knower/worker.py` | Added `build_claim_review_packet()` and `build_myth_fact_packet()`; updated domain routing and main() |
| `subagents/knower/worker_README.md` | Added documentation for new packet types |
| `subagents/knower/agent_runtime.md` | New: full runtime specification |
| `subagents/knower/examples/claim_review_response.json` | New: example claim_review packet |
| `subagents/knower/examples/myth_fact_response.json` | New: example myth_fact packet |
| `runtime/__init__.py` | Version bump to 0.3.0 |
| `runtime/task_store.py` | Added `claim_review` and `myth_fact` to DOMAIN_SUBAGENT_MAP; added packet types to SUBAGENT_PACKET_TYPES |
| `runtime/subagent_adapter.py` | Added `claim_review` and `myth_fact` to LIVE_WORKER_DOMAINS; added routing entries |
| `runtime/worker_capabilities.py` | Added packet types to EXPECTED_PACKET_TYPES for knower |
| `tools/validate_packet.py` | Added L2, L3, L6 validators for new packet types |
| `examples/runtime_demo_knower_claim_review.py` | New: full runtime demo |
| `examples/runtime_demo_knower_myth_fact.py` | New: full runtime demo |
| `tests/test_knower_claim_review.py` | New: verification test suite |
| `tests/test_knower_myth_fact.py` | New: verification test suite |
| `tests/test_manifest.json` | Added new test entries |
| `references/knower-v0.3.0.md` | New: this reference document |

### Unchanged (Preserved)

- KnowER's three original packet types (research, assessment, myth_separation) are unchanged
- KnowER's capability flags are unchanged
- KnowER's safety guarantees are unchanged (no outbound, no shell, no fs write)
- Worker contract is unchanged (stdin JSON → stdout JSON, exit 0/1)
- All existing tests remain valid and pass
- No changes to CryER, PypER, or CodER

### Design Rationale

1. **claim_review vs assessment**: `knower_assessment` evaluates a single claim with a
   verdict (confirmed/likely/possible/speculative/debunked). `knower_claim_review`
   classifies multiple claims into orthogonal categories (fact/inference/assumption/rumor)
   and adds source quality ratings, unknowns, and operator briefs. Different use cases.

2. **myth_fact vs myth_separation**: `knower_myth_separation` groups myths under a
   topic with debunking status. `knower_myth_fact` is a flatter, more operator-friendly
   classification that labels individual statements and provides explanations. Both are
   valid; myth_fact is simpler for quick triage.

3. **operator_brief field**: Required on both new types. Forces KnowER to produce a
   human-readable actionable summary, not just structured data. This is critical for
   substrate → operator handoff.

4. **source_quality scale**: A new 4-level scale (primary/secondary/tertiary/unverified)
   that explicitly rates source reliability from provided input only. KnowER never
   accesses external sources — this rating reflects the worker's assessment of the
   input data provenance.

5. **No network, no crawling, no outbound contact**: KnowER operates strictly on
   provided input text/snippets. All analysis derives from the input context. This
   is a hard constraint enforced at the worker level and validated at Level 5.

## Compatibility

- v0.3.0 is backward compatible with v0.2.1 tests and packet types
- All existing v0.2.1 tests must continue to pass
- New packet types are additive — no breaking changes
- Worker version string updated to "0.3.0"