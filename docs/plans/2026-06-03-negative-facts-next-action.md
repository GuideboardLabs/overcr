# Negative Facts & Next-Action Tracking — Implementation Plan (v2.11.1)

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Add structured "what didn't work" (rejected approaches) and "what to do next" (next-action) fact types to OverCR's vault-grounded memory, so agents stop retrying failed branches and can resume work between sessions.

**Architecture:** Two-layer. Layer 1 extends the vault fact parser and index to support kind-filtered facts. Layer 2 extends the runtime to inject these facts as guidance context during task creation. Filesystem-first, zero DB, backward-compatible with all existing facts fences.

**Tech Stack:** Python 3.11 stdlib, existing OverCR fact_parser.py and vault_adapter.py. No new dependencies.

---

### Task 1: Add kind prefix parsing to bullet-format facts

**Objective:** Parse optional `kind:` prefix from bullet-format fact claims so facts can be tagged as `rejected` or `next_action` (or any future kind).

**Files:**
- Modify: `knowledge/vault/fact_parser.py:99-142`
- Test: no separate test file yet — create `tests/test_fact_parser.py`

**Step 1: Write failing test for kind prefix parsing**

Create `tests/test_fact_parser.py`:

```python
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
```

**Step 2: Run test to verify failure**

Run: `python3 tests/test_fact_parser.py`
Expected: FAIL — the kind prefix is not yet parsed.

**Step 3: Modify fact_parser.py bullet parsing**

In `knowledge/vault/fact_parser.py`, modify the bullet row handler (around line 127-141):

```python
# After BULLET_ROW match in _parse_fence_body
b = BULLET_ROW.match(line)
if b:
    raw_key = b.group(1).strip()
    raw_claim = b.group(2).strip()
    
    # Parse optional kind: prefix from claim
    kind = "n/a"
    claim = raw_claim
    kind_match = re.match(r"^kind:(\w+)\s+(.*)", raw_claim)
    if kind_match:
        kind = kind_match.group(1).strip()
        claim = kind_match.group(2).strip()
    
    facts.append({
        "line": 0,
        "claim": f"[{raw_key}] {claim}",
        "kind": kind,
        "confidence": None,
        "value": "",
        "unit": "",
        "source": "",
        "context": "",
        "fact_key": raw_key,
    })
```

Add the `import re` at the top of the file (already present — verify).

**Step 4: Run test to verify pass**

Run: `python3 tests/test_fact_parser.py`
Expected: PASS — both tests pass.

**Step 5: Update test runner**

Add `test_fact_parser.py` to the test suite runner so it gets picked up:

```bash
# Add import/run lines to tests/run_all.py or create an entry
echo "import test_fact_parser; test_fact_parser.test_bullet_kind_parsing(); test_fact_parser.test_missing_kind_stays_na()" >> /dev/null
```

Actually, check how run_all.py works first:

```bash
grep -n 'import\|run\|exec\|subprocess\|pytest' tests/run_all.py | head -20
```

Then add the test module there.

**Step 6: Commit**

```bash
cd ~/Documents/overcr
git add tests/test_fact_parser.py knowledge/vault/fact_parser.py
git commit -m "feat: parse optional kind: prefix from bullet-format facts"
```

---

### Task 2: Add kind filter to VaultIndex.search()

**Objective:** Allow searching facts by kind (e.g., only `rejected` or only `next_action`) so the runtime can selectively inject guidance context.

**Files:**
- Modify: `knowledge/vault/vault_adapter.py` — add `kind` parameter to `search()` method
- Test: add kind search tests to `tests/test_fact_parser.py` (or new test file for vault)

**Step 1: Write failing test**

Append to `tests/test_fact_parser.py`:

```python
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
```

Add the import at top: `from pathlib import Path`

Run: `python3 tests/test_fact_parser.py`
Expected: FAIL — `search()` doesn't have a `kind` parameter yet.

**Step 2: Add kind parameter to VaultIndex.search()**

