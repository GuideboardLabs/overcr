# OverCR — Installation Guide

## Prerequisites

- Python 3.10+
- Hermes Agent (reference execution runtime) — <https://hermes-agent.nousresearch.com>
- Git (for cloning the repository)

## Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/YOUR_ORG/overcr-core.git
cd overcr-core
```

### 2. Set the OVERCR_ROOT environment variable

```bash
export OVERCR_ROOT="$(pwd)"
```

Add this to your shell profile (`~/.bashrc`, `~/.zshrc`) for persistence.

### 3. Verify runtime imports

```bash
python3 -c "from runtime.overcr_runtime import OverCRRuntime; print('OK')"
```

### 4. Run the test suite

```bash
python3 tests/run_all.py
```

Expected: 26/26 tests pass.

### 5. Run a demo

```bash
cd $OVERCR_ROOT
python3 examples/runtime_demo_cryer_to_pyper.py --workspace /tmp/overcr-demo
rm -rf /tmp/overcr-demo
```

### 6. Boot with Hermes

```bash
./boot.sh
```

This generates runtime state (workspace directories, boot manifest) and prints
a Hermes launch command. Each boot reconstructs context from filesystem state —
no session state is carried between runs.

## Configuration Templates

OverCR ships `configs/*.tpl` template files. To deploy:

```bash
# Replace {{PLACEHOLDER}} values with your paths
sed -i "s|{{OVERCR_ROOT}}|$OVERCR_ROOT|g" configs/*.tpl
sed -i "s|{{HERMES_HOME}}|$HOME/.hermes|g" configs/*.tpl
sed -i "s|{{CAG_MEMORY_PATH}}|$HOME/overcr-cag-memory|g" configs/*.tpl
sed -i "s|{{ROUTE_ID}}|overcr-hq|g" configs/*.tpl
sed -i "s|{{ARCHIVE_ROOT}}|$HOME/overcr-releases|g" configs/*.tpl

# Remove .tpl extension after filling
for f in configs/*.tpl; do mv "$f" "${f%.tpl}"; done
```

| Variable | Description | Example |
|----------|-------------|---------|
| `{{OVERCR_ROOT}}` | Absolute path to OverCR workspace | `$HOME/overcr-core` |
| `{{HERMES_HOME}}` | Absolute path to Hermes config directory | `$HOME/.hermes` |
| `{{HERMES_STATE_DB}}` | Absolute path to Hermes SQLite state DB | `$HOME/.hermes/state.db` |
| `{{HERMES_HISTORY_PATH}}` | Absolute path to Hermes history file | `$HOME/.hermes/.hermes_history` |
| `{{CAG_MEMORY_PATH}}` | Absolute path to CAG memory store | `$HOME/overcr-cag-memory` |
| `{{ROUTE_ID}}` | Route identifier for this HQ instance | `overcr-hq` |
| `{{ARCHIVE_ROOT}}` | Absolute path to release archive directory | `$HOME/overcr-releases` |

## Runtime Runtimes

OverCR is a **Hermes-first portable orchestration substrate** — it does not execute models itself. It needs a host runtime:

- **Hermes Agent** — primary reference runtime. See `docs/HERMES_REFERENCE_RUNTIME.md`.
- **Open WebUI** — optional secondary visual oversight layer.
- **Other runtimes** may adapt the contracts defined here, but compatibility is not guaranteed.
  The filesystem is the canonical interface; any runtime that can read/write the
  OverCR directory structure can drive it.

## Architecture Principles

1. **Filesystem truth is authoritative.** Chat history is ephemeral; filesystem state is canonical.
2. **Inspect before acting.** Always read state before modifying it.
3. **Prefer reversible changes.** Destructive operations require explicit approval.
4. **Keep work inside the assigned workspace.** Sandbox all operations.
5. **Cold-start continuity.** Any new instance must be able to boot from filesystem state alone.
6. **Release discipline.** Frozen release artifacts are immutable. Live state evolves independently.

## Safety & Governance

- **Filesystem-first source of truth.** Chat history is ephemeral; filesystem state is canonical.
- **Model output is untrusted until sanitized and validated.** All subagent output passes 6-level validation (L1–L6) before state advancement.
- **No autonomous outbound contact.** OverCR never initiates network requests, sends email, or calls external APIs.
- **No autonomous filesystem mutation.** Subagent workers produce structured packets; they do not write files or modify the filesystem directly.
- **PypER and CodER are advisory only.** PypER produces execution plans; CodER produces patch plans. Neither executes autonomously.
- **Workflow choreography is bounded, audited, and approval-aware.** DAGs are pre-flight checked, append-only audit traces are written, and approval gates are enforced.