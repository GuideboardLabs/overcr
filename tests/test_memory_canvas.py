#!/usr/bin/env python3
"""
OverCR v2.2.0 — Symbolic Memory Canvas Tests

Coverage:
  - CanvasNode: create, validation, from_dict, offload/archive/reactivate,
    serialization, ID generation, ref path
  - CanvasEdge: create, validation, from_dict, serialization
  - MemoryCanvas: add_node (with/without raw_text), get_node, retrieve_raw,
    list_nodes, archive/reactivate, add_edge, list_edges, remove_edge,
    render (Mermaid), render_compact, context_size_estimate, clear,
    persistence, audit index, self-loop rejection, duplicate edge prevention

Run:
    python3 tests/test_memory_canvas.py
    python3 tests/test_memory_canvas.py --phase node
    python3 tests/test_memory_canvas.py --phase edge
    python3 tests/test_memory_canvas.py --phase canvas
"""

import json
import shutil
import sys
import tempfile
from pathlib import Path

# Ensure project root is on sys.path
OVERCR_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(OVERCR_ROOT))

from memory.memory_canvas import (
    CanvasNode, CanvasEdge, MemoryCanvas,
    VALID_NODE_TYPES, VALID_EDGE_TYPES, NODE_ID_PATTERN,
)

FAILED = False


def assert_test(condition, msg):
    global FAILED
    if not condition:
        print(f"  FAIL: {msg}")
        FAILED = True


def make_temp_root():
    return tempfile.mkdtemp(prefix="overcr-canvas-test-")


# ═══════════════════════════════════════════════════════════════
# Phase 1: CanvasNode
# ═══════════════════════════════════════════════════════════════

def test_node_create():
    """Test CanvasNode.create() produces valid nodes."""
    n = CanvasNode.create(
        label="search_api",
        node_type="tool_call",
        detail="Searched API docs for rate limiting",
    )
    assert_test(NODE_ID_PATTERN.match(n.node_id), f"Bad node_id: {n.node_id}")
    assert_test(n.label == "search_api", f"Bad label: {n.label}")
    assert_test(n.node_type == "tool_call", f"Bad type: {n.node_type}")
    assert_test(n.detail == "Searched API docs for rate limiting", f"Bad detail: {n.detail}")
    assert_test(n.status == "active", f"Bad status: {n.status}")
    assert_test(n.ref_path == f"refs/{n.node_id}.md", f"Bad ref_path: {n.ref_path}")


def test_node_create_with_explicit_id():
    """Test CanvasNode.create() with explicit node_id."""
    n = CanvasNode.create(
        label="start",
        node_type="task_start",
        detail="Task started",
        node_id="n-abcd1234",
    )
    assert_test(n.node_id == "n-abcd1234", f"Bad node_id: {n.node_id}")


def test_node_validation():
    """Test CanvasNode validation catches bad inputs."""
    # Bad node_type
    try:
        CanvasNode.create(label="s", node_type="invalid", detail="d")
        assert_test(False, "Should reject bad node_type")
    except ValueError:
        pass

    # Empty label
    try:
        CanvasNode.create(label="", node_type="tool_call", detail="d")
        assert_test(False, "Should reject empty label")
    except ValueError:
        pass

    # Label too long
    try:
        CanvasNode.create(label="x" * 129, node_type="tool_call", detail="d")
        assert_test(False, "Should reject label > 128 chars")
    except ValueError:
        pass

    # Empty detail
    try:
        CanvasNode.create(label="s", node_type="tool_call", detail="")
        assert_test(False, "Should reject empty detail")
    except ValueError:
        pass

    # Detail too long
    try:
        CanvasNode.create(label="s", node_type="tool_call", detail="x" * 513)
        assert_test(False, "Should reject detail > 512 chars")
    except ValueError:
        pass

    # Bad node_id format
    try:
        CanvasNode.create(label="s", node_type="tool_call", detail="d", node_id="bad-id")
        assert_test(False, "Should reject bad node_id format")
    except ValueError:
        pass


