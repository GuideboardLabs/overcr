# OverCR Runtime v0.2.1
"""
The smallest useful runtime driver for the OverCR orchestration system.

v0.1.0 capabilities (all preserved):
  - Creates task records on the filesystem
  - Assigns task IDs from a sequential counter
  - Selects subagent type based on task domain
  - Generates request packets
  - Validates response packets via tools/validate_packet.py
  - Advances task lifecycle states
  - Enforces approval_required gates
  - Writes audit entries
  - Stores all state on disk (filesystem-first)

v0.2.0 additions:
  - Live subagent worker execution (CodER first)
  - WorkerRunner: subprocess invocation with timeout, capture, kill
  - SubagentAdapter: bridges OverCRRuntime to worker processes
  - Worker contract: stdin JSON request -> stdout JSON response
  - Output validation enforced (6-level) before state advancement
  - Audit-safe stdout/stderr summaries (truncated, control-char stripped)
  - Failed/timed-out workers leave task in safe state (never auto-advance)

v0.2.1 additions:
  - Worker Registry: centralized registration with compatibility checks
  - Worker Capabilities: validated capability flags per subagent
  - Worker Healthcheck: launch/response/schema/capability verification
  - Replay Runner: deterministic replay from filesystem state (read-only)
  - KnowER as second live worker (research, analysis, myth separation)
  - Duplicate and conflicting registration rejection
  - Packet type ownership enforcement
  - Audit consistency verification during replay
  - Tamper detection for audit history
  - Model Routing Layer: config-driven model selection (runtime-agnostic)
  - Model Policy Layer: governance enforcement (substrate only)
  - Client note: OverCR does NOT execute models; runtime delegates to host
    (Hermes is reference runtime) based on routing/policy decisions

v0.4.1 additions:
  - Execution bridge: HermesExecutionAdapter wires routing to worker invocation
  - Dry-run mode: resolve routing without inference
  - Route-aware execution: model/provider/timeout from routing config
  - CryER first-class worker: 6 packet types for public-signal reconnaissance
  - Execution audit fields in task records

## Architecture Clarification

### OverCR Is a Substrate, Not a Runtime

**OverCR is a portable orchestration substrate** — it defines contracts,
state, governance, and coordination, but does NOT execute models itself.

Components:
  - ModelRouter: config-driven model selection (intent layer)
  - ModelPolicy: governance constraints (validation layer)
  - SubagentAdapter: bridges to host runtime (Hermes)
  - WorkerRunner: subprocess worker execution

Host Runtime (Hermes):
  - Implements actual model invocation
  - Handles timeout enforcement
  - Implements failover to fallback models
  - Manages provider connections

Provider:
  - Ollama Cloud, local Ollama, etc.
  - Executes actual model inference
  - Returns responses to runtime
"""
__version__ = "1.0.0"

# Important note: OverCR delegates to host runtime for model execution
# The runtime layer is responsible for:
#   - Task lifecycle management
#   - Subagent invocation
#   - State advancement (filesystem-first)
#   - Policy validation
#   - Audit logging
#
# The host runtime (Hermes) is responsible for:
#   - Actual model invocation
#   - Provider connection management
#   - Timeout enforcement
#   - Failover logic
