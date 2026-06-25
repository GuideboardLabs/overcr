#!/usr/bin/env python3
"""Jac's OverCR integration bridge — callable from `execute_code` or terminal.

Usage:
  python3 overcr-bridge.py create <domain> <description> <instruction>
  python3 overcr-bridge.py advance <task_id> <state> [note]
  python3 overcr-bridge.py show <task_id>
  python3 overcr-bridge.py list [state_filter]
  python3 overcr-bridge.py audit <task_id>
  python3 overcr-bridge.py search [domain] [query] [--kind kind] [--max N]
  python3 overcr-bridge.py rebuild
  python3 overcr-bridge.py stats
  python3 overcr-bridge.py domains
  python3 overcr-bridge.py tags

Workspace: $HOME/overcr-workspace
OverCR root: $HOME/Documents/overcr
Vault:       $HOME/Documents/ObsidianVault
"""
import sys, json, argparse
from pathlib import Path

sys.path.insert(0, str(Path.home() / 'Documents' / 'overcr'))

from runtime.overcr_runtime import OverCRRuntime
from knowledge.vault.vault_adapter import VaultIndex

VAULT_ROOT = str(Path.home() / 'Documents' / 'ObsidianVault')
WORKSPACE = str(Path.home() / 'overcr-workspace')
OVERCR_ROOT = str(Path.home() / 'Documents' / 'overcr')


def cmd_create(rt, args):
    task = rt.create_task(
        domain=args[0],
        description=args[1],
        instruction=' '.join(args[2:]),
        input_context={},
    )
    print(json.dumps({'task_id': task['task_id'], 'state': task['state']}, indent=2))


def cmd_advance(rt, args):
    task_id, state = args[0], args[1]
    note = ' '.join(args[2:]) if len(args) > 2 else ''
    t = rt.task_store.advance_state(task_id, state, note)
    print(json.dumps({'task_id': t['task_id'], 'state': t['state']}, indent=2))


def cmd_show(rt, args):
    t = rt.task_store.load_task(args[0])
    print(json.dumps(t, indent=2, default=str))


def cmd_list(rt, args):
    tasks = rt.task_store.list_tasks()
    state_filter = args[0].lower() if args else None
    for t in tasks:
        if state_filter and t['state'].lower() != state_filter:
            continue
        print(f"{t['task_id']:12s} {t['state']:20s} {t['description'][:60]}")


def cmd_audit(rt, args):
    task_id = args[0] if args else None
    audit_path = Path(WORKSPACE) / 'runtime' / 'audit.jsonl'
    if not audit_path.exists():
        print("No audit log found.")
        return
    lines = audit_path.read_text().strip().split('\n')
    count = 0
    for line in reversed(lines):
        if not line.strip():
            continue
        e = json.loads(line)
        if task_id and 'task_id' in e and e['task_id'] != task_id:
            continue
        print(f"{e.get('timestamp','?'):26s} {e.get('entry_type','?'):20s} {str(e.get('payload',{}))[:80]}")
        count += 1
        if count >= 20:
            break


def cmd_search(_rt, args):
    idx = VaultIndex(VAULT_ROOT)
    domain = args.domain or None
    query = args.query or None
    kind = args.kind or None
    max_results = args.max or 20

    facts = idx.search(domain=domain, query=query, kind=kind, max_results=max_results)
    if not facts:
        print("No matching facts found.")
        return

    for i, f in enumerate(facts, 1):
        kind_str = f.get('kind', 'n/a')
        claim = f.get('claim', '')[:120]
        conf = f.get('confidence')
        conf_str = f' (conf: {conf})' if conf is not None else ''
        src = f.get('source', '')
        src_str = f' [{src}]' if src else ''
        print(f"  {i:3d}. [{kind_str}] {claim}{conf_str}{src_str}")

    if len(facts) >= max_results:
        print(f"\n  ... {len(facts)} total, showing {max_results}")


def cmd_rebuild(_rt, args):
    idx = VaultIndex(VAULT_ROOT)
    count = idx.rebuild()
    stats = idx.stats()
    print(f"Index rebuilt: {count} notes indexed")
    print(f"  Total facts: {stats.get('total_facts', 0)}")
    print(f"  Domains:     {stats.get('domains', 0)}")
    print(f"  Tags:        {stats.get('tags', 0)}")


def cmd_stats(_rt, args):
    idx = VaultIndex(VAULT_ROOT)
    if hasattr(idx, '_built') and not idx._built:
        idx.rebuild()
    stats = idx.stats()
    print(json.dumps(stats, indent=2, default=str))


def cmd_domains(_rt, args):
    idx = VaultIndex(VAULT_ROOT)
    if hasattr(idx, '_built') and not idx._built:
        idx.rebuild()
    domains = idx.list_domains()
    print(f"Domains ({len(domains)}):")
    for d in sorted(domains):
        print(f"  • {d}")


def cmd_tags(_rt, args):
    idx = VaultIndex(VAULT_ROOT)
    if hasattr(idx, '_built') and not idx._built:
        idx.rebuild()
    tags = idx.list_tags()
    print(f"Tags ({len(tags)}):")
    for t in sorted(tags)[:50]:
        print(f"  • {t}")
    if len(tags) > 50:
        print(f"  ... and {len(tags) - 50} more")


COMMANDS = {
    'create':  cmd_create,
    'advance': cmd_advance,
    'show':    cmd_show,
    'list':    cmd_list,
    'audit':   cmd_audit,
    'search':  cmd_search,
    'rebuild': cmd_rebuild,
    'stats':   cmd_stats,
    'domains': cmd_domains,
    'tags':    cmd_tags,
}


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == 'help' or cmd not in COMMANDS:
        print(__doc__)
        sys.exit(0)

    # For search, use argparse for named flags
    if cmd == 'search':
        parser = argparse.ArgumentParser(description='OverCR vault search')
        parser.add_argument('domain', nargs='?', default='')
        parser.add_argument('query', nargs='?', default='')
        parser.add_argument('--kind', default='')
        parser.add_argument('--max', type=int, default=20)
        # Strip command name from argv
        parsed = parser.parse_args(sys.argv[2:])
        cmd_search(None, parsed)
        return

    # Runtime commands
    rt = OverCRRuntime(WORKSPACE)

    if cmd in ('rebuild', 'stats', 'domains', 'tags'):
        # Doesn't need runtime, but pass it for consistency
        pass

    raw_args = sys.argv[2:]
    COMMANDS[cmd](rt, raw_args)


if __name__ == '__main__':
    main()