In `knowledge/vault/vault_adapter.py`, modify the `search()` method signature and add filtering:

```python
def search(
    self,
    domain: str | None = None,
    tags: list[str] | None = None,
    query: str | None = None,
    kind: str | None = None,        # NEW
    max_results: int = 20,
) -> list[dict]:
```

After the query matching section, before sorting, add kind filter:

```python
# Filter by kind (if specified)
if kind:
    candidates = [f for f in candidates if f.get("kind") == kind]
```

**Step 3: Run test to verify pass**

Run: `python3 tests/test_fact_parser.py`
Expected: PASS

**Step 4: Commit**

```bash
cd ~/Documents/overcr
git add tests/test_fact_parser.py knowledge/vault/vault_adapter.py
git commit -m "feat: add kind filter to VaultIndex.search()"
```

---

### Task 3: Seed vault with rejected-fact and next-action facts

**Objective:** Add initial `kind:rejected` and `kind:next_action` facts to the vault based on known pain points from development history.

**Files:**
- Modify: `~/Documents/ObsidianVault/5-Research/overcr/index.md` — add rejected/next_action facts
- Modify: `~/Documents/ObsidianVault/1-Projects/cammander/index.md` — add next_action facts

**Step 1: Add rejected facts to OverCR index**

Append inside the existing `<!--- overcr:facts:begin -->` fence in `5-Research/overcr/index.md`:

```
- [overcr::memory::rejected] kind:rejected Vector DB embeddings for memory search — chosen CAG/filesystem-first from the start, no regrets
- [overcr::memory::rejected] kind:rejected In-memory cache for task state — filesystem-first invariants prohibit this by design
- [overcr::design::rejected] kind:rejected Autonomous outbound contact — OverCR is a substrate, not an agent; no autonomous side effects
- [overcr::design::rejected] kind:rejected Full in-memory state cache — every mutation hits disk immediately; no cache coherency questions
```

**Step 2: Add next_action facts to Cammander index**

Append inside the existing `<!--- overcr:facts:begin -->` fence in `1-Projects/cammander/index.md`:

```
- [cammander::next::priority] kind:next_action Implement v0.2 working memory plan — pure markdown fact fences, no DB
- [cammander::next::feature] kind:next_action PTY terminal persistence across browser sessions
```

**Step 3: Add next_action facts to OverCR index**

```
- [overcr::next::priority] kind:next_action Rebuild vault index and re-verify all 20+ notes parse correctly with the new kind field
```

**Step 4: Verify fences still parse cleanly**

```bash
cd ~/Documents/overcr
python3 -c "
from knowledge.vault.fact_parser import parse_file
rejected = [f for f in parse_file('/home/sc/Documents/ObsidianVault/5-Research/overcr/index.md') if f.get('kind') == 'rejected']
next_act = [f for f in parse_file('/home/sc/Documents/ObsidianVault/5-Research/overcr/index.md') if f.get('kind') == 'next_action']
print(f'OverCR: {len(rejected)} rejected, {len(next_act)} next_action facts')
camm = parse_file('/home/sc/Documents/ObsidianVault/1-Projects/cammander/index.md')
camm_next = [f for f in camm if f.get('kind') == 'next_action']
print(f'Cammander: {len(camm_next)} next_action facts')
print('All fences parse cleanly.')
"
```

Expected: Shows correct counts, no errors.

**Step 5: Commit**

```bash
cd ~/Documents/overcr
git add -A
git commit -m "docs: seed vault with rejected and next_action facts"
```

---

### Task 4: Inject rejected/next_action context during task creation

**Objective:** Extend `OverCRRuntime.create_task()` to search the vault for `kind=rejected` and `kind=next_action` facts in the task domain, and inject them as guidance context.

**Files:**
- Modify: `runtime/overcr_runtime.py` — extend context enrichment in `create_task()`

**Step 1: Write failing test**

Add to `tests/test_fact_parser.py` (or a new runtime test file):

