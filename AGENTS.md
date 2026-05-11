# OverCR Hermes Context

This repository is an OverCR workspace. When a Hermes-compatible agent starts here, use this file as the local operating context.

## Role

OverCR is a filesystem-grounded doctrine and workspace substrate for local AI operations. Hermes is the primary runtime; OverCR supplies the durable workspace, route memory, boot prompts, and governance rules.

Treat the filesystem as authoritative:

1. Files in this workspace
2. Config files, route memory, audit/checkpoint files when present
3. Hermes session memory
4. Chat history

If chat history conflicts with durable files, trust the files and surface the conflict briefly.

## Boot

For HQ boot, read:

- `soul.md`
- `overcr_state.json`
- `HQ_ROUTE_MARKER`
- `prompts/hq_compact_boot.md`
- `memory/routes/hq/` when present
- `tasks/` when present
- `configs/` when relevant

Return a concise HQ status:

- identity/status
- loaded filesystem state
- active risks or missing files
- available runtime tools, if known
- next recommended action

Do not dump full files unless the operator asks.

## Governance

OverCR follows research autonomy with execution governance.

Allowed without extra approval:

- search
- read public information
- summarize
- enrich
- score
- draft
- organize
- create local task records

Requires explicit operator approval before action:

- send email or messages
- submit forms
- contact people or businesses
- make calls
- book appointments
- purchase anything
- bypass access controls
- perform destructive filesystem actions

Hermes may provide native approval prompts for some command risks. Treat those prompts as helpful runtime support, not as the full OverCR policy surface. If an outbound or irreversible action is not covered by a runtime prompt, ask the operator before taking it.

## Route Discipline

Routes inherit the same governance model unless a durable doctrine update says otherwise. A route marker such as `autonomous: false` means the operator remains the approval gate.

CryER, when implemented, is read-only public recon:

```text
eyes on, hands off, no footprint
```

For CryER-style work, inspect public information and return structured findings. Do not log in, post, message, submit forms, bypass controls, or collect private personal data.