def test_node_from_dict():
    """Test CanvasNode.from_dict() reconstruction."""
    n = CanvasNode.create(
        label="test", node_type="decision", detail="Decided to proceed",
    )
    d = n.to_dict()
    n2 = CanvasNode.from_dict(d)
    assert_test(n2.node_id == n.node_id, "ID mismatch")
    assert_test(n2.label == n.label, "Label mismatch")
    assert_test(n2.node_type == n.node_type, "Type mismatch")
    assert_test(n2.detail == n.detail, "Detail mismatch")


def test_node_from_json():
    """Test JSON round-trip."""
    n = CanvasNode.create(
        label="json_test", node_type="milestone", detail="Milestone reached",
    )
    json_str = n.to_json()
    n2 = CanvasNode.from_dict(json.loads(json_str))
    assert_test(n2.node_id == n.node_id, "JSON round-trip ID mismatch")
    assert_test(n2.label == n.label, "JSON round-trip label mismatch")


def test_node_offload():
    """Test offload transitions node to offloaded status."""
    n = CanvasNode.create(label="s", node_type="tool_call", detail="d")
    assert_test(n.status == "active", f"Expected active, got {n.status}")
    n.offload()
    assert_test(n.status == "offloaded", f"Expected offloaded, got {n.status}")


def test_node_archive():
    """Test archive transitions node to archived status."""
    n = CanvasNode.create(label="s", node_type="tool_call", detail="d")
    n.archive()
    assert_test(n.status == "archived", f"Expected archived, got {n.status}")


def test_node_reactivate():
    """Test reactivating an archived node."""
    n = CanvasNode.create(label="s", node_type="tool_call", detail="d")
    n.archive()
    assert_test(n.status == "archived", f"Expected archived: {n.status}")
    n.reactivate()
    assert_test(n.status == "active", f"Expected active after reactivate: {n.status}")

    # Can't reactivate non-archived
    try:
        n.reactivate()
        assert_test(False, "Should reject reactivating active node")
    except ValueError:
        pass


def test_node_all_types():
    """Test all valid node types."""
    for ntype in VALID_NODE_TYPES:
        n = CanvasNode.create(label="s", node_type=ntype, detail="d")
        assert_test(n.node_type == ntype, f"Bad type for {ntype}: {n.node_type}")


# ═══════════════════════════════════════════════════════════════
# Phase 2: CanvasEdge
# ═══════════════════════════════════════════════════════════════

def test_edge_create():
    """Test CanvasEdge.create() produces valid edges."""
    e = CanvasEdge.create("n-aaaa1111", "n-bbbb2222", "next", label="proceed")
    assert_test(e.from_id == "n-aaaa1111", f"Bad from: {e.from_id}")
    assert_test(e.to_id == "n-bbbb2222", f"Bad to: {e.to_id}")
    assert_test(e.edge_type == "next", f"Bad type: {e.edge_type}")
    assert_test(e.label == "proceed", f"Bad label: {e.label}")


def test_edge_validation():
    """Test CanvasEdge validation."""
    # Bad from_id
    try:
        CanvasEdge.create("bad", "n-bbbb2222", "next")
        assert_test(False, "Should reject bad from_id")
    except ValueError:
        pass

    # Bad to_id
    try:
        CanvasEdge.create("n-aaaa1111", "bad", "next")
        assert_test(False, "Should reject bad to_id")
    except ValueError:
        pass

    # Bad edge_type
    try:
        CanvasEdge.create("n-aaaa1111", "n-bbbb2222", "invalid")
        assert_test(False, "Should reject bad edge_type")
    except ValueError:
        pass


def test_edge_all_types():
    """Test all valid edge types."""
    for etype in VALID_EDGE_TYPES:
        e = CanvasEdge.create("n-aaaa1111", "n-bbbb2222", etype)
        assert_test(e.edge_type == etype, f"Bad type for {etype}: {e.edge_type}")


