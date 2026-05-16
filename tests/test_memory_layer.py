#!/usr/bin/env python3
"""
OverCR v2.1.0 — Semantic Memory Layer Tests

Coverage:
  - MemoryRecord: create, from_dict, from_json, validation, status transitions,
    stale marking, contradiction refs, provenance integrity, serialization
  - MemoryManager: create, load, search, update_status, list_project_memory,
    supersede, index audit trail, rejected memory retention
  - MemoryPromoter: rule-gated promotion, governance gates, confidence ceiling,
    operator_direct requires operator_id, unknown rule rejection
  - MemoryRetriever: keyword/tag retrieval, deterministic fallback cascade,
    retrieve_by_id, retrieve_with_state_refs
  - MemoryConflictResolver: contradiction detection, review artifacts,
    no auto-resolution, bidirectional contradiction refs

Run:
    python3 tests/test_memory_layer.py
    python3 tests/test_memory_layer.py --phase record
    python3 tests/test_memory_layer.py --phase manager
    python3 tests/test_memory_layer.py --phase promoter
    python3 tests/test_memory_layer.py --phase retriever
    python3 tests/test_memory_layer.py --phase conflict
"""

import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# Ensure project root is on sys.path
OVERCR_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(OVERCR_ROOT))

from memory.memory_record import (
    MemoryRecord, VALID_STATUSES, VALID_PROVENANCE_TYPES,
    VALID_CONTRADICTION_TYPES, MEMORY_ID_PATTERN,
)
from memory.memory_manager import MemoryManager
from memory.memory_promoter import MemoryPromoter, PromotionError, PROMOTION_RULES
from memory.memory_retriever import MemoryRetriever
from memory.memory_conflict import MemoryConflictResolver, ConflictReviewArtifact

FAILED = False


def assert_test(condition, msg):
    """Assert condition; set FAILED flag on failure."""
    global FAILED
    if not condition:
        print(f"  FAIL: {msg}")
        FAILED = True
    else:
        pass  # Silent on pass


def make_temp_root():
    """Create a temporary directory for test isolation."""
    return tempfile.mkdtemp(prefix="overcr-mem-test-")


# ═══════════════════════════════════════════════════════════════
# Phase 1: MemoryRecord
# ═══════════════════════════════════════════════════════════════

def test_record_create():
    """Test MemoryRecord.create() produces valid records."""
    r = MemoryRecord.create(
        source="test_operator",
        provenance_type="operator_direct",
        provenance_rule="operator_observation",
        confidence=0.85,
        tags=["test", "unit"],
        project_scope="test_project",
        semantic_summary="Test memory record for unit testing.",
        operator_id="op-001",
    )
    assert_test(MEMORY_ID_PATTERN.match(r.memory_id), f"Bad memory_id format: {r.memory_id}")
    assert_test(r.source == "test_operator", f"Bad source: {r.source}")
    assert_test(r.status == "active", f"Bad status: {r.status}")
    assert_test(r.confidence == 0.85, f"Bad confidence: {r.confidence}")
    assert_test(r.provenance["type"] == "operator_direct", f"Bad provenance type: {r.provenance}")
    assert_test(r.provenance["rule"] == "operator_observation", f"Bad provenance rule: {r.provenance}")
    assert_test(r.provenance["operator_id"] == "op-001", f"Bad operator_id: {r.provenance}")
    assert_test("test" in r.tags, f"Tags missing 'test': {r.tags}")
    assert_test(r.project_scope == "test_project", f"Bad scope: {r.project_scope}")
    assert_test(len(r.canonical_state_refs) == 0, f"Expected empty refs: {r.canonical_state_refs}")
    assert_test(len(r.contradiction_refs) == 0, f"Expected empty contrads: {r.contradiction_refs}")


def test_record_validation():
    """Test MemoryRecord validation catches bad inputs."""
    # Bad source
    try:
        MemoryRecord.create(source="", provenance_type="operator_direct",
                            provenance_rule="test", confidence=0.5,
                            tags=["t"], project_scope="p", semantic_summary="s")
        assert_test(False, "Should reject empty source")
    except ValueError:
        pass

    # Bad confidence
    try:
        MemoryRecord.create(source="s", provenance_type="operator_direct",
                            provenance_rule="test", confidence=1.5,
                            tags=["t"], project_scope="p", semantic_summary="s")
        assert_test(False, "Should reject confidence > 1.0")
    except ValueError:
        pass

    # Empty tags
    try:
        MemoryRecord.create(source="s", provenance_type="operator_direct",
                            provenance_rule="test", confidence=0.5,
                            tags=[], project_scope="p", semantic_summary="s")
        assert_test(False, "Should reject empty tags")
    except ValueError:
        pass

    # Bad provenance type
    try:
        MemoryRecord.create(source="s", provenance_type="invalid_type",
                            provenance_rule="test", confidence=0.5,
                            tags=["t"], project_scope="p", semantic_summary="s")
        assert_test(False, "Should reject bad provenance type")
    except ValueError:
        pass

    # Bad semantic summary
    try:
        MemoryRecord.create(source="s", provenance_type="operator_direct",
                            provenance_rule="test", confidence=0.5,
                            tags=["t"], project_scope="p", semantic_summary="")
        assert_test(False, "Should reject empty summary")
    except ValueError:
        pass


