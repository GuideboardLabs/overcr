# Workflow Choreography — v0.8.0 Reference

## Overview

OverCR v0.8.0 introduces **governed cross-worker choreography** — the ability for multiple subagents to collaborate inside explicit, validated workflow DAGs with typed packet handoffs routed exclusively through OverCR.

Key additions:

- **Explicit DAGs** — every workflow is a directed acyclic graph of nodes and edges, validated on construction
- **Typed packet handoffs** — every edge declares accepted packet types; packets flow through OverCR, never directly between subagents
- **Policy enforcement** — every node execution and edge handoff must pass WorkflowPolicy before proceeding
- **Audit trails** — append-only JSONL trace records every decision, failure, approval gate, and retry
- **Replay from filesystem** — workflows can be reconstructed from their trace files without re-execution

## Workflow Execution Model

Every workflow operates under these invariants:

1. **Every node is a task assigned to one subagent** — a single node maps to exactly one subagent producing exactly one packet type
2. **Every edge is a typed packet handoff routed through OverCR** — subagents never call each other directly; all routing goes through OverCR
3. **Workflows are explicit DAGs** — cycles are forbidden and detected at build time; the graph must pass validation before execution can begin
4. **Execution is topological** — nodes execute in topological order; a node runs only after all its predecessors have completed successfully
5. **Failure stops the workflow** — validation failure, policy violation, missing approval, or exhausted retries halt the entire workflow immediately

## Stop Conditions

A workflow halts immediately when any of these occur:

| Condition | Source | Behavior |
|---|---|---|
| Validation failure | Packet fails L1-L6 validation after retries | Workflow state → `failed` |
| Policy violation | WorkflowPolicy denies node or edge | Workflow state → `failed` |
| Approval required without operator approval | Node `approval_policy="always"` or edge `approval_gate="always"` with no granted approval | Workflow state → `failed` |
| Max retries exceeded | `node.max_retries` reached and deterministic fallback also fails | Workflow state → `failed` |

All stop conditions are recorded in the audit trace with `entry_type="workflow_fail"`.

## Workflow Graph

**Module:** `runtime/workflow_graph.py` (661 lines)

### WorkflowNode

A single node in the workflow DAG — one task assigned to one subagent.

**Fields:**

| Field | Type | Default | Description |
|---|---|---|---|
| `node_id` | str | required | Unique identifier within the graph |
| `subagent` | str | required | Which subagent executes this node |
| `packet_type` | str | required | What packet type this node produces |
| `input_requirements` | list | `[]` | Required input packet types |
| `output_requirements` | list | `[]` | Expected output packet types |
| `approval_policy` | str | `"always"` | `"always"` / `"on_failure"` / `"never"` |
| `max_retries` | int | `0` | Maximum retry attempts (0 = no retry) |
| `timeout_s` | float | `30.0` | Maximum seconds for this node's execution |
| `description` | str | `""` | Human-readable description |

**Validation rules:**

- `subagent` must be in `{"cryer", "pyper", "coder", "knower"}`
- `packet_type` must belong to the declared `subagent` (enforced from `PACKET_TYPES_BY_SUBAGENT`)
- `approval_policy` must be in `{"always", "on_failure", "never"}`
- `max_retries` must be >= 0
- `timeout_s` must be > 0

### WorkflowEdge

A directed edge between two nodes — a typed packet handoff routed through OverCR.

**Fields:**

| Field | Type | Default | Description |
|---|---|---|---|
| `edge_id` | str | required | Unique identifier within the graph |
| `source_node_id` | str | required | The node that produces the packet |
| `target_node_id` | str | required | The node that receives the packet |
| `accepted_packet_types` | list | `[]` | Packet types valid on this edge |
| `transformation_rule` | str or None | `None` | How to transform the packet for the target |
| `approval_gate` | str or None | `None` | Whether this handoff requires approval |

**Validation rules:**