def test_edge_from_dict():
    """Test CanvasEdge.from_dict() reconstruction."""
    e = CanvasEdge.create("n-aaaa1111", "n-bbbb2222", "retry", label="retry after error")
    d = e.to_dict()
    e2 = CanvasEdge.from_dict(d)
    assert_test(e2.from_id == e.from_id, "from_id mismatch")
    assert_test(e2.to_id == e.to_id, "to_id mismatch")
    assert_test(e2.edge_type == e.edge_type, "edge_type mismatch")
    assert_test(e2.label == e.label, "label mismatch")


# ═══════════════════════════════════════════════════════════════
# Phase 3: MemoryCanvas
# ═══════════════════════════════════════════════════════════════

def test_canvas_add_node_no_raw():
    """Test adding a node without raw_text (stays active)."""
    root = make_temp_root()
    try:
        canvas = MemoryCanvas(root=root, session_id="test-001")
        n = canvas.add_node(
            label="start",
            node_type="task_start",
            detail="Task initialized",
        )
        assert_test(n.status == "active", f"Expected active, got {n.status}")

        # No ref file should exist
        ref_path = canvas.refs_dir / f"{n.node_id}.md"
        assert_test(not ref_path.exists(), "Ref file should not exist without raw_text")

        # State should have the node
        node = canvas.get_node(n.node_id)
        assert_test(node is not None, "Node not found in state")
        assert_test(node.label == "start", f"Bad label: {node.label}")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_canvas_add_node_with_raw():
    """Test adding a node with raw_text (gets offloaded)."""
    root = make_temp_root()
    try:
        canvas = MemoryCanvas(root=root, session_id="test-002")
        raw = "x" * 50000  # 50KB of raw tool output
        n = canvas.add_node(
            label="search",
            node_type="tool_call",
            detail="Searched 500 docs",
            raw_text=raw,
        )
        assert_test(n.status == "offloaded", f"Expected offloaded, got {n.status}")

        # Ref file should exist with raw text
        ref_path = canvas.refs_dir / f"{n.node_id}.md"
        assert_test(ref_path.exists(), f"Ref file not created: {ref_path}")

        # Retrieve raw
        retrieved = canvas.retrieve_raw(n.node_id)
        assert_test(retrieved is not None, "Should retrieve raw text")
        assert_test(len(retrieved) == 50000, f"Bad raw length: {len(retrieved)}")
        assert_test(retrieved == raw, "Raw text mismatch")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_canvas_retrieve_raw_nonexistent():
    """Test retrieve_raw returns None for nonexistent node."""
    root = make_temp_root()
    try:
        canvas = MemoryCanvas(root=root, session_id="test-003")
        result = canvas.retrieve_raw("n-nonexist0")
        assert_test(result is None, f"Expected None, got {result}")

        # Bad ID format
        result = canvas.retrieve_raw("bad-id")
        assert_test(result is None, "Should return None for bad ID format")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_canvas_list_nodes():
    """Test listing nodes with and without status filter."""
    root = make_temp_root()
    try:
        canvas = MemoryCanvas(root=root, session_id="test-004")
        n1 = canvas.add_node(label="a", node_type="task_start", detail="start")
        n2 = canvas.add_node(label="b", node_type="tool_call", detail="tool", raw_text="raw")
        n3 = canvas.add_node(label="c", node_type="milestone", detail="done")
        canvas.archive_node(n3.node_id)

        all_nodes = canvas.list_nodes()
        assert_test(len(all_nodes) == 3, f"Expected 3 nodes, got {len(all_nodes)}")

        active = canvas.list_nodes(status_filter="active")
        assert_test(len(active) == 1, f"Expected 1 active, got {len(active)}")

        offloaded = canvas.list_nodes(status_filter="offloaded")
        assert_test(len(offloaded) == 1, f"Expected 1 offloaded, got {len(offloaded)}")

        archived = canvas.list_nodes(status_filter="archived")
        assert_test(len(archived) == 1, f"Expected 1 archived, got {len(archived)}")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_canvas_archive_and_reactivate():
    """Test archiving and reactivating nodes."""
    root = make_temp_root()
    try:
        canvas = MemoryCanvas(root=root, session_id="test-005")
        n = canvas.add_node(label="x", node_type="tool_call", detail="d", raw_text="raw")

        archived = canvas.archive_node(n.node_id)
        assert_test(archived is not None, "archive_node should return node")
        assert_test(archived.status == "archived", f"Expected archived: {archived.status}")

        reactivated = canvas.reactivate_node(n.node_id)
        assert_test(reactivated is not None, "reactivate_node should return node")
        assert_test(reactivated.status == "active", f"Expected active: {reactivated.status}")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_canvas_archive_nonexistent():
    """Test archiving a nonexistent node returns None."""
    root = make_temp_root()
    try:
        canvas = MemoryCanvas(root=root, session_id="test-006")
        result = canvas.archive_node("n-nonexist0")
        assert_test(result is None, f"Expected None, got {result}")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_canvas_add_edge():
    """Test adding edges between nodes."""
    root = make_temp_root()
    try:
        canvas = MemoryCanvas(root=root, session_id="test-007")
        n1 = canvas.add_node(label="start", node_type="task_start", detail="begin")
        n2 = canvas.add_node(label="search", node_type="tool_call", detail="ran search", raw_text="output")

        e = canvas.add_edge(n1.node_id, n2.node_id, "next")
        assert_test(e.from_id == n1.node_id, "Bad from_id")
        assert_test(e.to_id == n2.node_id, "Bad to_id")

        edges = canvas.list_edges()
        assert_test(len(edges) == 1, f"Expected 1 edge, got {len(edges)}")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_canvas_edge_self_loop():
    """Test that self-loops are rejected."""
    root = make_temp_root()
    try:
        canvas = MemoryCanvas(root=root, session_id="test-008")
        n = canvas.add_node(label="s", node_type="task_start", detail="d")
        try:
            canvas.add_edge(n.node_id, n.node_id, "next")
            assert_test(False, "Should reject self-loop")
        except ValueError:
            pass
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_canvas_edge_nonexistent_nodes():
    """Test that edges to nonexistent nodes are rejected."""
    root = make_temp_root()
    try:
        canvas = MemoryCanvas(root=root, session_id="test-009")
        n = canvas.add_node(label="s", node_type="task_start", detail="d")
        try:
            canvas.add_edge(n.node_id, "n-nonexist0", "next")
            assert_test(False, "Should reject edge to nonexistent node")
        except ValueError:
            pass

        try:
            canvas.add_edge("n-nonexist0", n.node_id, "next")
            assert_test(False, "Should reject edge from nonexistent node")
        except ValueError:
            pass
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_canvas_duplicate_edge():
    """Test that duplicate edges are silently ignored."""
    root = make_temp_root()
    try:
        canvas = MemoryCanvas(root=root, session_id="test-010")
        n1 = canvas.add_node(label="a", node_type="task_start", detail="d1")
        n2 = canvas.add_node(label="b", node_type="tool_call", detail="d2")

        canvas.add_edge(n1.node_id, n2.node_id, "next")
        canvas.add_edge(n1.node_id, n2.node_id, "next")  # duplicate

        edges = canvas.list_edges()
        assert_test(len(edges) == 1, f"Expected 1 edge (dedup), got {len(edges)}")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_canvas_remove_edge():
    """Test removing edges."""
    root = make_temp_root()
    try:
        canvas = MemoryCanvas(root=root, session_id="test-011")
        n1 = canvas.add_node(label="a", node_type="task_start", detail="d1")
        n2 = canvas.add_node(label="b", node_type="tool_call", detail="d2")
        canvas.add_edge(n1.node_id, n2.node_id, "next")

        removed = canvas.remove_edge(n1.node_id, n2.node_id)
        assert_test(removed, "Should return True for removed edge")

        edges = canvas.list_edges()
        assert_test(len(edges) == 0, f"Expected 0 edges, got {len(edges)}")

        # Remove again — should return False
        removed = canvas.remove_edge(n1.node_id, n2.node_id)
        assert_test(not removed, "Should return False for nonexistent edge")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_canvas_render():
    """Test Mermaid graph rendering."""
    root = make_temp_root()
    try:
        canvas = MemoryCanvas(root=root, session_id="test-012")
        n1 = canvas.add_node(label="Start Task", node_type="task_start", detail="begin")
        n2 = canvas.add_node(label="Search API", node_type="tool_call", detail="ran search", raw_text="output")
        canvas.add_edge(n1.node_id, n2.node_id, "next")

        mermaid = canvas.render()
        assert_test("graph LR" in mermaid, "Missing graph LR header")
        assert_test(n1.node_id.replace("-", "_") in mermaid, "Missing node 1 in render")
        assert_test(n2.node_id.replace("-", "_") in mermaid, "Missing node 2 in render")
        assert_test("-->" in mermaid, "Missing edge in render")
        assert_test("Start Task" in mermaid, "Missing label in render")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_canvas_render_excludes_archived():
    """Test that render() excludes archived nodes by default."""
    root = make_temp_root()
    try:
        canvas = MemoryCanvas(root=root, session_id="test-013")
        n1 = canvas.add_node(label="active", node_type="task_start", detail="d1")
        n2 = canvas.add_node(label="archived", node_type="tool_call", detail="d2")
        canvas.archive_node(n2.node_id)

        mermaid = canvas.render()
        # The classDef line always mentions "archived" for styling,
        # but the node label "archived" should not appear as a node entry
        from memory.memory_canvas import _escape_mermaid
        archived_mid = n2.node_id.replace("-", "_")
        assert_test(archived_mid not in mermaid, "Archived node ID should not be in default render")
        assert_test("active" in mermaid, "Active node should be in render")

        # With include_archived=True
        mermaid_all = canvas.render(include_archived=True)
        assert_test(archived_mid in mermaid_all, "Archived node should appear with include_archived=True")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_canvas_render_compact():
    """Test compact text rendering."""
    root = make_temp_root()
    try:
        canvas = MemoryCanvas(root=root, session_id="test-014")
        n1 = canvas.add_node(label="Start", node_type="task_start", detail="begin")
        n2 = canvas.add_node(label="Search", node_type="tool_call", detail="ran search", raw_text="x" * 1000)
        canvas.add_edge(n1.node_id, n2.node_id, "next")

        compact = canvas.render_compact()
        assert_test(n1.node_id in compact, "Missing node 1 ID in compact")
        assert_test(n2.node_id in compact, "Missing node 2 ID in compact")
        assert_test("[offloaded]" in compact, "Missing offloaded marker in compact")
        assert_test("--next-->" in compact, "Missing edge in compact")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_canvas_context_size_estimate():
    """Test token savings estimation."""
    root = make_temp_root()
    try:
        canvas = MemoryCanvas(root=root, session_id="test-015")
        # Add a node with lots of raw text
        canvas.add_node(
            label="big_search", node_type="tool_call", detail="searched 1000 docs",
            raw_text="x" * 100000,  # 100KB
        )
        canvas.add_node(
            label="small", node_type="decision", detail="decided to proceed",
        )

        estimate = canvas.context_size_estimate()
        assert_test(estimate["node_count"] == 2, f"Bad node_count: {estimate['node_count']}")
        assert_test(estimate["offloaded_count"] == 1, f"Bad offloaded: {estimate['offloaded_count']}")
        assert_test(estimate["full_raw_chars"] > 100000, f"Raw chars too low: {estimate['full_raw_chars']}")
        assert_test(estimate["canvas_chars"] < estimate["full_raw_chars"],
                    f"Canvas should be smaller: {estimate['canvas_chars']} vs {estimate['full_raw_chars']}")
        assert_test(estimate["estimated_savings_pct"] > 90, f"Savings too low: {estimate['estimated_savings_pct']}%")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_canvas_persistence():
    """Test that canvas state persists across instances."""
    root = make_temp_root()
    try:
        canvas1 = MemoryCanvas(root=root, session_id="test-016")
        n = canvas1.add_node(label="persist", node_type="task_start", detail="persistence test", raw_text="raw data")

        # New instance, same session
        canvas2 = MemoryCanvas(root=root, session_id="test-016")
        node = canvas2.get_node(n.node_id)
        assert_test(node is not None, "Node not found in new instance")
        assert_test(node.label == "persist", f"Bad label after reload: {node.label}")

        raw = canvas2.retrieve_raw(n.node_id)
        assert_test(raw == "raw data", f"Raw text not persisted: {raw}")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_canvas_audit_index():
    """Test that the audit index accumulates entries."""
    root = make_temp_root()
    try:
        canvas = MemoryCanvas(root=root, session_id="test-017")
        n = canvas.add_node(label="audit", node_type="task_start", detail="audit test")
        canvas.archive_node(n.node_id)

        assert_test(canvas.index_path.exists(), "Index file not created")

        with open(canvas.index_path, "r") as f:
            lines = f.readlines()
        assert_test(len(lines) >= 2, f"Expected at least 2 index entries, got {len(lines)}")

        first = json.loads(lines[0])
        assert_test(first["action"] == "node_added", f"Expected node_added: {first['action']}")

        second = json.loads(lines[1])
        assert_test(second["action"] == "node_archived", f"Expected node_archived: {second['action']}")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_canvas_graph_file_generated():
    """Test that graph.mmd is generated and updated."""
    root = make_temp_root()
    try:
        canvas = MemoryCanvas(root=root, session_id="test-018")
        canvas.add_node(label="g1", node_type="task_start", detail="graph test")

        assert_test(canvas.graph_path.exists(), "Graph file not generated")

        with open(canvas.graph_path, "r") as f:
            content = f.read()
        assert_test("graph LR" in content, "Graph file missing header")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_canvas_clear_all():
    """Test clearing the entire canvas."""
    root = make_temp_root()
    try:
        canvas = MemoryCanvas(root=root, session_id="test-019")
        n = canvas.add_node(label="x", node_type="task_start", detail="d", raw_text="raw")

        canvas.clear(keep_archived=False)

        nodes = canvas.list_nodes()
        assert_test(len(nodes) == 0, f"Expected 0 nodes after clear, got {len(nodes)}")

        # Ref file should be gone
        ref_path = canvas.refs_dir / f"{n.node_id}.md"
        assert_test(not ref_path.exists(), "Ref file should be deleted after clear")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_canvas_clear_keep_archived():
    """Test clearing while keeping archived nodes."""
    root = make_temp_root()
    try:
        canvas = MemoryCanvas(root=root, session_id="test-020")
        n1 = canvas.add_node(label="active", node_type="task_start", detail="d1")
        n2 = canvas.add_node(label="archived", node_type="tool_call", detail="d2", raw_text="raw2")
        canvas.archive_node(n2.node_id)

        canvas.clear(keep_archived=True)

        nodes = canvas.list_nodes()
        assert_test(len(nodes) == 1, f"Expected 1 node (archived), got {len(nodes)}")
        assert_test(nodes[0].status == "archived", f"Expected archived, got {nodes[0].status}")

        # Archived ref should still exist
        raw = canvas.retrieve_raw(n2.node_id)
        assert_test(raw == "raw2", f"Archived ref not kept: {raw}")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_canvas_mermaid_escape():
    """Test that special characters are escaped in Mermaid output."""
    root = make_temp_root()
    try:
        canvas = MemoryCanvas(root=root, session_id="test-021")
        n = canvas.add_node(
            label='Search "quoted" [bracketed]',
            node_type="tool_call",
            detail='detail with | pipe char',
        )
        mermaid = canvas.render()
        # Should not contain unescaped quotes or brackets that break Mermaid
        assert_test('"quoted"' not in mermaid, "Unescaped quotes in Mermaid")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_canvas_multi_session_isolation():
    """Test that different sessions have isolated canvases."""
    root = make_temp_root()
    try:
        c1 = MemoryCanvas(root=root, session_id="session-a")
        c2 = MemoryCanvas(root=root, session_id="session-b")

        n1 = c1.add_node(label="a", node_type="task_start", detail="in session a")
        n2 = c2.add_node(label="b", node_type="task_start", detail="in session b")

        # Session A should only see n1
        assert_test(c1.get_node(n2.node_id) is None, "Session A leaked into session B")
        assert_test(c2.get_node(n1.node_id) is None, "Session B leaked into session A")

        # Each should see its own
        assert_test(c1.get_node(n1.node_id) is not None, "Session A missing its own node")
        assert_test(c2.get_node(n2.node_id) is not None, "Session B missing its own node")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_canvas_retry_edge_render():
    """Test that retry edges render as dashed lines."""
    root = make_temp_root()
    try:
        canvas = MemoryCanvas(root=root, session_id="test-022")
        n1 = canvas.add_node(label="fail", node_type="error", detail="tool failed")
        n2 = canvas.add_node(label="retry", node_type="tool_call", detail="retrying")
        canvas.add_edge(n1.node_id, n2.node_id, "retry", label="after fix")

        mermaid = canvas.render()
        # Retry edges should use dashed line syntax (-.)
        assert_test("-." in mermaid, "Retry edge should use dashed line syntax")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_canvas_branch_edge_render():
    """Test that branch edges render with labels."""
    root = make_temp_root()
    try:
        canvas = MemoryCanvas(root=root, session_id="test-023")
        n1 = canvas.add_node(label="decision", node_type="decision", detail="choose path")
        n2 = canvas.add_node(label="path_a", node_type="tool_call", detail="path A")
        canvas.add_edge(n1.node_id, n2.node_id, "branch", label="if condition")

        mermaid = canvas.render()
        assert_test("if condition" in mermaid, "Branch label missing in render")
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════
# Main Runner
# ═══════════════════════════════════════════════════════════════

