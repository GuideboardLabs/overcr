#!/usr/bin/env python3
"""Jac's OverCR integration bridge — callable from `execute_code` or terminal.

Usage:
  python3 overcr-bridge.py create <domain> <description> <instruction>
  python3 overcr-bridge.py advance <task_id> <state> [note]
  python3 overcr-bridge.py show <task_id>
  python3 overcr-bridge.py list
  python3 overcr-bridge.py audit <task_id>

Workspace: $HOME/overcr-workspace
OverCR root: $HOME/Documents/overcr
"""
import sys, json
sys.path.insert(0, '/home/sc/Documents/overcr')
from runtime.overcr_runtime import OverCRRuntime

def main():
    rt = OverCRRuntime('/home/sc/overcr-workspace')
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'help'

    if cmd == 'create':
        task = rt.task_store.create_task(
            assigned_subagent='jac',
            domain=sys.argv[2],
            description=sys.argv[3],
            instruction=' '.join(sys.argv[4:]) if len(sys.argv) > 4 else '',
            input_context={}
        )
        rt.task_store.advance_state(task['task_id'], 'assigned', 'Jac assigned')
        rt.task_store.advance_state(task['task_id'], 'in_progress', 'Active')
        final = rt.task_store.load_task(task['task_id'])
        print(json.dumps({'task_id': final['task_id'], 'state': final['state']}))

    elif cmd == 'advance':
        t = rt.task_store.advance_state(sys.argv[2], sys.argv[3], ' '.join(sys.argv[4:]) if len(sys.argv) > 4 else '')
        print(json.dumps({'task_id': t['task_id'], 'state': t['state']}))

    elif cmd == 'show':
        t = rt.task_store.load_task(sys.argv[2])
        print(json.dumps(t, indent=2, default=str))

    elif cmd == 'list':
        for t in rt.task_store.list_tasks():
            print(f"{t['task_id']:12s} {t['state']:20s} {t['description'][:60]}")

    elif cmd == 'audit':
        from pathlib import Path
        audit_path = Path('/home/sc/overcr-workspace') / 'runtime' / 'audit.jsonl'
        if audit_path.exists():
            for line in audit_path.read_text().strip().split('\n')[-20:]:
                e = json.loads(line)
                print(f"{e.get('timestamp','?'):26s} {e.get('entry_type','?'):20s} {str(e.get('payload',{}))[:80]}")

if __name__ == '__main__':
    main()