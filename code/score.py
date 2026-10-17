"""Score result files against WSN-IntentBench labels and print a table (also saved as CSV).

Usage: python score.py ../data/intents.jsonl ../results/*.jsonl
"""
import sys, json, glob, os, csv
from agent import Verifier
import model as M

intents = {r['id']: r for r in map(json.loads, open(sys.argv[1], encoding='utf-8'))}
files = [f for p in sys.argv[2:] for f in glob.glob(p)]
ver = Verifier(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'gt_table.csv'))


def life(dep, cid, cov):
    cov = min([1.0, 0.9, 0.75, 0.5], key=lambda c: abs(c - (cov or 1.0)))
    return ver.row(dep, cid)[f'life_c{int(cov*100)}_days']


rows = []
for f in files:
    res = [json.loads(l) for l in open(f, encoding='utf-8') if l.strip()]
    n = dict(feas=0, feas_ok=0, inf=0, inf_tp=0, pred_inf=0, amb=0, amb_ok=0, wrong_clarify=0, err=0, total=0, correct=0)
    ratios = []; calls = 0; bind_ok = []; gaps = []
    for r in res:
        g = intents[r['id']]; d = r['decision']; n['total'] += 1; calls += r.get('llm_calls', 0)
        if d in ('error', 'parse_fail'): n['err'] += 1
        if d == 'infeasible': n['pred_inf'] += 1
        if g['difficulty'] == 'ambiguous':
            n['amb'] += 1; ok = d == 'clarify'; n['amb_ok'] += ok; n['correct'] += ok; continue
        if d == 'clarify': n['wrong_clarify'] += 1
        if g['feasible']:
            n['feas'] += 1
            ok = d == 'configure' and r.get('cid') in set(g['feasible_cids'])
            n['feas_ok'] += ok; n['correct'] += ok
            if ok and g['schema']['lifetime_days'] is not None:
                ratios.append(life(g['deploy'], r['cid'], g['schema']['coverage']) / life(g['deploy'], g['best_cid'], g['schema']['coverage']))
        else:
            n['inf'] += 1; ok = d == 'infeasible'; n['inf_tp'] += ok; n['correct'] += ok
            if ok and r.get('cid') is not None:   # quality of the closest alternative, judged in simulation
                gs = g['schema']; cov = min([1.0, 0.9, 0.75, 0.5], key=lambda c: abs(c - (gs['coverage'] or 1.0)))
                row = ver.row(g['deploy'], r['cid'])
                sim = dict(lifetime_days=row[f'life_c{int(cov*100)}_days'], latency_max_s=row['latency_max_s'], sampling_s=row['sampling_s'])
                rho, bind, _ = M.relaxation(sim, gs)
                bind_ok.append(bind == g['binding_constraint']); gaps.append(rho - g['relaxation_needed'])
    prec = n['inf_tp'] / n['pred_inf'] if n['pred_inf'] else 0.0
    rec = n['inf_tp'] / n['inf'] if n['inf'] else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    rows.append(dict(file=os.path.basename(f), n=n['total'],
                     overall_acc=round(100 * n['correct'] / max(n['total'], 1), 1),
                     satisfied_pct=round(100 * n['feas_ok'] / max(n['feas'], 1), 1),
                     infeasible_P=round(100 * prec, 1), infeasible_R=round(100 * rec, 1), infeasible_F1=round(100 * f1, 1),
                     clarify_pct=round(100 * n['amb_ok'] / max(n['amb'], 1), 1), wrong_clarify=n['wrong_clarify'],
                     lifetime_vs_best=round(sum(ratios) / len(ratios), 3) if ratios else None,
                     binding_acc=round(100 * sum(bind_ok) / len(bind_ok), 1) if bind_ok else None,
                     relax_gap=round(sum(gaps) / len(gaps), 3) if gaps else None,
                     llm_calls_per_intent=round(calls / max(n['total'], 1), 2), errors=n['err']))
if rows:
    cols = list(rows[0].keys()); w = {c: max(len(c), *(len(str(r[c])) for r in rows)) for c in cols}
    print('  '.join(c.rjust(w[c]) for c in cols))
    for r in rows: print('  '.join(str(r[c]).rjust(w[c]) for c in cols))
    out = os.path.join(os.path.dirname(os.path.abspath(files[0])), 'scores.csv')
    with open(out, 'w', newline='', encoding='utf-8') as f:
        wr = csv.DictWriter(f, fieldnames=cols); wr.writeheader(); wr.writerows(rows)
    print('saved', out)