PHASES = {
    "node": [
        test_node_create,
        test_node_create_with_explicit_id,
        test_node_validation,
        test_node_from_dict,
        test_node_from_json,
        test_node_offload,
        test_node_archive,
        test_node_reactivate,
        test_node_all_types,
    ],
    "edge": [
        test_edge_create,
        test_edge_validation,
        test_edge_all_types,
        test_edge_from_dict,
    ],
    "canvas": [
        test_canvas_add_node_no_raw,
        test_canvas_add_node_with_raw,
        test_canvas_retrieve_raw_nonexistent,
        test_canvas_list_nodes,
        test_canvas_archive_and_reactivate,
        test_canvas_archive_nonexistent,
        test_canvas_add_edge,
        test_canvas_edge_self_loop,
        test_canvas_edge_nonexistent_nodes,
        test_canvas_duplicate_edge,
        test_canvas_remove_edge,
        test_canvas_render,
        test_canvas_render_excludes_archived,
        test_canvas_render_compact,
        test_canvas_context_size_estimate,
        test_canvas_persistence,
        test_canvas_audit_index,
        test_canvas_graph_file_generated,
        test_canvas_clear_all,
        test_canvas_clear_keep_archived,
        test_canvas_mermaid_escape,
        test_canvas_multi_session_isolation,
        test_canvas_retry_edge_render,
        test_canvas_branch_edge_render,
    ],
}


def main():
    global FAILED

    total = 0
    passed = 0

    for phase_name, tests in PHASES.items():
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
                    FAILED = False
            except Exception as e:
                print(f"  ERROR: {name} - {e}")
                FAILED = True

    print(f"\n{'=' * 60}")
    print(f"Results: {passed}/{total} passed")
    print(f"{'=' * 60}")

    if FAILED:
        print(f"\nFAILED: One or more tests did not pass")
        return 1
    else:
        print(f"\nALL PASSED: {passed} test(s) passed")
        return 0


if __name__ == "__main__":
    sys.exit(main())