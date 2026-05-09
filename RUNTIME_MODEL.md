# Runtime Model — OverCR v0.0.3

This document explains how OverCR's layers fit together, who talks to what, and where state lives.

---

## The Four Layers

```
┌─────────────────────────────────────────────────┐
│                  Operator                        │
│            (human approval gate)                 │
│    Approves all outbound actions. Reads           │
│    recon, scores, drafts. Greenlights or         │
│    rejects. Not a spectator.                      │
└──────────┬───────────────────────┬──────────────┘
           │                       │
    ┌──────▼──────┐        ┌───────▼───────┐
    │   Hermes     │        │  Open WebUI    │
    │  (terminal)  │        │  (browser)     │
    └──────┬──────┘        └───────┬───────┘
           │                       │
           └───────┬───────────────┘
                   │ filesystem
           ┌───────▼───────┐
           │    OverCR       │
           │  (substrate)    │
           │  doctrine +    │
           │  state files   │
           └───────┬───────┘
                   │ API calls / inference
           ┌───────▼───────┐
           │  Model Provider │
           │  (interchangeable)│
           └───────────────┘
```

### Layer 1: Model Provider (interchangeable cognition)

The bottom layer. This is where inference happens. OverCR does not care which provider you use.

Supported patterns:

| Pattern | Examples | Notes |
|---------|----------|-------|
| Local | Ollama, llama.cpp, vLLM | Data stays on your machine |
| Cloud | OpenAI, Anthropic, Google | Requires API key, sends data to provider |
| Hybrid | Local for speed + cloud for reasoning | Route by task complexity |
| Self-hosted | vLLM on a GPU box | Full control, higher setup cost |

OverCR connects to the model through Hermes. You configure the provider in Hermes, not in OverCR. OverCR's `OVERCR_MODEL` and `OVERCR_PROVIDER` env vars are optional overrides, not replacements for Hermes configuration.

**Provider agnosticism is structural.** The doctrine, governance, state, and memory are all in the substrate layer. Swap the model provider and the doctrine doesn't change. Use a weaker model and the agent may struggle with complex instructions, but it won't bypass the outreach boundary.

### Layer 2: OverCR (portable doctrine and substrate)

The middle layer. Files on disk in `$OVERCR_ROOT`.

- `soul.md` — identity, personality, rules, workflow
- `overcr_state.json` — runtime state (instance ID, paths, routes)
- `configs/` — routing, ingestion, memory, release preservation
- `memory/routes/` — per-route memory storage
- `prompts/` — boot prompts and context bundles

This layer is **filesystem-first**. The files are the source of truth. Chat history in any interface (Hermes, Open WebUI, or anything else) is secondary and ephemeral. If the agent and a config file disagree, the file wins.

Key implications:

- You can inspect, edit, or version-control OverCR state by editing files
- You can reset state by clearing files
- You can freeze a snapshot by archiving the directory
- You can transfer the workspace to another machine by copying the directory and setting `OVERCR_ROOT`

### Layer 3: Interfaces

Hermes and Open WebUI both sit above the substrate. They read and write the same filesystem. They are not OverCR — they are interfaces to it.

**Hermes (primary, terminal)**

- Command-line agent interface
- Runs OverCR's boot prompts and governance rules
- Executes tool calls (search, file operations, terminal)
- Maintains its own session database (`~/.hermes/state.db`)
- The primary supported path for OverCR

**Open WebUI (secondary, browser)**

- Web dashboard for reviewing reports, scores, and drafts
- Visual interface for approving or rejecting outbound actions
- Can connect to the same model backend as Hermes
- Does **not** automatically share session state with Hermes
- Must be pointed at the same `$OVERCR_ROOT` to reflect OverCR state

### Layer 4: Operator (approval gate)

You. The human who approves or rejects outbound actions.

The governance model is explicit: the agent can research, enrich, score, draft, and structure freely. It cannot send, call, book, submit, or contact anyone without your approval.

This is not a suggestion. It is a rule in the doctrine (`soul.md`), enforced in every route, every subagent specification, and every session prompt.

---

## How State Flows

```
Operator edits file ──────────────→ filesystem (source of truth)
                                        │
Hermes session ───── reads files ───────┤
                                        │
Open WebUI ───────── reads files ───────┘
```

- When Hermes writes state, it writes to files in `$OVERCR_ROOT`
- When Open WebUI reads state, it reads from files in `$OVERCR_ROOT`
- There is no sync protocol. There is no event bus. There is no API bridge.
- The filesystem is the coordination layer.

If you run both Hermes and Open WebUI simultaneously:

1. State written by Hermes (for example, a task note or route update) will be on disk within the session
2. Open WebUI will see it when it reads the same files
3. There is no real-time push. The filesystem is the eventual-consistency layer.

