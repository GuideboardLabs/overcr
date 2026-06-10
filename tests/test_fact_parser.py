"""Tests for fact_parser.py."""
import sys, os
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

if __name__ == "__main__":
    test_bullet_kind_parsing()
    test_missing_kind_stays_na()
    print("All fact_parser kind tests PASS")