- `source_node_id` and `target_node_id` must exist in the graph
- No self-loops (`source_node_id != target_node_id`)
- Must declare at least one `accepted_packet_types` entry
- All `accepted_packet_types` must be valid packet types
- `approval_gate` must be in `{"always", "on_failure", "never"}` if set

### WorkflowGraph

An explicit DAG for governed cross-worker choreography. OverCR is the only router — no direct subagent-to-subagent routing.

**Construction:**

```python
graph = WorkflowGraph(
    workflow_id="optional-uuid",  # auto-generated if omitted
    name="my_workflow",
    version="0.8.0",
    description="...",
)
graph.add_node(node).add_edge(edge)
valid, errors = graph.build()
```

**Build validation checks:**

1. At least one node exists
2. All node IDs referenced by edges exist
3. No cycles — DAG invariant enforced via Kahn's algorithm topological sort
4. Sovereignty enforcement — cross-subagent handoffs must use a valid OverCR path from `VALID_HANDOFF_PATHS`
5. Packet type compatibility — source node's `packet_type` must be in edge's `accepted_packet_types`
6. No orphan nodes — every non-root node must be reachable from a root

**Valid handoff paths (v0.8.0):**

| Path | Description |
|---|---|
| `knower → cryer` | Classification context to reconnaissance |
| `cryer → pyper` | Signal data to execution planning |
| `coder → pyper` | Patch advisory to execution simulation |
| `knower → pyper` | Research to outreach planning |
| `knower → coder` | Research to implementation |
| `coder → knower` | Blocked state to research |
| `cryer → knower` | Recon to deep analysis |

**Key methods:**

| Method | Returns | Description |
|---|---|---|
| `add_node(node)` | `self` (chainable) | Add a validated node |
| `add_edge(edge)` | `self` (chainable) | Add a validated edge |
| `build()` | `(bool, list[str])` | Validate and finalize the graph |
| `topological_order()` | `list[str]` | Node IDs in execution order |
| `edges_from(node_id)` | `list[WorkflowEdge]` | Outgoing edges |
| `edges_to(node_id)` | `list[WorkflowEdge]` | Incoming edges |
| `predecessor_nodes(node_id)` | `list[str]` | Predecessor node IDs |
| `successor_nodes(node_id)` | `list[str]` | Successor node IDs |
| `to_dict()` / `to_json()` | dict / str | Serialize |
| `from_dict(data)` / `from_json(str)` | `WorkflowGraph` | Deserialize |

### Factory Methods

Pre-built demo workflow graphs:

**`WorkflowGraph.knower_to_cryer_workflow()`**

KnowER classifies claims → CryER produces governed recon packet from validated public-signal context.

- Node `knower_classify`: subagent=knower, packet_type=knower_claim_review, approval_policy=on_failure, max_retries=1
- Node `cryer_recon`: subagent=cryer, packet_type=cryer_recon, approval_policy=always, max_retries=1
- Edge `knower_to_cryer`: accepted=[knower_claim_review, knower_assessment], transformation=extract_public_signal_context, approval_gate=never

**`WorkflowGraph.cryer_to_pyper_workflow()`**

CryER produces public signal → PypER produces execution plan (approval_required, no outbound).

- Node `cryer_signal`: subagent=cryer, packet_type=cryer_engagement_signal, approval_policy=on_failure, max_retries=1
- Node `pyper_plan`: subagent=pyper, packet_type=pyper_execution_plan, approval_policy=always, max_retries=0
- Edge `cryer_to_pyper`: accepted=[cryer_engagement_signal, cryer_reputation_signal, cryer_recon], transformation=extract_signal_for_planning, approval_gate=always

**`WorkflowGraph.coder_to_pyper_workflow()`**

CodER produces advisory patch plan → PypER produces execution plan simulation (no real execution, no filesystem mutation).