Actually, this is best tested by running the existing runtime tests and adding a new test. Let me check the test structure first.

For now, we'll verify manually:

```python
# Test harness — verify vault guidance injection works
from runtime.overcr_runtime import OverCRRuntime
rt = OverCRRuntime(
    root="/home/sc/overcr-workspace",
    vault_path="/home/sc/Documents/ObsidianVault"
)
vault = rt.vault_index

# Check we can find rejected facts
rejected = vault.search(tags=["overcr"], kind="rejected")
print(f"Rejected facts found: {len(rejected)}")
for f in rejected:
    print(f"  - {f['claim'][:80]}")

next_actions = vault.search(tags=["cammander"], kind="next_action")
print(f"Next actions found: {len(next_actions)}")
```

**Step 2: Modify create_task() in overcr_runtime.py**

Find the vault enrichment section in `create_task()` (around line 128-144):

```python
# Enrich context with vault facts
enriched_context = dict(input_context)
vault = self.vault_index
if vault:
    facts = vault.search(
        domain=domain,
        tags=description.split(),
        query=instruction,
        max_results=15,
    )
    if facts:
        enriched_context["_vault_facts"] = facts
        enriched_context["_vault_note"] = (
            f"OverCR found {len(facts)} relevant vault facts "
            f"for domain '{domain}'. "
            f"Index includes {vault.stats()['notes_with_facts']} notes."
        )
```

Add after the existing vault enrichment:

```python
    # NEW: Inject guidance facts — rejected approaches and next actions
    rejected_approaches = vault.search(
        domain=domain,
        kind="rejected",
        max_results=10,
    )
    next_actions = vault.search(
        domain=domain,
        kind="next_action",
        max_results=5,
    )
    
    guidance_entries = []
    if rejected_approaches:
        enriched_context["_vault_rejected_approaches"] = rejected_approaches
        guidance_entries.append(
            f"Known approaches that did NOT work ({len(rejected_approaches)}): "
            + "; ".join(f['claim'][:100] for f in rejected_approaches)
        )
    if next_actions:
        enriched_context["_vault_next_actions"] = next_actions
        guidance_entries.append(
            f"Suggested next actions ({len(next_actions)}): "
            + "; ".join(f['claim'][:100] for f in next_actions)
        )
    
    if guidance_entries:
        enriched_context["_vault_guidance"] = "\n".join(guidance_entries)
```

**Step 3: Run full test suite to verify no regressions**

```bash
cd ~/Documents/overcr
python3 tests/run_all.py
```

Expected: All existing tests pass (28/28 or whatever the count is).

**Step 4: Manual integration check**

```bash
cd ~/Documents/overcr
python3 -c "
from runtime.overcr_runtime import OverCRRuntime
rt = OverCRRuntime(
    root='/home/sc/overcr-workspace',
    vault_path='/home/sc/Documents/ObsidianVault'
)
task = rt.create_task(
    domain='research',
    description='Test negative facts integration',
    instruction='Check if rejected approaches are injected into context',
    input_context={}
)
ctx = task['request_packet']['input_context']
print('vault_guidance:', ctx.get('_vault_guidance', 'MISSING')[:200])
print('rejected:', len(ctx.get('_vault_rejected_approaches', [])))
print('next_actions:', len(ctx.get('_vault_next_actions', [])))
if ctx.get('_vault_guidance'):
    print('[PASS] Guidance injected')
else:
    print('[INFO] No guidance — may need domain/tag match')
"
```

