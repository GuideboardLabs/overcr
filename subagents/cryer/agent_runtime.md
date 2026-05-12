# CryER Agent Runtime Specification — v0.4.0

## Overview

CryER (Crawling Reputation, Yield, Engagement & Recon) is OverCR's public-signal
reconnaissance subagent. As of v0.4.0, CryER is promoted to a **first-class live
worker** for analyzing provided public snippets, URLs, review text, directory text,
hiring snippets, and social/profile excerpts.

CryER operates **strictly on provided input text/snippets**. It makes no
network requests, no outbound contact, no browser automation, no login/authenticated
access, no form submission, and no live crawling. All analysis derives from the
input context supplied by OverCR.

## Packet Types (v0.4.0)

| Packet Type | Domain Trigger | Purpose |
|-------------|---------------|---------|
| `cryer_recon` | `recon` | Public signal reconnaissance with yield scoring |
| `cryer_reputation_signal` | `reputation_signal` | Focused reputation signal summary |
| `cryer_engagement_signal` | `engagement_signal` | Engagement signal summary (reviews, ratings, activity) |
| `cryer_booking_friction` | `booking_friction` | Booking friction detection (scheduling, availability, UX barriers) |
| `cryer_directory_completeness` | `directory_completeness` | Directory listing completeness assessment |
| `cryer_hiring_growth` | `hiring_growth` | Hiring/growth signal detection |

New in v0.4.0 are marked in **bold** (all packet types are new live worker types;
`cryer_recon` existed as a simulated type, now promoted to live worker with expanded
payload, and 5 new packet types added).

## CryER Scope and Boundaries

### What CryER Does
- Analyzes provided public snippets for reputation signals
- Scores yield (0-100) based on observable public indicators
- Detects booking/scheduling friction patterns in provided text
- Identifies hiring/growth signals from provided job listings or announcements
- Assesses directory listing completeness from provided directory text
- Summarizes engagement patterns from provided review/rating text
- Produces confidence ratings and explicit unknowns
- Routes all output to OverCR for downstream handling

### What CryER Does NOT Do
- Live web crawling or browsing
- Browser automation or rendering
- Login/authenticated access to any service
- Outbound contact of any kind (email, phone, DM, form submission)
- Form submission or booking attempts
- Provider/runtime replacement (Hermes is the reference runtime)
- Direct handoff to another subagent (all output targets OverCR)

### Signal Classification

CryER distinguishes four epistemic categories in all output:

| Category | Meaning | Marker |
|----------|---------|--------|
| **Observed** | Directly present in provided input text | `classification: "observed"` |
| **Inferred** | Reasonable conclusion from observed signals | `classification: "inferred"` |
| **Assumed** | Plausible but unsupported by direct evidence | `classification: "assumed"` |
| **Unknown** | Cannot determine from available input | `classification: "unknown"` |

## New Packet Details

### cryer_reputation_signal

Triggered by domain `reputation_signal`. Produces a structured reputation
signal summary from provided review text, directory listings, or social snippets.

**Required fields:**

- `reputation_signal_data.entity` — non-empty string, the entity under review
- `reputation_signal_data.signals` — array of at least 1 signal object
  - `signal.type` — one of: `rating`, `review_volume`, `sentiment`, `accreditation`, `mention_frequency`, `complaint_pattern`
  - `signal.classification` — one of: `observed`, `inferred`, `assumed`, `unknown`
  - `signal.confidence` — integer 0-100
  - `signal.detail` — non-empty string describing the signal
  - `signal.source_quality` — one of: `primary`, `secondary`, `tertiary`, `unverified`
  - `signal.unknowns` — array (may be empty) of verification needs
- `reputation_signal_data.yield_score` — integer 0-100
- `reputation_signal_data.confidence_notes` — non-empty string explaining confidence and caveats
- `reputation_signal_data.recommended_routing` — one of: `overcr`

**Routing:** `("cryer", "cryer_reputation_signal")` → `[{target: "operator", condition: "reputation signals require operator review"}]`

### cryer_engagement_signal

Triggered by domain `engagement_signal`. Produces an engagement signal summary
from provided review text, rating data, or social metrics.

**Required fields:**

- `engagement_signal_data.entity` — non-empty string
- `engagement_signal_data.metrics` — array of at least 1 metric object
  - `metric.type` — one of: `review_count`, `average_rating`, `response_rate`, `recency`, `platform_presence`
  - `metric.classification` — one of: `observed`, `inferred`, `assumed`, `unknown`
  - `metric.value` — string representation of the metric value
  - `metric.confidence` — integer 0-100
  - `metric.source_quality` — one of: `primary`, `secondary`, `tertiary`, `unverified`
  - `metric.unknowns` — array (may be empty)
- `engagement_signal_data.engagement_summary` — non-empty string
- `engagement_signal_data.recommended_routing` — one of: `overcr`

**Routing:** `("cryer", "cryer_engagement_signal")` → `[{target: "operator", condition: "engagement signals require operator review"}]`

### cryer_booking_friction

Triggered by domain `booking_friction`. Detects booking/scheduling friction
patterns from provided text snippets (website copy, booking page descriptions,
hours of operation, etc.).

**Required fields:**