This is intentional. OverCR values simplicity and auditability over real-time convenience. If you need real-time sync between interfaces, that is outside OverCR's scope — you would need to build it yourself.

---

## Model Provider Configuration

OverCR does not configure model providers. That's Hermes' job.

**Via Hermes CLI:**
```bash
hermes config set provider ollama-cloud
hermes config set model qwen3-coder-next
```

**Via environment override:**
```bash
export OVERCR_MODEL="gpt-4o"
export OVERCR_PROVIDER="openai"
```

The env vars are hints. If a model is specified in both Hermes config and env vars, the env var takes precedence for that OverCR instance. If neither is set, Hermes uses its default.

**Local backend (Ollama):**
```bash
# Start Ollama
ollama serve

# Pull a model
ollama pull qwen3-coder

# Point Hermes at it
hermes config set provider ollama-cloud
hermes config set model qwen3-coder-next
```

**Cloud backend (OpenAI):**
```bash
export OPENAI_API_KEY="your-openai-api-key"

# Point Hermes at it
hermes config set provider openai
hermes config set model gpt-4o
```

**Hybrid backend:**
You can configure Hermes with model routing rules that send different tasks to different providers. OverCR doesn't control this — it's configured at the Hermes level.

---

## Session Lifecycle

### Cold Start

On a fresh workspace, OverCR has no state on disk beyond the templates. The boot process reconstructs context from files:

1. Read `soul.md` for identity and rules
2. Read `overcr_state.json` for paths and config
3. Read `memory/routes/hq/` for route-based memory
4. Read `tasks/` for task assignments
5. Check `configs/` for routing and ingestion settings
6. Report status and await commands

### Session Continuity

Between sessions, state persists on disk. When you boot again, the agent reads the filesystem — not the chat history — to reconstruct context.

If you use Hermes, its built-in session database (`~/.hermes/state.db`) provides additional continuity. If you use Open WebUI, it has its own session storage. Neither replaces the filesystem as the authoritative source.

### Hot Redeploy

You can update OverCR files mid-session. The agent reads from disk at boot and when explicitly asked. To pick up changes:

```
Re-read soul.md and overcr_state.json. Apply updated configuration.
```

Or simply re-boot.

---

## Outreach Boundary Implementation

The boundary is enforced at three levels:

1. **Doctrine** (`soul.md`) — the agent's rules include "avoid destructive commands unless approved" and "inspect before acting"
2. **Subagent specification** (CryER and future subagents) — explicitly list permitted and forbidden actions
3. **Interface behavior** — Hermes and Open WebUI are interfaces. They do not auto-send. The agent drafts, you approve.

No configuration flag weakens this. No model override bypasses it. If you find a way around it, that's a bug, not a feature.

---

## What Open WebUI Does Not Do

- Automatically share state with Hermes
- Provide real-time sync with OverCR
- Have special OverCR integration
- Override the outreach boundary
- Substitute for the filesystem as source of truth

If you want Open WebUI to reflect OverCR state, point it at the same model backend and the same `$OVERCR_ROOT` directory. State flows through files, not through an API.

---

## Adding Models or Providers

OverCR is model-agnostic. To add a new model or provider:

1. Configure it in Hermes: `hermes config set provider <name>`
2. Ensure the model is available (local: `ollama pull <model>`, cloud: set API key)
3. Optionally set `OVERCR_MODEL` and `OVERCR_PROVIDER` env vars

You do not need to modify OverCR files. The substrate doesn't care what inference engine generates the tokens.

---

## Adding Routes

OverCR starts with the `overcr-hq` route. To add more:

1. Create a directory: `mkdir -p $OVERCR_ROOT/memory/routes/my-route`
2. Add to `overcr_state.json` under `routes`
3. Boot into the route by telling Hermes to load context from that directory

Routes share the same governance model. A new route cannot weaken the outreach boundary.

---

## FAQ

**Can I use OverCR without Hermes?**

Technically yes — the files are just files. You can load `soul.md` and the boot prompt into any LLM interface. But Hermes is the primary supported path. Other interfaces are at your own discretion.

**Can I use Open WebUI instead of Hermes?**

You can. Open WebUI is a secondary, optional interface. It does not replace Hermes. It does not automatically share state with Hermes. Point both at the same `$OVERCR_ROOT` for filesystem-level coordination.

**What happens if Hermes and Open WebUI show different state?**

The filesystem wins. Check `$OVERCR_ROOT/overcr_state.json` and `$OVERCR_ROOT/memory/`.

**Can I use a cloud model and still keep data local?**

OverCR's state files stay on your machine. The model provider receives prompts (which may contain your data). If data privacy is critical, use a local model. OverCR's doctrine and governance don't change regardless of provider.

**Is this production-ready?**

No. v0.0.3 is early-stage. Expect rough edges. The governance model is solid, but the tooling, testing, and subagent infrastructure are incomplete.