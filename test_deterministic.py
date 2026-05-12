#!/usr/bin/env python3
import sys
sys.path.insert(0, '.')
from runtime.workflow_runner import WorkflowRunner
from runtime.workflow_graph import WorkflowGraph, WorkflowNode, WorkflowEdge
import importlib.util

spec = importlib.util.spec_from_file_location('validate_packet', 'tools/validate_packet.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

from pathlib import Path
runner = WorkflowRunner(root=str(Path(__file__).resolve().parent))

for sa, pt, ap in [
    ('knower', 'knower_claim_review', 'on_failure'),
    ('cryer', 'cryer_recon', 'never'),
    ('coder', 'coder_patch_plan', 'always'),
    ('pyper', 'pyper_execution_plan', 'always'),
    ('pyper', 'pyper_execution_receipt', 'always'),
    ('cryer', 'cryer_engagement_signal', 'never'),
]:
    node = WorkflowNode(node_id=f'test_{sa}', subagent=sa, packet_type=pt, approval_policy=ap)
    pkt = runner._deterministic_output(node, {})
    valid, errors, warnings = mod.validate_packet(pkt)
    status = f'valid={valid}'
    if not valid:
        status += f' errors={errors}'
    print(f'{sa}/{pt}: {status}')

print('ALL CHECKS DONE')