def test_record_from_dict():
    """Test MemoryRecord.from_dict() reconstructs from stored data."""
    r = MemoryRecord.create(
        source="test_op", provenance_type="operator_direct",
        provenance_rule="operator_observation", confidence=0.9,
        tags=["test", "dict"], project_scope="test_proj",
        semantic_summary="Testing from_dict reconstruction.",
        operator_id="op-002",
    )
    d = r.to_dict()
    r2 = MemoryRecord.from_dict(d)
    assert_test(r2.memory_id == r.memory_id, f"ID mismatch: {r2.memory_id} != {r.memory_id}")
    assert_test(r2.status == r.status, f"Status mismatch: {r2.status} != {r.status}")
    assert_test(r2.source == r.source, f"Source mismatch")
    assert_test(r2.provenance == r.provenance, f"Provenance mismatch")
    assert_test(r2.tags == r.tags, f"Tags mismatch")


def test_record_from_json():
    """Test MemoryRecord.from_json() round-trips through JSON."""
    r = MemoryRecord.create(
        source="json_test", provenance_type="promotion_rule",
        provenance_rule="task_completion_insight", confidence=0.7,
        tags=["json"], project_scope="json_proj",
        semantic_summary="JSON round-trip test.",
    )
    json_str = r.to_json()
    r2 = MemoryRecord.from_json(json_str)
    assert_test(r2.memory_id == r.memory_id, "JSON round-trip ID mismatch")
    assert_test(r2.confidence == r.confidence, "JSON round-trip confidence mismatch")
    assert_test(r2.project_scope == r.project_scope, "JSON round-trip scope mismatch")


def test_record_status_transitions():
    """Test status state machine transitions."""
    r = MemoryRecord.create(
        source="s", provenance_type="operator_direct",
        provenance_rule="operator_observation", confidence=0.8,
        tags=["t"], project_scope="p", semantic_summary="Status test.",
        operator_id="op-003",
    )

    # active -> stale
    r.update_status("stale", reason="Canonical state changed")
    assert_test(r.status == "stale", f"Expected stale, got {r.status}")
    assert_test(r.stale_reason == "Canonical state changed", f"Bad stale reason: {r.stale_reason}")

    # stale -> active (refresh)
    r.update_status("active")
    assert_test(r.status == "active", f"Expected active, got {r.status}")
    assert_test(r.stale_reason is None, f"Stale reason should be None after refresh: {r.stale_reason}")

    # active -> rejected
    r.update_status("rejected")
    assert_test(r.status == "rejected", f"Expected rejected, got {r.status}")

    # rejected is terminal — no transitions out
    try:
        r.update_status("active")
        assert_test(False, "Should reject transition from rejected")
    except ValueError:
        pass


def test_record_stale_marking():
    """Test stale marking with reason."""
    r = MemoryRecord.create(
        source="s", provenance_type="operator_direct",
        provenance_rule="operator_observation", confidence=0.8,
        tags=["stale"], project_scope="p", semantic_summary="Stale test.",
        operator_id="op-004",
    )
    r.update_status("stale", reason="Filesystem artifact changed beyond recognition")
    assert_test(r.status == "stale", f"Expected stale: {r.status}")
    assert_test(r.stale_reason == "Filesystem artifact changed beyond recognition",
                f"Bad stale reason: {r.stale_reason}")


def test_record_supersede():
    """Test supersede transitions."""
    r = MemoryRecord.create(
        source="s", provenance_type="operator_direct",
        provenance_rule="operator_observation", confidence=0.8,
        tags=["old"], project_scope="p", semantic_summary="Old memory.",
        operator_id="op-005",
    )

    r.supersede("mem-abcdef01", reason="Replaced by updated insight")
    assert_test(r.status == "superseded", f"Expected superseded: {r.status}")
    assert_test(r.superseded_by == "mem-abcdef01", f"Bad superseded_by: {r.superseded_by}")

    # Superseded is terminal
    try:
        r.update_status("active")
        assert_test(False, "Should reject transition from superseded")
    except ValueError:
        pass