- Node `coder_patch`: subagent=coder, packet_type=coder_patch_plan, approval_policy=always, max_retries=1
- Node `pyper_simulate`: subagent=pyper, packet_type=pyper_execution_receipt, approval_policy=always, max_retries=0
- Edge `coder_to_pyper`: accepted=[coder_patch_plan], transformation=extract_patch_for_simulation, approval_gate=always

## Workflow Policy

**Module:** `runtime/workflow_policy.py` (421 lines)

### PolicyDecision

The result of every policy check. Returns `True`/`False` via `__bool__` for direct use in conditionals.

**Fields:**

| Field | Type | Description |
|---|---|---|
| `allowed` | bool | Whether the action is permitted |
| `reason` | str | Human-readable explanation |
| `policy_name` | str | Name of the policy that was checked |
| `details` | dict | Additional context (violations, errors, etc.) |

### WorkflowPolicy Checks

#### check_node_execution(graph, node, packet=None)

Checks if a node is allowed to execute:

1. Node subagent must be valid
2. Node packet_type must belong to its subagent
3. Packet content must not contain forbidden patterns (if packet provided)

#### check_edge_handoff(graph, edge, source_packet=None)

Checks if an edge handoff is allowed:

1. Source and target nodes must exist
2. Cross-subagent handoff must go through a valid OverCR path
3. No direct subagent-to-subagent routing (sovereignty)
4. Source packet type must be in edge's `accepted_packet_types`
5. Edge approval gate must be satisfied if set

#### check_approval_required(node, edge=None, operator_approval=None)

Checks if operator approval is required and whether it has been granted:

- `approval_policy="always"` on a node requires approval
- `approval_gate="always"` on an edge requires approval
- Returns `allowed=True` if no approval needed or if `operator_approval["decision"] == "approved"`
- Returns `allowed=False` if approval required but not granted

#### check_retry_allowed(node, current_retry_count, last_error=None)

Checks if retry is allowed for a node:

- `max_retries == 0` → no retry allowed
- `current_retry_count >= max_retries` → limit reached, no retry

#### check_deterministic_fallback(node, inference_failed=False)

Checks if deterministic fallback is allowed:

- Only allowed if policy config `allow_deterministic_fallback` is `True`
- Only allowed when inference has actually failed (`inference_failed=True`)

#### check_full_workflow(graph, operator_approvals=None)

Comprehensive policy check on the entire workflow graph. Checks every node and every edge for policy compliance, including all approval requirements.

### Content Safety Patterns

The policy engine scans all packet content for forbidden patterns:

**Shell patterns (FORBIDDEN_SHELL_PATTERNS):**

| Pattern | Blocks |
|---|---|
| `curl\|bash` | Remote pipe execution |
| `wget\|sh` | Remote pipe execution |
| `rm -rf` | Recursive delete |
| `mkfs` | Filesystem format |
| `dd if=` | Block device write |
| `> /dev/sd` | Block device redirect |
| `chmod 777` | Permission escalation |
| `/etc/passwd` | System credential access |
| `exec(` | Python dynamic exec |
| `__import__` | Python dynamic import |
| `subprocess.Popen` | Subprocess spawning |
| `os.system(` | OS command execution |

**Network patterns (FORBIDDEN_NETWORK_PATTERNS):**

| Pattern | Blocks |
|---|---|
| `requests.get` | HTTP GET via requests |
| `requests.post` | HTTP POST via requests |
| `urllib.request` | urllib access |
| `http://` / `https://` | URL patterns with active fetch/request context |
| `socket.connect` | Socket connections |

Note: `http://` and `https://` are only flagged when combined with active fetch/request keywords, not when appearing as passive entity references.

## Workflow Runner

**Module:** `runtime/workflow_runner.py` (1038 lines)

### WorkflowRunner

The orchestration engine that executes a WorkflowGraph with full governance.

**Construction:**

