"""Recompute the tool-side decision of existing SensIntent / oracle / rule results from their stored schemas.

The LLM is not called: everything after parsing is deterministic, so a change to the optimiser or the
verifier can be applied to finished runs. Originals are kept as <file>.bak once.
Usage: python replan.py ../results/natural/sensintent_*.jsonl ../results/natural/oracle.jsonl ../results/natural/rule.jsonl
"""
import sys, json, glob, os, shutil
from agent import Verifier, plan_with_tools

HERE = os.path.dirname(os.path.abspath(__file__))
ver = Verifier(os.path.join(HERE, '..', 'data', 'gt_table.csv'))
intents = {r['id']: r for r in map(json.loads, open(os.path.join(HERE, '..', 'data', 'intents_natural.jsonl'), encoding='utf-8'))}
for f in [f for p in sys.argv[1:] for f in glob.glob(p)]:
    res = [json.loads(l) for l in open(f, encoding='utf-8') if l.strip()]
    changed = flipped = 0; out = []
    for r in res:
        if r.get('schema') and r.get('decision') in ('configure', 'infeasible'):
            new = plan_with_tools(r['schema'], intents[r['id']]['deploy'], ver)
            if new['decision'] != r['decision']: flipped += 1
            if new.get('cid') != r.get('cid'): changed += 1
            for k in ('cid', 'config', 'predicted', 'simulated', 'binding', 'relaxation', 'note'):
                r.pop(k, None)
                if k in new: r[k] = new[k]
            r['decision'] = new['decision']
        out.append(r)
    if not os.path.exists(f + '.bak'): shutil.copy(f, f + '.bak')
    with open(f, 'w', encoding='utf-8') as fh:
        for r in out: fh.write(json.dumps(r, default=str) + '\n')
    print(f'{os.path.basename(f)}: {len(res)} records, {changed} configurations changed, {flipped} decisions changed')