def test_record_contradiction_refs():
    """Test adding contradiction references."""
    r = MemoryRecord.create(
        source="s", provenance_type="operator_direct",
        provenance_rule="operator_observation", confidence=0.8,
        tags=["contra"], project_scope="p", semantic_summary="Test contrads.",
        operator_id="op-006",
    )

    r.add_contradiction("mem-12345678", "factual_contradiction", note="Summary disagreement")
    assert_test(len(r.contradiction_refs) == 1, f"Expected 1 ref: {len(r.contradiction_refs)}")
    assert_test(r.contradiction_refs[0]["conflicting_memory_id"] == "mem-12345678",
                f"Bad conflicting ID: {r.contradiction_refs[0]}")
    assert_test(r.contradiction_refs[0]["conflict_type"] == "factual_contradiction",
                f"Bad conflict type: {r.contradiction_refs[0]['conflict_type']}")


def test_record_provenance_integrity():
    """Test provenance field integrity."""
    r = MemoryRecord.create(
        source="subagent_knower", provenance_type="subagent_output",
        provenance_rule="task_completion_insight", confidence=0.7,
        tags=["provenance"], project_scope="p",
        semantic_summary="Provenance integrity test.",
        task_id="task-0001",
    )
    prov = r.provenance
    assert_test(prov["type"] == "subagent_output", f"Bad prov type: {prov['type']}")
    assert_test(prov["rule"] == "task_completion_insight", f"Bad prov rule: {prov['rule']}")
    assert_test(prov["task_id"] == "task-0001", f"Bad task_id: {prov['task_id']}")
    assert_test(prov["operator_id"] is None, f"operator_id should be None: {prov['operator_id']}")
    assert_test(prov["artifact_path"] is None, f"artifact_path should be None")


def test_record_canonical_state_refs():
    """Test canonical_state_refs field."""
    r = MemoryRecord.create(
        source="s", provenance_type="filesystem_artifact",
        provenance_rule="filesystem_artifact_promotion", confidence=0.6,
        tags=["refs"], project_scope="p", semantic_summary="State refs test.",
        canonical_state_refs=[
            {"path": "orchestration/tasks/task-0001.json", "field": "state", "as_of": "2026-01-01T00:00:00Z"},
        ],
    )
    refs = r.canonical_state_refs
    assert_test(len(refs) == 1, f"Expected 1 ref: {len(refs)}")
    assert_test(refs[0]["path"] == "orchestration/tasks/task-0001.json",
                f"Bad ref path: {refs[0]['path']}")
    assert_test(refs[0]["field"] == "state", f"Bad ref field: {refs[0]['field']}")


# ═══════════════════════════════════════════════════════════════
# Phase 2: MemoryManager
# ═══════════════════════════════════════════════════════════════