```python
runner = WorkflowRunner(
    root="/path/to/overcr",      # OverCR root directory
    policy=WorkflowPolicy(...),   # Optional: defaults to allow_deterministic_fallback=True
    worker_fn=my_worker,          # Optional: callable(node, input_packet) -> dict
    validator_fn=my_validator,    # Optional: callable(packet) -> (valid, errors, warnings)
    allow_deterministic_fallback=True,
)
```

If `worker_fn` is `None`, nodes produce simulated/deterministic output. If `validator_fn` is `None`, `tools/validate_packet.py` is lazy-loaded.

### Execution Flow

1. **Build and validate graph** — `graph.build()` must succeed
2. **Run full workflow policy check** — `policy.check_full_workflow()` must pass
3. **Initialize node states** — all nodes start in `pending`
4. **Execute in topological order** — for each node:
   - Check node execution policy
   - Check approval gate
   - Execute node (worker or deterministic output)
   - Validate output packet (L1-L6)
   - On validation failure: retry if allowed, then fall back to deterministic if allowed
   - Process outgoing edges: check edge handoff policy, check edge approval gate, apply transformation rule
5. **Record every step in audit trace**
6. **Stop on any failure**, violation, or missing approval

### Workflow States

| State | Description |
|---|---|
| `pending` | Workflow has not started |
| `running` | Nodes are executing |
| `paused` | (reserved) |
| `completed` | All nodes executed successfully |
| `failed` | Workflow stopped due to error/policy violation |
| `stopped` | (reserved) |

### Node Execution States

| State | Description |
|---|---|
| `pending` | Node has not started |
| `running` | Node is executing |
| `completed` | Node finished successfully |
| `failed` | Node execution or validation failed |
| `skipped` | (reserved) |
| `waiting_approval` | (reserved) |

### run() Return

| Field | Type | Description |
|---|---|---|
| `success` | bool | Whether the workflow completed |
| `workflow_id` | str | UUID of this workflow execution |
| `workflow_state` | str | Final state |
| `executed_nodes` | list[str] | Node IDs that completed successfully |
| `failed_nodes` | list[str] | Node IDs that failed |
| `trace` | list[dict] | Full audit trace entries |
| `error` | str or None | Error message if workflow failed |
| `final_workflow_state` | str | Canonical final state |

### Transformation Rules

Edge handoffs can apply named transformation rules to extract relevant context from the source packet:

| Rule | Source | Target | Extracts |
|---|---|---|---|
| `extract_public_signal_context` | KnowER | CryER | `source_packet_type`, `source_subagent`, `summary`, `payload_summary` |
| `extract_signal_for_planning` | CryER | PypER | `source_packet_type`, `source_subagent`, `summary`, `recon_data` |
| `extract_patch_for_simulation` | CodER | PypER | `source_packet_type`, `source_subagent`, `summary`, `patch_data` |

Unknown transformation rules pass the packet through unchanged.

### Replay from Filesystem

`WorkflowRunner.replay_from_trace(root, workflow_id)` reconstructs workflow state from the append-only JSONL trace on disk — without re-executing any nodes.

**Replay semantics:**

- Reads `runtime/workflow_trace_{workflow_id}.jsonl`
- Reconstructs `executed_nodes`, `failed_nodes`, and `final_state` from trace entries
- A node that started but has no matching `node_complete` entry is inferred as failed
- Returns `success`, `workflow_id`, `final_state`, `executed_nodes`, `failed_nodes`, `trace_entries` count

## Configuration

**File:** `config/workflow_choreography.yaml`

### Global Defaults

| Setting | Default | Description |
|---|---|---|
| `approval_policy` | `"always"` | Default approval policy for nodes |
| `max_retries` | `1` | Default retry limit |
| `timeout_s` | `60.0` | Default node timeout |
| `allow_deterministic_fallback` | `true` | Whether deterministic fallback is permitted |
| `stop_on_validation_failure` | `true` | Halt on validation failure |
| `stop_on_policy_violation` | `true` | Halt on policy violation |
| `stop_on_approval_required_without_approval` | `true` | Halt on missing approval |
| `stop_on_max_retries` | `true` | Halt when retries exhausted |

