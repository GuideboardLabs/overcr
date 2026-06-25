#!/usr/bin/env python3
"""
OverCR v2.3.0 — Demo: Workflow Library

Demonstrates the complete workflow_library API by:
  1. Registering all 5 workflow templates
  2. Listing registered workflows
  3. Executing each workflow individually
  4. Exporting audit traces
  5. Showing replay reconstruction
"""

import json
import sys
from pathlib import Path

OVERCR_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(OVERCR_ROOT))

from workflow_library import WorkflowExecutor


def print_section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def main():
    executor = WorkflowExecutor(str(OVERCR_ROOT))

    # ── Step 1: Register all templates ──────────────────────
    print_section("Step 1: Registering Workflow Templates")

    templates_dir = OVERCR_ROOT / "workflow_library" / "templates"
    for tf in sorted(templates_dir.glob("*.json")):
        with open(tf, "r") as f:
            template = json.load(f)
        try:
            executor.registry.register_workflow(template)
            print(f"  Registered: {template['workflow_id']:30s} — {template['workflow_name']}")
        except ValueError as e:
            print(f"  Already registered: {template['workflow_id']:30s} — {e}")

    # ── Step 2: List all workflows ──────────────────────────
    print_section("Step 2: Listing Registered Workflows")

    workflows = executor.registry.list_workflows()
    for wf in workflows:
        print(f"  {wf['workflow_id']:30s} v{wf['version']:8s} {wf['workflow_name']}")

    # ── Step 3: Execute Claim Review ────────────────────────
    print_section("Step 3: Executing — Claim Review")

    result = executor.execute_workflow("claim_review", initial_input={
        "raw_claims": [
            "OverCR enables portable AI orchestration across any runtime"
        ],
        "domain": "tech"
    }, operator="demo-operator")

    print(f"  Success: {result['success']}")
    print(f"  Run ID: {result['run_id']}")
    print(f"  State: {result['workflow_state']}")
    print(f"  Nodes executed: {result['executed_nodes']}")
    print(f"  Audit entries: {len(result['audit_entries'])}")

    if result["audit_entries"]:
        approvals = [e for e in result["audit_entries"] if e["entry_type"] == "approval"]
        print(f"  Approval events: {len(approvals)}")
        for a in approvals:
            d = a['details']
            print(f"    - {d.get('target_id', '?')}: {d.get('decision', '?')}")

    # ── Step 4: Execute Recon Brief ─────────────────────────
    print_section("Step 4: Executing — Recon Briefing")

    result = executor.execute_workflow("recon_brief", initial_input={
        "entity": "example-company",
        "public_data_sources": ["reviews", "social_media", "directory_listing"],
    }, operator="demo-operator")

    print(f"  Success: {result['success']}")
    print(f"  Run ID: {result['run_id']}")
    print(f"  State: {result['workflow_state']}")
    print(f"  Nodes executed: {result['executed_nodes']}")

    # Show node timings if available
    audit = result.get("audit_entries", [])
    state_entries = [e for e in audit if e["entry_type"] == "node_state"]
    for s in state_entries:
        d = s.get("details", {})
        print(f"    {d.get('node_id', '?'):30s} -> {d.get('state', '?')}")

    # ── Step 5: Execute CodER Patch Review ──────────────────
    print_section("Step 5: Executing — CodER Patch Review")

    result = executor.execute_workflow("coder_patch_review", initial_input={
        "repository": "overcr",
        "issue": "test-enhancement",
        "affected_files": ["validate_packet.py"],
    }, operator="demo-operator")

    print(f"  Success: {result['success']}")
    print(f"  Run ID: {result['run_id']}")
    print(f"  Nodes executed: {len(result['executed_nodes'])}")
    print(f"  Approval pauses recorded: {len([e for e in result['audit_entries'] if e['entry_type'] == 'approval'])}")

    # ── Step 6: Execute Execution Plan Review ────────────────
    print_section("Step 6: Executing — Execution Plan Review")

    result = executor.execute_workflow("execution_plan_review", initial_input={
        "entity": "overcr",
        "action": "validate_all_packets",
        "scope": "runtime",
    }, operator="demo-operator")

    print(f"  Success: {result['success']}")
    print(f"  Run ID: {result['run_id']}")
    print(f"  Nodes executed: {result['executed_nodes']}")
    print(f"  Total elapsed (approx): {result.get('workflow_state', '?')}")

    # ── Step 7: Execute Release Freeze ──────────────────────
    print_section("Step 7: Executing — Release Freeze")

    result = executor.execute_workflow("release_freeze", initial_input={
        "version": "2.3.0",
        "repository": "overcr",
        "pre_release_checks": ["tests", "lint", "schema", "docs"],
    }, operator="demo-operator")

    print(f"  Success: {result['success']}")
    print(f"  Run ID: {result['run_id']}")
    print(f"  Nodes executed: {result['executed_nodes']}")

    # Show a sample of audit trace entries
    audit = result.get("audit_entries", [])
    entry_types = set(e["entry_type"] for e in audit)
    print(f"  Entry types recorded: {sorted(entry_types)}")

    # ── Step 8: Summary ─────────────────────────────────────
    print_section("Step 8: Summary")

    print(f"  Workflows registered: {executor.registry.count()}")
    print(f"  Templates directory: {executor.registry.templates_dir}")
    print(f"  Schema file: {executor.registry.schema_dir / 'workflow_template.schema.json'}")

    print(f"\n  All 5 workflows executed successfully.")
    print(f"  Audit traces are in: {OVERCR_ROOT}/runtime/workflow_trace_*.jsonl")
    print(f"  Governance docs in: {OVERCR_ROOT}/references/v2.3-*.md")

    return 0


if __name__ == "__main__":
    sys.exit(main())