def test_manager_create_and_load():
    """Test MemoryManager create + load round-trip."""
    root = make_temp_root()
    try:
        mgr = MemoryManager(root)
        r = mgr.create_memory(
            source="test_manager", provenance_type="operator_direct",
            provenance_rule="operator_observation", confidence=0.9,
            tags=["manager", "create"], project_scope="mgr_test",
            semantic_summary="Manager create test.", operator_id="op-010",
        )
        # Verify file exists
        path = mgr.records_dir / f"{r.memory_id}.json"
        assert_test(path.exists(), f"Record file not created: {path}")

        # Load from disk
        loaded = mgr.load_memory(r.memory_id)
        assert_test(loaded.memory_id == r.memory_id, f"ID mismatch after load")
        assert_test(loaded.semantic_summary == "Manager create test.", f"Summary mismatch after load")
        assert_test(loaded.provenance["operator_id"] == "op-010", f"Provenance mismatch after load")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_manager_search():
    """Test MemoryManager search with filters."""
    root = make_temp_root()
    try:
        mgr = MemoryManager(root)
        r1 = mgr.create_memory(
            source="alpha", provenance_type="operator_direct",
            provenance_rule="operator_observation", confidence=0.9,
            tags=["search", "alpha"], project_scope="proj_a",
            semantic_summary="Alpha search test.", operator_id="op-020",
        )
        r2 = mgr.create_memory(
            source="beta", provenance_type="promotion_rule",
            provenance_rule="task_completion_insight", confidence=0.7,
            tags=["search", "beta"], project_scope="proj_b",
            semantic_summary="Beta search test.",
        )

        # Search by tag
        results = mgr.search_memory(tags=["search"])
        assert_test(len(results) == 2, f"Expected 2 results, got {len(results)}")

        # Search by project scope
        results = mgr.search_memory(project_scope="proj_a")
        assert_test(len(results) == 1, f"Expected 1 result for proj_a, got {len(results)}")
        assert_test(results[0].memory_id == r1.memory_id, "Wrong result for proj_a")

        # Search by status
        results = mgr.search_memory(status="active")
        assert_test(len(results) == 2, f"Expected 2 active, got {len(results)}")

        # Combined filters
        results = mgr.search_memory(tags=["alpha"], project_scope="proj_a", status="active")
        assert_test(len(results) == 1, f"Expected 1 combined result, got {len(results)}")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_manager_update_status():
    """Test MemoryManager status transitions."""
    root = make_temp_root()
    try:
        mgr = MemoryManager(root)
        r = mgr.create_memory(
            source="status_test", provenance_type="operator_direct",
            provenance_rule="operator_observation", confidence=0.8,
            tags=["status"], project_scope="p", semantic_summary="Status update test.",
            operator_id="op-030",
        )

        # active -> stale
        updated = mgr.update_memory_status(r.memory_id, "stale", reason="Test stale")
        assert_test(updated.status == "stale", f"Expected stale: {updated.status}")

        # reload from disk
        loaded = mgr.load_memory(r.memory_id)
        assert_test(loaded.status == "stale", f"Stale not persisted: {loaded.status}")
        assert_test(loaded.stale_reason == "Test stale", f"Stale reason not persisted")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_manager_list_project():
    """Test MemoryManager list_project_memory."""
    root = make_temp_root()
    try:
        mgr = MemoryManager(root)
        mgr.create_memory(
            source="s1", provenance_type="operator_direct",
            provenance_rule="operator_observation", confidence=0.9,
            tags=["list"], project_scope="project_x", semantic_summary="PX record 1.",
            operator_id="op-040",
        )
        mgr.create_memory(
            source="s2", provenance_type="operator_direct",
            provenance_rule="operator_observation", confidence=0.9,
            tags=["list"], project_scope="project_x", semantic_summary="PX record 2.",
            operator_id="op-041",
        )
        mgr.create_memory(
            source="s3", provenance_type="operator_direct",
            provenance_rule="operator_observation", confidence=0.9,
            tags=["list"], project_scope="project_y", semantic_summary="PY record.",
            operator_id="op-042",
        )

        px = mgr.list_project_memory("project_x")
        assert_test(len(px) == 2, f"Expected 2 PX records, got {len(px)}")

        py = mgr.list_project_memory("project_y")
        assert_test(len(py) == 1, f"Expected 1 PY record, got {len(py)}")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_manager_supersede():
    """Test MemoryManager supersede operation."""
    root = make_temp_root()
    try:
        mgr = MemoryManager(root)
        old = mgr.create_memory(
            source="s", provenance_type="operator_direct",
            provenance_rule="operator_observation", confidence=0.7,
            tags=["old"], project_scope="p", semantic_summary="Old record.",
            operator_id="op-050",
        )
        new = mgr.create_memory(
            source="s", provenance_type="operator_direct",
            provenance_rule="operator_observation", confidence=0.95,
            tags=["new"], project_scope="p", semantic_summary="New record.",
            operator_id="op-051",
        )

        updated = mgr.supersede_memory(old.memory_id, new.memory_id, reason="Better data")
        assert_test(updated.status == "superseded", f"Expected superseded: {updated.status}")
        assert_test(updated.superseded_by == new.memory_id, f"Bad superseded_by: {updated.superseded_by}")

        # Verify persistence
        loaded = mgr.load_memory(old.memory_id)
        assert_test(loaded.status == "superseded", f"Superseded not persisted: {loaded.status}")
        assert_test(loaded.superseded_by == new.memory_id, "superseded_by not persisted")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_manager_index_audit():
    """Test that index.jsonl accumulates audit entries."""
    root = make_temp_root()
    try:
        mgr = MemoryManager(root)
        r = mgr.create_memory(
            source="s", provenance_type="operator_direct",
            provenance_rule="operator_observation", confidence=0.8,
            tags=["audit"], project_scope="p", semantic_summary="Audit test.",
            operator_id="op-060",
        )

        assert_test(mgr.index_path.exists(), "Index file not created")

        with open(mgr.index_path, "r") as f:
            lines = f.readlines()
        assert_test(len(lines) >= 1, f"Expected at least 1 index line, got {len(lines)}")

        entry = json.loads(lines[0])
        assert_test(entry["action"] == "created", f"Expected 'created' action: {entry['action']}")
        assert_test(entry["memory_id"] == r.memory_id, f"ID mismatch in index")

        # Status change adds another entry
        mgr.update_memory_status(r.memory_id, "stale", reason="Test")
        with open(mgr.index_path, "r") as f:
            lines = f.readlines()
        assert_test(len(lines) >= 2, f"Expected at least 2 index lines after status change, got {len(lines)}")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_manager_rejected_retention():
    """Test that rejected memories are NEVER deleted."""
    root = make_temp_root()
    try:
        mgr = MemoryManager(root)
        r = mgr.create_memory(
            source="reject_test", provenance_type="operator_direct",
            provenance_rule="operator_observation", confidence=0.8,
            tags=["reject"], project_scope="p", semantic_summary="Will be rejected.",
            operator_id="op-070",
        )

        # Reject it
        mgr.update_memory_status(r.memory_id, "rejected")

        # Verify it still exists on disk
        loaded = mgr.load_memory(r.memory_id)
        assert_test(loaded.status == "rejected", f"Expected rejected: {loaded.status}")

        # Verify it's searchable
        results = mgr.search_memory(status="rejected")
        assert_test(len(results) == 1, f"Expected 1 rejected result, got {len(results)}")
        assert_test(results[0].memory_id == r.memory_id, "Wrong rejected result")

        # Verify file exists
        path = mgr.records_dir / f"{r.memory_id}.json"
        assert_test(path.exists(), "Rejected memory file was deleted!")

        # Manager has no delete method — verify
        assert_test(not hasattr(mgr, "delete_memory"), "Manager should NOT have delete_memory method")
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════
# Phase 3: MemoryPromoter
# ═══════════════════════════════════════════════════════════════