### Handoff Path Definitions

Each handoff path declares source/target subagents, accepted packet types, optional transformation rule, and optional approval gate. Cross-subagent handoffs that are not listed here are forbidden — direct routing is never allowed.

### Workflow Definitions

Each workflow under `workflows:` declares its nodes and edges:

```yaml
workflows:
  knower_to_cryer:
    description: "KnowER classifies claims, CryER produces recon from public signals"
    version: "0.8.0"
    nodes:
      knower_classify:
        subagent: knower
        packet_type: knower_claim_review
        input_requirements: [raw_claims]
        output_requirements: [classified_claims]
        approval_policy: "on_failure"
        max_retries: 1
        timeout_s: 60
      cryer_recon:
        subagent: cryer
        packet_type: cryer_recon
        input_requirements: [classified_claims]
        output_requirements: [recon_packet]
        approval_policy: "always"
        max_retries: 1
        timeout_s: 60
    edges:
      knower_to_cryer:
        source: knower_classify
        target: cryer_recon
        accepted_packet_types: [knower_claim_review, knower_assessment]
        transformation_rule: "extract_public_signal_context"
        approval_gate: "never"
```

Three demo workflows are defined: `knower_to_cryer`, `cryer_to_pyper`, `coder_to_pyper`.

## Audit and Trace

### Format

The audit trail is an **append-only JSONL file** at `runtime/workflow_trace_{workflow_id}.jsonl`. Each line is a JSON object representing one `WorkflowTraceEntry`.

### Trace Entry Fields

| Field | Type | Description |
|---|---|---|
| `timestamp` | str | ISO 8601 UTC timestamp |
| `workflow_id` | str | UUID of the workflow |
| `graph_version` | str | Graph schema version |
| `entry_type` | str | Type of event (see below) |
| `node_id` | str or None | Node involved |
| `edge_id` | str or None | Edge involved |
| `source_packet_id` | str or None | Source packet type |
| `target_packet_id` | str or None | Target packet or node |
| `selected_subagent` | str or None | Subagent that executed |
| `selected_model` | str or None | Model used for inference |
| `validation_result` | dict or None | L1-L6 validation outcome |
| `policy_result` | dict or None | Policy decision |
| `approval_required` | bool | Whether approval was needed |
| `execution_authority` | str or None | Always `"overcr_routed"` or `"none"` |
| `fallback_used` | bool | Whether deterministic fallback was used |
| `elapsed_s` | float | Wall-clock time for this step |
| `details` | dict | Additional context |

### Entry Types

| `entry_type` | When |
|---|---|
| `workflow_start` | Workflow begins execution |
| `workflow_complete` | Workflow finishes successfully |
| `workflow_fail` | Workflow stops due to error |
| `node_start` | Node begins execution |
| `node_complete` | Node finishes successfully |
| `node_fail` | Node execution fails |
| `edge_handoff` | Packet handed off through an edge |
| `policy_check` | Policy decision recorded |
| `approval_gate` | Approval gate evaluation |
| `retry` | Retry or deterministic fallback |

### Replay Semantics

- Trace is write-once (append-only) — no entries are modified or deleted
- `replay_from_trace()` reads the JSONL and reconstructs state without re-execution
- A node with `node_start` but no matching `node_complete` is inferred as failed
- Final state is determined by the last `workflow_complete` or `workflow_fail` entry

## Deterministic Mode

When inference fails (worker error, validation failure after retries), the runner falls back to deterministic output — provided policy allows it (`allow_deterministic_fallback=True`).

Deterministic packets pass L1-L6 validation by construction. They carry `governance.deterministic_mode=True` and `governance.inference_used=False`.

