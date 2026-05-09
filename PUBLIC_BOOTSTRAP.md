# Public Bootstrap — OverCR v0.0.3-alpha

## Cold Start

```bash
git clone <repo-url> overcr
cd overcr
export OVERCR_ROOT="$(pwd)"
bash overcr-hq-localboot.sh
```

Inside Hermes:

```text
Boot OverCR HQ from prompts/hq_compact_boot.md
```

## What Should Happen

OverCR should read `soul.md`, inspect the local workspace, and report a concise HQ status. It should treat filesystem state as authoritative and chat history as secondary.

## First Operator Check

Ask:

```text
Summarize the authority hierarchy, runtime roles, operational boundaries, and next recommended action.
```

Expected answer should include:

- Hermes as primary terminal runtime
- Open WebUI as optional secondary browser layer
- OverCR as doctrine/substrate
- files as source of truth
- no outbound or irreversible actions without approval
