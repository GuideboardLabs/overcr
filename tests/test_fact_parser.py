"""Tests for fact_parser.py."""
import sys, os
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from knowledge.vault.fact_parser import parse_text

def test_bullet_kind_parsing():
    """Bullet facts with kind: prefix parse the kind correctly."""
    text = """<!--- overcr:facts:begin -->
- [domain::key] kind:rejected This approach failed
- [domain::key] kind:next_action Run the tests
- [domain::key] normal claim without kind
<!--- overcr:facts:end -->"""
    facts = parse_text(text)
    assert len(facts) == 3, f"Expected 3 facts, got {len(facts)}"
    
    # Find facts by kind
    rejected = [f for f in facts if f.get("kind") == "rejected"]
    next_act = [f for f in facts if f.get("kind") == "next_action"]
    normal = [f for f in facts if f.get("kind") in ("n/a", "fact")]
    
    assert len(rejected) == 1, f"Expected 1 rejected, got {len(rejected)}"
    assert "failed" in rejected[0]["claim"]
    assert len(next_act) == 1, f"Expected 1 next_action, got {len(next_act)}"
    assert "Run" in next_act[0]["claim"]
    print("  [PASS] test_bullet_kind_parsing")

def test_missing_kind_stays_na():
    """Facts without kind: prefix keep kind='n/a'."""
    text = """<!--- overcr:facts:begin -->
- [domain::key] plain fact
- [other::key] another one
<!--- overcr:facts:end -->"""
    facts = parse_text(text)
    assert len(facts) == 2
    for f in facts:
        assert f.get("kind") == "n/a", f"Expected kind='n/a', got '{f.get('kind')}'"
    print("  [PASS] test_missing_kind_stays_na")

def test_search_by_kind():
    """VaultIndex.search() with kind filter returns only matching facts."""
    import tempfile
    from knowledge.vault.vault_adapter import VaultIndex

    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        idx = VaultIndex(str(vault))

        # Create a note with mixed kind facts
        note = vault / "test-note.md"
        note.write_text("""---
tags: [test]
---
<!--- overcr:facts:begin -->
- [test::approach] kind:rejected This approach failed
- [test::approach] kind:next_action Run tests first
- [test::approach] normal fact
<!--- overcr:facts:end -->""")

        idx.rebuild()

        # Search by kind
        rejected = idx.search(tags=["test"], kind="rejected")
        assert len(rejected) == 1, f"Expected 1 rejected, got {len(rejected)}"
        assert "failed" in rejected[0]["claim"]

        next_act = idx.search(tags=["test"], kind="next_action")
        assert len(next_act) == 1, f"Expected 1 next_action, got {len(next_act)}"
        assert "Run" in next_act[0]["claim"]

        normal = idx.search(tags=["test"], kind="n/a")
        assert len(normal) >= 1, f"Expected at least 1 n/a fact, got {len(normal)}"

    print("  [PASS] test_search_by_kind")

def test_multiline_claims():
    """Multi-line claims (text spanning multiple lines after kind: prefix) parse correctly."""
    # Multi-line claims use backslash continuation: claim\
    text = """<!--- overcr:facts:begin -->

    - [domain::multiline] kind:next_action This is a multi-line claim\\
        It spans several lines before the next bullet.
    
    - [domain::multiline2] kind:next_action Another multi-line rejection\\
        With multiple paragraphs.
        And more text here.
    
    - [domain::single] kind:fact Single line claim
    
    <!--- overcr:facts:end -->"""

    facts = parse_text(text)
    assert len(facts) == 3, f"Expected 3 facts, got {len(facts)}"
    
    # Find next_action facts
    next_acts = [f for f in facts if f.get("kind") == "next_action"]
    assert len(next_acts) == 2, f"Expected 2 next_action facts, got {len(next_acts)}"
    
    # First multi-line claim
    claim1 = next_acts[0]["claim"]
    assert "This is a multi-line claim" in claim1, "First multi-line claim not parsed correctly"
    assert "spans several lines" in claim1, "Multi-line content truncated"
    
    # Second multi-line claim  
    claim2 = next_acts[1]["claim"]
    assert "Another multi-line rejection" in claim2, "Second multi-line claim not parsed"
    assert "multiple paragraphs" in claim2, "Multi-line content truncated"
    assert "And more text here" in claim2, "Full multi-line claim not captured"
    
    # Single line fact
    single = [f for f in facts if f.get("kind") == "fact"][0]
    assert "domain::single" in single["claim"], "Single line fact not parsed correctly"
    assert "Single line claim" in single["claim"], "Single line claim text missing"
    
    print("  [PASS] test_multiline_claims")