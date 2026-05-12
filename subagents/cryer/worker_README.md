# CryER Worker — Crawling Reputation, Yield, Engagement & Recon

## Overview

CryER is OverCR's public-signal reconnaissance subagent. As of v0.4.0, CryER is
a **first-class live worker** that analyzes provided text snippets, URLs, review
text, directory text, hiring snippets, and social/profile excerpts.

**CryER operates strictly on provided input text.** It makes no network requests,
no outbound contact, no browser automation, and no live crawling.

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

## Packet Types (v0.4.0)

| Domain | Packet Type | Purpose |
|--------|-------------|---------|
| `recon` | `cryer_recon` | Public signal reconnaissance with yield scoring |
| `reputation_signal` | `cryer_reputation_signal` | Focused reputation signal summary |
| `engagement_signal` | `cryer_engagement_signal` | Engagement signal summary (reviews, ratings, activity) |
| `booking_friction` | `cryer_booking_friction` | Booking friction detection |
| `directory_completeness` | `cryer_directory_completeness` | Directory listing completeness assessment |
| `hiring_growth` | `cryer_hiring_growth` | Hiring/growth signal detection |

## Usage

```bash
# Invoke directly via stdin/stdout
echo '{"task_id":"task-0001","domain":"reputation_signal","instruction":"Analyze reputation","input_context":{"entity":"Example Corp","snippets":["Rated 4.2 stars"]}}' | python3 subagents/cryer/worker.py

# Via OverCR runtime (automated invocation)
# The runtime creates the task, invokes the worker, validates, and routes.
```

## Signal Classification

All CryER output uses one of four epistemic categories:

| Category | Meaning | Marker |
|----------|---------|--------|
| **Observed** | Directly present in provided input text | `classification: "observed"` |
| **Inferred** | Reasonable conclusion from observed signals | `classification: "inferred"` |
| **Assumed** | Plausible but unsupported by direct evidence | `classification: "assumed"` |
| **Unknown** | Cannot determine from available input | `classification: "unknown"` |

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
5. Source snippets treated as untrusted input — never invent source details
6. Private/personal data detection — worker must refuse to extract or store PII
7. All recommended routing targets OverCR only — never another subagent directly

## Version

0.4.0 — CryER first-class live worker: 6 packet types, public-signal reconnaissance only