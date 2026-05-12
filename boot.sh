#!/usr/bin/env bash
set -euo pipefail

# OverCR HQ Cold-Start Boot Script
# Usage: ./boot.sh [hermes args]
#
# This script prepares a fresh OverCR workspace and launches Hermes.
# It does NOT carry session state between runs.
# Each boot reconstructs context from filesystem state.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

# Ensure workspace directories exist
mkdir -p prompts sessions/hq logs memory/routes/hq tasks workspace tui

# Generate compact boot prompt (idempotent)
COMPACT_BOOT="prompts/hq_compact_boot.md"

if [ ! -f "$COMPACT_BOOT" ]; then
    echo "ERROR: Missing boot prompt: $COMPACT_BOOT"
    exit 1
fi

if [ ! -f "soul.md" ]; then
    echo "ERROR: Missing soul.md - cannot boot without identity"
    exit 1
fi

echo "[OverCR HQ] Boot sequence starting..."
echo "[OverCR HQ] Workspace: $ROOT"
echo "[OverCR HQ] soul.md: present"
echo "[OverCR HQ] Boot prompt: $COMPACT_BOOT"
echo
echo "Launch Hermes with:"
echo "  hermes --continue <session-name> --system-file soul.md \"$(cat $COMPACT_BOOT)\" --tui chat"
echo
echo "Or start a fresh session:"
echo "  hermes chat --system-file soul.md -z \"$(head -1 $COMPACT_BOOT)\" --tui"
echo
echo "Replace <session-name> with your preferred Hermes session identifier."
echo "The OverCR workspace at $ROOT will be used as the working directory."