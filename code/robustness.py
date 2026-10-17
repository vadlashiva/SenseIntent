"""Battery-capacity robustness and bootstrap confidence intervals for the main results.

Usage: python robustness.py   (reads data/ and results/natural*, prints tables)
Robustness: real lifetime = f x simulated lifetime (lifetime is linear in battery energy, Eq. 5);
a returned configuration counts as satisfying only if it still meets every constraint.
"""
import json, os, random
from agent import Verifier
H = os.path.dirname(os.path.abspath(__file__))
I = {r['id']: r for r in map(json.loads, open(os.path.join(H, '..', 'data', 'intents_natural.jsonl'), encoding='utf-8'))}
ver = Verifier(os.path.join(H, '..', 'data', 'gt_table.csv'))
R = os.path.join(H, '..', 'results')
FILES = {'Default': 'natural/default.jsonl', 'Oracle': 'natural/oracle.jsonl'}
for m, tag in (('Zero-shot', 'zeroshot'), ('LLM+repair', 'repair'), ('SensIntent', 'sensintent')):
    for s in ('120b', '20b'):
        FILES[f'{m} {s}'] = f'natural_v3/{tag}_openai_gpt-oss-{s}.jsonl'

def meets(g, cid, f):
    gs = g['schema']; row = ver.row(g['deploy'], cid)
    if gs['lifetime_days'] is not None:
        cov = min([1.0, 0.9, 0.75, 0.5], key=lambda c: abs(c - (gs['coverage'] or 1.0)))
        if f * row[f'life_c{int(cov*100)}_days'] < gs['lifetime_days']: return False
    if gs['latency_max_s'] is not None and row['latency_max_s'] > gs['latency_max_s']: return False
    if gs['sampling_max_s'] is not None and row['sampling_s'] > gs['sampling_max_s']: return False
    return True

def outcome(r, f=1.0):
    """per-request record: correct?, feasible?, satisfied?, silent?, pred_inf, true_inf"""
    g = I[r['id']]; d = r['decision']; amb = g['difficulty'] == 'ambiguous'
    feas = (not amb) and g['feasible']; inf = (not amb) and not g['feasible']
    sat = feas and d == 'configure' and meets(g, r['cid'], f)
    silent = (not amb) and d == 'configure' and not (g['feasible'] and meets(g, r['cid'], f))
    correct = (d == 'clarify') if amb else (sat if feas else d == 'infeasible')
    return dict(correct=correct, feas=feas, sat=sat, silent=silent, pinf=d == 'infeasible', tinf=inf)

def metrics(os_):
    n = len(os_); feas = sum(o['feas'] for o in os_)
    tp = sum(o['pinf'] and o['tinf'] for o in os_); p = sum(o['pinf'] for o in os_); t = sum(o['tinf'] for o in os_)
    pr = tp / p if p else 0; rc = tp / t if t else 0
    return dict(acc=100 * sum(o['correct'] for o in os_) / n, sat=100 * sum(o['sat'] for o in os_) / max(feas, 1),
                silent=sum(o['silent'] for o in os_), f1=100 * (2 * pr * rc / (pr + rc) if pr + rc else 0))

data = {k: [json.loads(l) for l in open(os.path.join(R, v), encoding='utf-8') if l.strip()] for k, v in FILES.items()}
print('ROBUSTNESS (satisfaction % / silent failures) when real batteries hold a fraction f of the modelled energy')
print(f"{'method':18s}" + ''.join(f'  f={f:<4} ' for f in (1.0, 0.95, 0.9, 0.8)))
for k, rs in data.items():
    cells = []
    for f in (1.0, 0.95, 0.9, 0.8):
        m = metrics([outcome(r, f) for r in rs]); cells.append(f"{m['sat']:5.1f}/{m['silent']:<3d}")
    print(f'{k:18s}' + '  '.join(cells))

print('\nBOOTSTRAP 95% CI (2000 resamples of the 300 requests)')
random.seed(1); B = 2000
base = {k: [outcome(r) for r in rs] for k, rs in data.items()}
ids = [r['id'] for r in data['SensIntent 120b']]
idx = {k: {r['id']: i for i, r in enumerate(rs)} for k, rs in data.items()}
samples = [[random.choice(ids) for _ in ids] for _ in range(B)]
def ci(vals):
    vals = sorted(vals); return vals[int(0.025 * B)], vals[int(0.975 * B) - 1]
for k in data:
    if len(data[k]) != 300: continue
    accs, sats, f1s = [], [], []
    for smp in samples:
        o = [base[k][idx[k][i]] for i in smp]; m = metrics(o)
        accs.append(m['acc']); sats.append(m['sat']); f1s.append(m['f1'])
    m = metrics(base[k])
    print(f"{k:18s} acc {m['acc']:5.1f} [{ci(accs)[0]:.1f}, {ci(accs)[1]:.1f}]  sat {m['sat']:5.1f} [{ci(sats)[0]:.1f}, {ci(sats)[1]:.1f}]  F1 {m['f1']:5.1f} [{ci(f1s)[0]:.1f}, {ci(f1s)[1]:.1f}]")
for a, b in (('SensIntent 120b', 'LLM+repair 120b'), ('SensIntent 120b', 'Zero-shot 120b'), ('SensIntent 20b', 'LLM+repair 20b')):
    d = []
    for smp in samples:
        d.append(metrics([base[a][idx[a][i]] for i in smp])['acc'] - metrics([base[b][idx[b][i]] for i in smp])['acc'])
    lo, hi = ci(d); print(f'paired accuracy difference {a} - {b}: {sum(d)/B:.1f} [{lo:.1f}, {hi:.1f}]')