Expected: `_vault_guidance` present in context (or empty if no domain matches, which is fine — it's optional).

**Step 5: Commit**

```bash
cd ~/Documents/overcr
git add runtime/overcr_runtime.py
git commit -m "feat: inject rejected/next_action guidance facts into task context"
```

---

### Task 5: Update CHANGELOG and version

**Objective:** Document the changes for v2.11.1.

**Files:**
- Modify: `CHANGELOG.md`

**Step 1: Add v2.11.1 entry**

Insert after the `## [2.11.0]` section:

```markdown
## [2.11.1] — 2026-06-03

### Added

- **Negative facts (rejected approaches)** — bullet-format facts can now carry a `kind:rejected` prefix. These get injected into task context as `_vault_rejected_approaches`, telling agents what approaches are known to fail so they don't retry dead ends.
- **Next-action tracking** — bullet-format facts can carry a `kind:next_action` prefix. These get injected as `_vault_next_actions`, bridging the "what should I do next?" gap between sessions.
- `fact_parser.py`: optional `kind:` prefix in bullet format (e.g., `- [domain::key] kind:rejected This approach failed`). Backward compatible — existing facts without the prefix get `kind="n/a"`.
- `vault_adapter.py`: `VaultIndex.search()` accepts a `kind` parameter for filtering by fact kind.
- `overcr_runtime.py`: `create_task()` enriches context with `_vault_guidance`, `_vault_rejected_approaches`, and `_vault_next_actions` when vault facts of those kinds exist for the task domain.
- Vault seeds: 4 rejected facts in `5-Research/overcr/index.md`, 2 next-action facts in `1-Projects/cammander/index.md`.

### Changed

- `fact_parser.py`: bullet format now extracts `kind` from `kind:<value>` prefix in the claim text.
- `vault_adapter.py`: `VaultIndex.search()` signature extended with optional `kind` parameter.

### Testing

- `tests/test_fact_parser.py`: new test file covering kind prefix parsing, missing kind fallback, and kind-filtered search.
```

**Step 2: Verify changelog**

```bash
head -80 ~/Documents/overcr/CHANGELOG.md | grep "2.11.1"
```

Expected: 2.11.1 entry visible.

**Step 3: Commit**

```bash
cd ~/Documents/overcr
git add CHANGELOG.md
git commit -m "docs: add v2.11.1 changelog entry for negative facts + next-action tracking"
```

---

### Task 6: Run final integration verification

**Objective:** Confirm the full pipeline — fact parsing → vault indexing → runtime context enrichment — works end-to-end.

**Step 1: Rebuild vault index and verify**

```bash
cd ~/Documents/overcr
python3 -c "
from knowledge.vault import VaultIndex
idx = VaultIndex('/home/sc/Documents/ObsidianVault')
count = idx.rebuild()
stats = idx.stats()
print(f'Notes with facts: {stats[\"notes_with_facts\"]}')
print(f'Total facts: {stats[\"total_facts\"]}')

# Check kind distribution
kinds = {}
for note_path, note in idx._notes.items():
    for f in note['facts']:
        k = f.get('kind', 'n/a')
        kinds[k] = kinds.get(k, 0) + 1
print(f'Kind distribution: {kinds}')
"
```

Expected: Shows `rejected: 4`, `next_action: 3` (or however many were seeded), plus `n/a` for all existing bulk facts.

**Step 2: Run full test suite**

```bash
cd ~/Documents/overcr
python3 tests/run_all.py
```

Expected: ALL tests pass.

**Step 3: Final summary**

```bash
cd ~/Documents/overcr
echo "=== v2.11.1 Implementation Summary ==="
echo "Files modified:"
git diff --name-only HEAD~5
echo ""
echo "New files:"
git diff --diff-filter=A --name-only HEAD~5
echo ""
echo "Commits:"
git log --oneline HEAD~5..HEAD
```

---

## Acceptance Criteria

- [ ] `kind:rejected` and `kind:next_action` prefixes parse correctly from bullet-format facts
- [ ] Existing facts without kind prefix remain `kind="n/a"` (backward compatible)
- [ ] `VaultIndex.search(kind="rejected")` returns only rejected facts
- [ ] `OverCRRuntime.create_task()` injects `_vault_rejected_approaches` and `_vault_next_actions` into context
- [ ] Vault has at least 4 rejected and 3 next_action facts seeded
- [ ] All existing tests pass with no regressions
- [ ] CHANGELOG updated with v2.11.1 entry