- `booking_friction_data.entity` — non-empty string
- `booking_friction_data.friction_points` — array of at least 1 friction point
  - `friction.type` — one of: `limited_hours`, `no_online_booking`, `complex_scheduling`, `high_cancellation_penalty`, `opaque_pricing`, `contact_required`, `poor_availability_info`, `ux_barrier`
  - `friction.classification` — one of: `observed`, `inferred`, `assumed`, `unknown`
  - `friction.confidence` — integer 0-100
  - `friction.detail` — non-empty string describing the friction
  - `friction.source_quality` — one of: `primary`, `secondary`, `tertiary`, `unverified`
  - `friction.unknowns` — array (may be empty)
- `booking_friction_data.friction_summary` — non-empty string summarizing findings
- `booking_friction_data.recommended_routing` — one of: `overcr`

**Routing:** `("cryer", "cryer_booking_friction")` → `[{target: "operator", condition: "booking friction requires operator review"}]`

### cryer_directory_completeness

Triggered by domain `directory_completeness`. Assesses the completeness of
a directory listing from provided directory text.

**Required fields:**

- `directory_completeness_data.entity` — non-empty string
- `directory_completeness_data.present_fields` — array of strings (fields found in input)
- `directory_completeness_data.missing_fields` — array of strings (expected fields absent)
- `directory_completeness_data.completeness_score` — integer 0-100
- `directory_completeness_data.classification` — one of: `observed`, `inferred`, `assumed`, `unknown`
- `directory_completeness_data.confidence` — integer 0-100
- `directory_completeness_data.recommended_routing` — one of: `overcr`
- `directory_completeness_data.source_quality` — one of: `primary`, `secondary`, `tertiary`, `unverified`
- `directory_completeness_data.unknowns` — array (may be empty)

**Routing:** `("cryer", "cryer_directory_completeness")` → `[{target: "operator", condition: "directory assessment requires operator review"}]`

### cryer_hiring_growth

Triggered by domain `hiring_growth`. Detects hiring/growth signals from
provided job listings, career pages, or announcements.

**Required fields:**

- `hiring_growth_data.entity` — non-empty string
- `hiring_growth_data.signals` — array of at least 1 signal
  - `signal.type` — one of: `job_posting`, `growth_indication`, `expansion_signal`, `hiring_surge`, `department_opening`, `role_specific`
  - `signal.classification` — one of: `observed`, `inferred`, `assumed`, `unknown`
  - `signal.confidence` — integer 0-100
  - `signal.detail` — non-empty string
  - `signal.source_quality` — one of: `primary`, `secondary`, `tertiary`, `unverified`
  - `signal.unknowns` — array (may be empty)
- `hiring_growth_data.growth_summary` — non-empty string
- `hiring_growth_data.recommended_routing` — one of: `overcr`

**Routing:** `("cryer", "cryer_hiring_growth")` → `[{target: "operator", condition: "hiring signals require operator review"}]`

## Confidence Scale

| Level | Meaning |
|-------|---------|
| 80-100 | Strong observed signal — directly present in provided input |
| 60-79 | Likely signal — reasonable inference from multiple indicators |
| 40-59 | Possible signal — some evidence but gaps present |
| 20-39 | Speculative — minimal evidence, primarily inference |
| 0-19 | Unknown — cannot determine from available input |

## Source Quality Scale

| Level | Meaning |
|-------|---------|
| `primary` | Direct first-party source (original document, official listing) |
| `secondary` | Second-party reporting (review aggregator, directory mirror) |
| `tertiary` | Third-party synthesis (blog summary, social reshare) |
| `unverified` | Source quality cannot be verified from provided input |

## Domain Map (v0.4.0)

| Domain | Packet Type |
|--------|-------------|
| `recon` | `cryer_recon` |
| `reputation_signal` | `cryer_reputation_signal` |
| `engagement_signal` | `cryer_engagement_signal` |
| `booking_friction` | `cryer_booking_friction` |
| `directory_completeness` | `cryer_directory_completeness` |
| `hiring_growth` | `cryer_hiring_growth` |

## Worker Contract

| Aspect | Specification |
|--------|---------------|
| Input | JSON request packet on stdin |
| Output | JSON response packet on stdout |
| Exit code 0 | Success — stdout contains a valid response packet |
| Exit code nonzero | Failure — caller must NOT trust stdout |
| Timeout | Configurable (default 30s), subprocess killed on timeout |
| Side effects | None — analysis only |
| Network | No network access |
| Shell | No shell execution |
| Outbound | No outbound capability |

## Capability Flags

| Flag | Meaning |
|------|---------|
| `no_network` | Worker makes no network calls |
| `no_shell` | Worker executes no shell commands |
| `no_fs_write` | Worker writes nothing outside temp |
| `no_outbound` | Worker has no outbound capability |
| `readonly_analysis` | Worker produces analysis only |

## Safety Guarantees

1. Worker output is NEVER trusted — always validated by 6-level validator
2. No outbound contact — worker produces analysis only
3. No shell execution, no filesystem mutation, no network access
4. Governance override claims caught at Level 5
5. L5 OUTBOUND_PATTERN catches "contact", "reach.out", "dm" — use "No external action needed" instead
6. Source snippets treated as untrusted input — never invent source details
7. Private/personal data detection — worker must refuse to extract or store PII
8. All recommended routing targets OverCR only — never another subagent directly

## Anti-Contamination Rules

- No business-specific hardcoding (no city names, company names, market references)
- No local-market contamination (no geographic assumptions)
- Source snippets are untrusted input — distinguish observed, inferred, assumed, unknown
- Contact recommendations are NEVER framed as executable actions
- Outreach next steps must route to OverCR and require approval

## Version

0.4.0 — CryER first-class live worker: 6 packet types, public-signal reconnaissance only