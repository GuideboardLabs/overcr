# OverCR Installation Guide

**Version:** v0.0.3-alpha  
**Primary runtime:** Hermes terminal  
**Secondary runtime:** Open WebUI browser layer, optional

## Requirements

- Linux, macOS, or WSL2
- Hermes Agent installed and configured
- A model backend available through Hermes
- Bash
- Optional: Python 3.8+ for future tooling

OverCR does not include a model. Use a local, cloud, or hybrid provider.

## 1. Get OverCR

```bash
git clone <repo-url> overcr
cd overcr
export OVERCR_ROOT="$(pwd)"
```

For a ZIP release:

```bash
unzip overcr-clean-core-v0.0.3-alpha.zip
cd overcr
export OVERCR_ROOT="$(pwd)"
```

## 2. Configure Hermes

Install and configure Hermes using its own documentation. Then verify it can start:

```bash
hermes --tui chat
```

Configure any model provider you prefer. OverCR is provider-agnostic.

Examples:

```bash
# Example only. Use the provider/model names available in your Hermes setup.
hermes config set provider ollama
hermes config set model qwen3-coder
```

For cloud providers, keep API keys outside this repository. Use shell environment variables, your OS secret store, or Hermes configuration. Never commit keys.

## 3. Boot OverCR HQ

```bash
cd "$OVERCR_ROOT"
bash overcr-hq-localboot.sh
```

The script creates expected directories, prepares the compact HQ boot prompt, and starts Hermes if available.

Inside Hermes, send:

```text
Boot OverCR HQ from prompts/hq_compact_boot.md
```

## 4. Verify the Workspace

```bash
bash HQ_BOOT_VERIFICATION.sh
```

The verification script checks for the core files, route marker, config files, and release-archive separation.

## 5. Optional Open WebUI Layer

Open WebUI is optional. Use it as a visual review or command-room layer, not as the source of truth.

Important rules:

- Open WebUI does not automatically share state with Hermes.
- To keep continuity, point it at the same OverCR workspace or use an explicit sync/export flow.
- Hermes remains the primary supported path.
- The filesystem remains authoritative.

## 6. Add Routes Later

HQ is the first route. Additional routes can be added under:

```text
memory/routes/<route-name>/
```

Route examples might include `research`, `codeworker`, or `cryer`. Routes inherit the same governance model unless explicitly changed through a documented doctrine update.

## 7. Governance Boundary

OverCR may research, summarize, score, draft, and organize. It may not contact anyone or perform irreversible actions without explicit human approval.

This applies across Hermes, Open WebUI, future routes, and future subagents.

## 8. Freezing a Release

```bash
mkdir -p "${OVERCR_RELEASE_ARCHIVE:-$OVERCR_ROOT/../releases}"
STAMP="$(date +%Y%m%d_%H%M%S)"
tar --exclude='.git' --exclude='sessions' --exclude='logs' --exclude='tmp' --exclude='cache' --exclude='checkpoints' \
  -czf "${OVERCR_RELEASE_ARCHIVE:-$OVERCR_ROOT/../releases}/overcr-clean-core-$STAMP.tar.gz" \
  -C "$(dirname "$OVERCR_ROOT")" "$(basename "$OVERCR_ROOT")"
sha256sum "${OVERCR_RELEASE_ARCHIVE:-$OVERCR_ROOT/../releases}/overcr-clean-core-$STAMP.tar.gz" \
  > "${OVERCR_RELEASE_ARCHIVE:-$OVERCR_ROOT/../releases}/overcr-clean-core-$STAMP.sha256"
```

## Troubleshooting

If Hermes opens but OverCR seems contextless, send the boot prompt again:

```text
Boot OverCR HQ from prompts/hq_compact_boot.md. Read soul.md first. Use filesystem state as authoritative.
```

If state seems wrong, inspect `overcr_state.json`, `configs/`, and `memory/routes/` before trusting chat history.