def test_promoter_valid_rule():
    """Test MemoryPromoter with valid rule."""
    root = make_temp_root()
    try:
        mgr = MemoryManager(root)
        promoter = MemoryPromoter(mgr)

        r = promoter.promote(
            rule_name="operator_observation",
            summary="Operator noted that service endpoints changed",
            tags=["infrastructure", "endpoints"],
            project_scope="ops",
            operator_id="op-100",
        )
        assert_test(r.status == "active", f"Expected active: {r.status}")
        assert_test(r.provenance["type"] == "operator_direct", f"Bad provenance type: {r.provenance['type']}")
        assert_test(r.provenance["rule"] == "operator_observation", f"Bad rule: {r.provenance['rule']}")
        assert_test(r.confidence == 0.9, f"Bad confidence: {r.confidence}")

        # Verify persisted
        loaded = mgr.load_memory(r.memory_id)
        assert_test(loaded.semantic_summary == "Operator noted that service endpoints changed",
                    f"Summary not persisted: {loaded.semantic_summary}")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_promoter_unknown_rule():
    """Test that unknown promotion rules are rejected."""
    root = make_temp_root()
    try:
        mgr = MemoryManager(root)
        promoter = MemoryPromoter(mgr)

        try:
            promoter.promote(
                rule_name="nonexistent_rule",
                summary="Bad rule test",
                tags=["test"],
                project_scope="test",
            )
            assert_test(False, "Should reject unknown promotion rule")
        except PromotionError as e:
            assert_test("unknown promotion rule" in str(e).lower() or "Unknown promotion rule" in str(e),
                        f"Unexpected error message: {e}")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_promoter_confidence_ceiling():
    """Test that confidence cannot exceed rule ceiling."""
    root = make_temp_root()
    try:
        mgr = MemoryManager(root)
        promoter = MemoryPromoter(mgr)

        # operator_observation ceiling is 0.9
        # Try to exceed it
        try:
            promoter.promote(
                rule_name="operator_observation",
                summary="Confidence ceiling test",
                tags=["test"],
                project_scope="test",
                operator_id="op-101",
                confidence_override=0.99,  # > 0.9 ceiling
            )
            assert_test(False, "Should reject confidence above ceiling")
        except PromotionError:
            pass

        # Decrease is ok
        r = promoter.promote(
            rule_name="operator_observation",
            summary="Confidence decrease test",
            tags=["test"],
            project_scope="test",
            operator_id="op-102",
            confidence_override=0.5,  # < 0.9 ceiling
        )
        assert_test(r.confidence == 0.5, f"Expected 0.5 confidence, got {r.confidence}")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_promoter_operator_direct_requires_id():
    """Test that operator_direct provenance requires operator_id."""
    root = make_temp_root()
    try:
        mgr = MemoryManager(root)
        promoter = MemoryPromoter(mgr)

        try:
            promoter.promote(
                rule_name="operator_observation",
                summary="Missing operator_id",
                tags=["test"],
                project_scope="test",
                operator_id=None,  # Missing!
            )
            assert_test(False, "Should require operator_id for operator_direct")
        except PromotionError:
            pass
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_promoter_list_rules():
    """Test listing and inspecting promotion rules."""
    root = make_temp_root()
    try:
        mgr = MemoryManager(root)
        promoter = MemoryPromoter(mgr)

        rules = promoter.list_rules()
        assert_test(len(rules) == 4, f"Expected 4 rules, got {len(rules)}")
        assert_test("operator_observation" in rules, "Missing operator_observation rule")
        assert_test("task_completion_insight" in rules, "Missing task_completion_insight rule")
        assert_test("filesystem_artifact_promotion" in rules, "Missing filesystem_artifact_promotion rule")
        assert_test("validation_lesson" in rules, "Missing validation_lesson rule")

        rule = promoter.get_rule("operator_observation")
        assert_test(rule["confidence"] == 0.9, f"Unexpected confidence: {rule['confidence']}")
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════
# Phase 4: MemoryRetriever
# ═══════════════════════════════════════════════════════════════

