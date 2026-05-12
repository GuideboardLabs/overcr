#!/usr/bin/env python3
"""
OverCR v0.2.1 Audit Integration Test

Demonstrates how policy violations are logged to the audit trail.
"""

import sys
import os
_CORE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _CORE_DIR)

import json
from datetime import datetime, timezone
from runtime.model_policy import ModelPolicy


def test_audit_logging():
    """Test audit logging for policy violations."""
    
    print("=" * 70)
    print("OverCR v0.2.1 Audit Integration Test")
    print("=" * 70)
    
    policy = ModelPolicy()
    
    # Track audit entries
    audit_entries = []
    
    def log_policy_decision(task_id, decision_type, result):
        """Simulate logging policy decision to audit."""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "task_id": task_id,
            "entry_type": f"policy_{decision_type}",
            "policy_result": result.to_dict(),
        }
        audit_entries.append(entry)
        return entry
    
    # Test scenarios
    scenarios = [
        ("task-audit-001", "glm-5.1:cloud", "research", "knower", "valid_routing"),
        ("task-audit-002", "qwen3:4b", "recon", "cryer", "violation_sovereignty"),
    ]
    
    print("")
    print("AUDIT ENTRIES GENERATED:")
    print("-" * 70)
    
    for task_id, model, route, subagent, decision_type in scenarios:
        result = policy.validate_routing(
            model=model,
            route=route,
            subagent=subagent,
        )
        
        entry = log_policy_decision(task_id, decision_type, result)
        
        print(f"")
        print(f"Entry: policy_{decision_type}")
        print(f"  Task ID: {task_id}")
        print(f"  Timestamp: {entry['timestamp']}")
        print(f"  Valid: {result.valid}")
        
        if result.errors:
            print(f"  Errors: {result.errors}")
        if result.warnings:
            print(f"  Warnings: {result.warnings}")
        
        if result.policy_facts:
            pf = result.policy_facts
            print(f"  Model class: {pf.get('model_class')}")
            print(f"  Minimum class required: {pf.get('minimum_class_required')}")
            print(f"  Approval required: {pf.get('approval_required')}")
    
    # Summary
    print("")
    print("-" * 70)
    print(f"Total audit entries: {len(audit_entries)}")
    
    # Count violations
    violations = sum(1 for e in audit_entries if not e['policy_result']['valid'])
    print(f"Policy violations logged: {violations}")
    
    # Audit trail format example
    print("")
    print("AUDIT TRAIL EXAMPLE (JSON):")
    print("-" * 70)
    print(json.dumps(audit_entries[0], indent=2))
    
    print("")
    print("=" * 70)
    print("Audit integration test complete")
    print("=" * 70)


if __name__ == "__main__":
    test_audit_logging()