### L1-L6 Valid Packet Generation Rules

| Level | Rule | How Deterministic Output Satisfies |
|---|---|---|
| **L1** | Required fields present | All base fields (`packet_type`, `version`, `timestamp`, `source`, `target`, `task_id`, `summary`) are populated |
| **L2** | Field types correct | String, list, dict, bool, int types match specification |
| **L3** | Value constraints | `source` matches node subagent, `target` is `"overcr"`, enum values within allowed sets |
| **L4** | Approval/authority metadata | `approval_required` set per node policy, `execution_authority` is `"none"` for pyper/coder |
| **L5** | Content safety patterns | No forbidden shell/network patterns in generated content |
| **L6** | Domain-specific constraints | `execution_type="simulated"`, `actual_execution=False`, `overall_result` contains `"SIMULATED"`, `side_effects=[]` for PypER receipts; no real command data for CodER patches |

### task_id Format

Deterministic packets use sequential task IDs: `task-NNNN` where NNNN is a zero-padded 4-digit counter starting at 0001 (e.g., `task-0001`, `task-0002`). The counter is per-runner-instance.

### Subagent-Specific Deterministic Payloads

| Subagent | Packet Type | Key Payload Fields |
|---|---|---|
| knower | `knower_claim_review` | `claim_review_data` with one test claim, classification `"fact"`, confidence 3 |
| cryer | `cryer_recon` | `recon_data` with one target entity, deterministic reputation/engagement signals |
| cryer | `cryer_engagement_signal` | `engagement_signal_data` with one metric, classification `"observed"` |
| pyper | `pyper_execution_plan` | `execution_plan_data` with one safe step, `approval_required=True`, `execution_authority="none"` |
| pyper | `pyper_execution_receipt` | `receipt_data` with `execution_type="simulated"`, `actual_execution=False`, `side_effects=[]` |
| coder | `coder_patch_plan` | `patch_plan_data` with advisory patch, `approval_required=True` |
| (other) | (any) | Generic `payload` with `deterministic=True` |

## Safety Guarantees

The following invariants are enforced by the workflow choreography system and cannot be overridden:

1. **Subagents never call each other directly** — all handoffs go through OverCR via `VALID_HANDOFF_PATHS`
2. **All handoffs through OverCR** — every edge handoff is policy-checked and routed via `execution_authority="overcr_routed"`
3. **Model output is untrusted until validated** — every packet passes L1-L6 validation before acceptance
4. **No real shell execution** — forbidden shell patterns are detected and blocked at both the policy and content-safety levels
5. **No filesystem mutation by inference** — deterministic output and model output are treated as advisory only; no code path writes to disk based on packet content (except the audit trace itself)
6. **No outbound contact** — forbidden network patterns (requests, urllib, socket) are detected and blocked; `http://`/`https://` URLs are only permitted as passive entity references, not active fetch targets

## Version History

| Version | Date | Change |
|---|---|---|
| v0.8.0 | 2026-05-11 | Workflow choreography: explicit DAGs, typed handoffs, policy enforcement, audit traces, replay, deterministic fallback |
| v0.7.0 | 2026-05-11 | PypER controlled live execution planning, 3 new packet types, L5/L6 protections |
| v0.6.0 | 2026-05-10 | CodER patch plan inference |
| v0.5.0 | 2026-05-09 | KnowER inference pipeline |
| v0.4.2 | 2026-05-08 | Hermes CLI adapter, CryER v0.4.0 |
| v0.4.1 | 2026-05-07 | CryER live worker, inference adapter |
| v0.4.0 | 2026-05-06 | CryER reconnaissance subagent |
| v0.3.0 | 2026-05-05 | Approval gate enforcement |
| v0.2.1 | 2026-05-04 | Live worker subsystem |
| v0.2.0 | 2026-05-03 | Inference pipeline |
| v0.1.0 | 2026-05-02 | Initial runtime, KnowER + CodER |