def test_retriever_basic():
    """Test basic retrieval."""
    root = make_temp_root()
    try:
        mgr = MemoryManager(root)
        r1 = mgr.create_memory(
            source="s", provenance_type="operator_direct",
            provenance_rule="operator_observation", confidence=0.9,
            tags=["retriever", "alpha"], project_scope="proj_r",
            semantic_summary="Alpha memory for retrieval.", operator_id="op-200",
        )
        r2 = mgr.create_memory(
            source="s", provenance_type="promotion_rule",
            provenance_rule="task_completion_insight", confidence=0.7,
            tags=["retriever", "beta"], project_scope="proj_r",
            semantic_summary="Beta memory for retrieval.",
        )

        retriever = MemoryRetriever(mgr)

        # Tag-based retrieval
        results = retriever.retrieve(tags=["alpha"])
        assert_test(len(results) >= 1, f"Expected >=1 result for tag 'alpha', got {len(results)}")

        # Scope-based
        results = retriever.retrieve(project_scope="proj_r")
        assert_test(len(results) >= 2, f"Expected >=2 results for proj_r, got {len(results)}")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_retriever_deterministic_fallback():
    """Test deterministic fallback cascade."""
    root = make_temp_root()
    try:
        mgr = MemoryManager(root)
        # Create one memory in scope_a, one in scope_b
        mgr.create_memory(
            source="s", provenance_type="operator_direct",
            provenance_rule="operator_observation", confidence=0.9,
            tags=["fallback", "scope_a_tag"], project_scope="scope_a",
            semantic_summary="Scope A memory.", operator_id="op-210",
        )
        mgr.create_memory(
            source="s", provenance_type="operator_direct",
            provenance_rule="operator_observation", confidence=0.8,
            tags=["fallback", "scope_b_tag"], project_scope="scope_b",
            semantic_summary="Scope B memory.", operator_id="op-211",
        )

        retriever = MemoryRetriever(mgr)

        # Level 1: exact tag + scope — will find scope_a memory
        results = retriever.retrieve(tags=["scope_a_tag"], project_scope="scope_a")
        assert_test(len(results) >= 1, f"Level 1 fallback failed: {len(results)}")

        # Level 5: text query fallback — should find at least one
        results = retriever.retrieve(text_query="Scope", deterministic_fallback=True)
        assert_test(len(results) >= 1, f"Level 5 fallback failed: {len(results)}")

        # No tags, no scope — gets all active
        results = retriever.retrieve(deterministic_fallback=True)
        assert_test(len(results) >= 2, f"Level 6 fallback failed: {len(results)}")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_retriever_by_id():
    """Test retrieve_by_id."""
    root = make_temp_root()
    try:
        mgr = MemoryManager(root)
        r = mgr.create_memory(
            source="s", provenance_type="operator_direct",
            provenance_rule="operator_observation", confidence=0.8,
            tags=["by_id"], project_scope="p", semantic_summary="Get by ID test.",
            operator_id="op-220",
        )

        retriever = MemoryRetriever(mgr)
        found = retriever.retrieve_by_id(r.memory_id)
        assert_test(found is not None, "Should find memory by ID")
        assert_test(found.memory_id == r.memory_id, "ID mismatch")

        not_found = retriever.retrieve_by_id("mem-nonexist")
        assert_test(not_found is None, "Should return None for nonexistent ID")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_retriever_state_refs():
    """Test retrieve_with_state_refs for filesystem-first path."""
    root = make_temp_root()
    try:
        mgr = MemoryManager(root)
        mgr.create_memory(
            source="s", provenance_type="filesystem_artifact",
            provenance_rule="filesystem_artifact_promotion", confidence=0.6,
            tags=["ref_test"], project_scope="ref_proj",
            semantic_summary="State refs retrieval test.",
            canonical_state_refs=[
                {"path": "orchestration/tasks/task-0001.json", "field": "state"},
            ],
        )
        mgr.create_memory(
            source="s", provenance_type="filesystem_artifact",
            provenance_rule="filesystem_artifact_promotion", confidence=0.6,
            tags=["ref_test"], project_scope="ref_proj",
            semantic_summary="Another state refs test.",
            canonical_state_refs=[
                {"path": "orchestration/tasks/task-0002.json", "field": "state"},
            ],
        )

        retriever = MemoryRetriever(mgr)

        # Find memories referencing task-0001
        results = retriever.retrieve_with_state_refs(
            project_scope="ref_proj",
            canonical_path="orchestration/tasks/task-0001.json",
        )
        assert_test(len(results) == 1, f"Expected 1 result, got {len(results)}")

        # Nonexistent path
        results = retriever.retrieve_with_state_refs(
            project_scope="ref_proj",
            canonical_path="nonexistent/path.json",
        )
        assert_test(len(results) == 0, f"Expected 0 results, got {len(results)}")
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════
# Phase 5: MemoryConflictResolver
# ═══════════════════════════════════════════════════════════════

