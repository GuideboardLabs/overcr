#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

# Environment-driven paths
export OVERCR_ROOT="${OVERCR_ROOT:-$ROOT}"
export HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
export OVERCR_INSTANCE_ID="${OVERCR_INSTANCE_ID:-overcr-hq-$(date +%Y%m%d_%H%M%S)}"
export OVERCR_RELEASE_ARCHIVE="${OVERCR_RELEASE_ARCHIVE:-${OVERCR_ROOT}/../releases}"
export OVERCR_CAG_MEMORY="${OVERCR_CAG_MEMORY:-}"
export OVERCR_MODEL="${OVERCR_MODEL:-}"
export OVERCR_PROVIDER="${OVERCR_PROVIDER:-}"

mkdir -p prompts sessions/hq logs memory/routes/hq configs tasks workspace tui

COMPACT_BOOT="prompts/hq_compact_boot.md"

cat > "$COMPACT_BOOT" <<'PROMPT'
Boot OverCR HQ.

Read soul.md first.

Reconstruct operational context from filesystem state, not chat history.

Inspect:
- overcr_state.json if present
- memory/routes/hq/
- memory/warm/
- tasks/
- knowledge/
- checkpoints/
- release manifests

Return concise HQ status:
- identity/status
- loaded memory/state
- active risks
- available runtime tools
- next recommended action

Do not dump full files.
Do not expand architecture.
Use filesystem truth as authoritative.
PROMPT

echo "[OverCR HQ] Boot file ready: $COMPACT_BOOT"
echo "[OverCR HQ] OverCR_ROOT=$OVERCR_ROOT"
echo "[OverCR HQ] OVERCR_INSTANCE_ID=$OVERCR_INSTANCE_ID"
echo "[OverCR HQ] Optional preflight: bash overcr-hermes-preflight.sh"
echo
echo "First message inside Hermes:"
echo "Boot OverCR HQ from prompts/hq_compact_boot.md"
echo

# Launch Hermes if available, otherwise print instructions
if command -v hermes &>/dev/null; then
    hermes --tui chat
else
    echo "[OverCR HQ] hermes CLI not found. Run manually from your Hermes session."
fi