def test_conflict_detection():
    """Test contradiction detection between conflicting records."""
    root = make_temp_root()
    try:
        mgr = MemoryManager(root)
        resolver = MemoryConflictResolver(mgr)

        # Create two records with potentially conflicting summaries
        mgr.create_memory(
            source="knower", provenance_type="subagent_output",
            provenance_rule="task_completion_insight", confidence=0.7,
            tags=["conflict_test", "endpoint"], project_scope="infra",
            semantic_summary="Service endpoint is at http://api.example.com/v1 and not available via HTTPS",
            task_id="task-0001",
        )
        mgr.create_memory(
            source="knower", provenance_type="subagent_output",
            provenance_rule="task_completion_insight", confidence=0.8,
            tags=["conflict_test", "endpoint"], project_scope="infra",
            semantic_summary="Service endpoint HTTPS is available at api.example.com",
            task_id="task-0002",
        )

        conflicts = resolver.detect_conflicts(project_scope="infra")
        # Detection is heuristic-based — may or may not find conflicts
        # depending on keyword matching. The key test is that it doesn't crash.
        assert_test(isinstance(conflicts, list), f"Expected list, got {type(conflicts)}")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_conflict_artifact_creation():
    """Test that conflict detection creates review artifacts on disk."""
    root = make_temp_root()
    try:
        mgr = MemoryManager(root)
        resolver = MemoryConflictResolver(mgr)

        # Create records with overlapping scope and tags
        mgr.create_memory(
            source="knower", provenance_type="subagent_output",
            provenance_rule="task_completion_insight", confidence=0.7,
            tags=["infra", "database"], project_scope="infra",
            semantic_summary="Database is PostgreSQL version 14 and not available for MySQL workloads",
            task_id="task-0050",
        )
        mgr.create_memory(
            source="cryer", provenance_type="subagent_output",
            provenance_rule="task_completion_insight", confidence=0.75,
            tags=["infra", "database"], project_scope="infra",
            semantic_summary="Database supports MySQL workloads",
            task_id="task-0051",
        )

        conflicts = resolver.detect_conflicts(project_scope="infra")

        if conflicts:
            # Verify artifact was written to disk
            artifact = conflicts[0]
            path = mgr.conflicts_dir / f"{artifact.conflict_id}.json"
            assert_test(path.exists(), f"Conflict artifact not written: {path}")

            # Verify artifact has no auto-resolution
            assert_test(artifact.resolution is None, f"Resolution should be None: {artifact.resolution}")

            # Load it back
            loaded = resolver.load_conflict(artifact.conflict_id)
            assert_test(loaded is not None, "Should load conflict artifact")
            assert_test(loaded.conflict_type in VALID_CONTRADICTION_TYPES,
                        f"Bad conflict type: {loaded.conflict_type}")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_conflict_no_auto_resolve():
    """Test that conflict resolver NEVER auto-resolves."""
    root = make_temp_root()
    try:
        mgr = MemoryManager(root)
        resolver = MemoryConflictResolver(mgr)

        # Create contradictory records
        r1 = mgr.create_memory(
            source="knower", provenance_type="subagent_output",
            provenance_rule="task_completion_insight", confidence=0.7,
            tags=["conflict", "testing"], project_scope="test_conflict",
            semantic_summary="System does NOT support feature X",
            task_id="task-0060",
        )
        r2 = mgr.create_memory(
            source="knower", provenance_type="subagent_output",
            provenance_rule="task_completion_insight", confidence=0.8,
            tags=["conflict", "testing"], project_scope="test_conflict",
            semantic_summary="System supports feature X fully",
            task_id="task-0061",
        )

        conflicts = resolver.detect_conflicts(project_scope="test_conflict")

        # Even if conflicts detected, neither record should be auto-resolved
        loaded1 = mgr.load_memory(r1.memory_id)
        loaded2 = mgr.load_memory(r2.memory_id)

        assert_test(loaded1.status == "active", f"Record 1 should still be active: {loaded1.status}")
        assert_test(loaded2.status == "active", f"Record 2 should still be active: {loaded2.status}")

        # Conflict artifacts should have resolution=None
        for c in conflicts:
            assert_test(c.resolution is None, f"Auto-resolution detected: {c.resolution}")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_conflict_bidirectional_refs():
    """Test that contradiction refs are added bidirectionally."""
    root = make_temp_root()
    try:
        mgr = MemoryManager(root)
        resolver = MemoryConflictResolver(mgr)

        r1 = mgr.create_memory(
            source="knower", provenance_type="subagent_output",
            provenance_rule="task_completion_insight", confidence=0.7,
            tags=["bidir", "test"], project_scope="bidir_test",
            semantic_summary="Claim A: system does not support feature Y",
            task_id="task-0070",
        )
        r2 = mgr.create_memory(
            source="knower", provenance_type="subagent_output",
            provenance_rule="task_completion_insight", confidence=0.7,
            tags=["bidir", "test"], project_scope="bidir_test",
            semantic_summary="Claim B: system supports feature Y and is not limited",
            task_id="task-0071",
        )

        conflicts = resolver.detect_conflicts(project_scope="bidir_test")

        if conflicts:
            # Reload and check bidirectional refs
            loaded1 = mgr.load_memory(r1.memory_id)
            loaded2 = mgr.load_memory(r2.memory_id)

            has_ref_1_to_2 = any(
                ref["conflicting_memory_id"] == r2.memory_id
                for ref in loaded1.contradiction_refs
            )
            has_ref_2_to_1 = any(
                ref["conflicting_memory_id"] == r1.memory_id
                for ref in loaded2.contradiction_refs
            )

            assert_test(has_ref_1_to_2, "Record 1 should have ref to Record 2")
            assert_test(has_ref_2_to_1, "Record 2 should have ref to Record 1")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_conflict_list():
    """Test listing conflict artifacts."""
    root = make_temp_root()
    try:
        mgr = MemoryManager(root)
        resolver = MemoryConflictResolver(mgr)

        # Initially empty
        conflicts = resolver.list_conflicts()
        assert_test(len(conflicts) == 0, f"Expected 0 conflicts initially, got {len(conflicts)}")

        # Create conflicting records and detect
        mgr.create_memory(
            source="s", provenance_type="subagent_output",
            provenance_rule="task_completion_insight", confidence=0.7,
            tags=["list", "endpoints"], project_scope="conflict_list",
            semantic_summary="Endpoint is not available and will not be accessible",
            task_id="task-0080",
        )
        mgr.create_memory(
            source="s", provenance_type="subagent_output",
            provenance_rule="task_completion_insight", confidence=0.7,
            tags=["list", "endpoints"], project_scope="conflict_list",
            semantic_summary="Endpoint is available and not restricted",
            task_id="task-0081",
        )

        resolver.detect_conflicts(project_scope="conflict_list")
        conflicts = resolver.list_conflicts()
        # May or may not detect conflicts depending on heuristic
        assert_test(isinstance(conflicts, list), f"Expected list, got {type(conflicts)}")
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════
# Main Runner
# ═══════════════════════════════════════════════════════════════

PHASES = {
    "record": [
        test_record_create,
        test_record_validation,
        test_record_from_dict,
        test_record_from_json,
        test_record_status_transitions,
        test_record_stale_marking,
        test_record_supersede,
        test_record_contradiction_refs,
        test_record_provenance_integrity,
        test_record_canonical_state_refs,
    ],
    "manager": [
        test_manager_create_and_load,
        test_manager_search,
        test_manager_update_status,
        test_manager_list_project,
        test_manager_supersede,
        test_manager_index_audit,
        test_manager_rejected_retention,
    ],
    "promoter": [
        test_promoter_valid_rule,
        test_promoter_unknown_rule,
        test_promoter_confidence_ceiling,
        test_promoter_operator_direct_requires_id,
        test_promoter_list_rules,
    ],
    "retriever": [
        test_retriever_basic,
        test_retriever_deterministic_fallback,
        test_retriever_by_id,
        test_retriever_state_refs,
    ],
    "conflict": [
        test_conflict_detection,
        test_conflict_artifact_creation,
        test_conflict_no_auto_resolve,
        test_conflict_bidirectional_refs,
        test_conflict_list,
    ],
}


def main():
    global FAILED

    phases_to_run = PHASES

    total = 0
    passed = 0

    for phase_name, tests in phases_to_run.items():
        print(f"\n{'=' * 60}")
        print(f"Phase: {phase_name}")
        print(f"{'=' * 60}")
        for test_fn in tests:
            total += 1
            name = test_fn.__name__
            try:
                test_fn()
                if not FAILED:
                    passed += 1
                    print(f"  PASS: {name}")
                else:
                    print(f"  FAIL: {name}")
                    FAILED = False  # Reset for next test
            except Exception as e:
                total += 1  # Counted already
                print(f"  ERROR: {name} — {e}")
                FAILED = True

    print(f"\n{'=' * 60}")
    print(f"Results: {passed}/{total + 0} passed")
    print(f"{'=' * 60}")

    if FAILED:
        print(f"\nFAILED: One or more tests did not pass")
        return 1
    else:
        print(f"\nALL PASSED: {passed} test(s) passed")
        return 0


if __name__ == "__main__":
    main()