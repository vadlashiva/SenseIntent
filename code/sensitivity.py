"""Sensitivity of SensIntent to errors in the energy-model parameters (standard library only).

SensIntent plans with the nominal parameters. The 'true' network differs: one parameter (or a
worst-case combination) is off by +/-20%. The true lifetime of a configuration is its simulated
lifetime (gt_table.csv) scaled by the ratio of closed-form lifetimes under true vs nominal
parameters. Gold intent records are used, so only model error is measured, not parsing error.

For every feasible intent with a lifetime target we report how often the configuration chosen
with safety margin eps still meets every constraint in the perturbed network.

Usage: python sensitivity.py ../data/intents_natural.jsonl
Writes ../results/sensitivity.csv
"""
import sys, os, json, csv
import config as g
import model as M
from agent import Verifier

HERE = os.path.dirname(os.path.abspath(__file__))
ver = Verifier(os.path.join(HERE, '..', 'data', 'gt_table.csv'))
intents = [json.loads(l) for l in open(sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, '..', 'data', 'intents_natural.jsonl'), encoding='utf-8')]
NOM = {k: getattr(g, k) for k in ('E0_REAL', 'P_RX', 'P_TX', 'P_SL', 'T_L', 'EELEC')}


def set_params(over):
    for k, v in NOM.items():
        setattr(g, k, over.get(k, v))
    g.SCALE = g.E0_REAL / g.E0_SIM


SCEN = [('nominal', {})]
for k, name in (('E0_REAL', 'battery energy'), ('P_RX', 'receive power'), ('P_TX', 'transmit power'),
                ('P_SL', 'sleep power'), ('T_L', 'channel-check time'), ('EELEC', 'electronics energy')):
    for f in (0.8, 1.2):
        SCEN.append((f'{name} {"-" if f < 1 else "+"}20%', {k: NOM[k] * f}))
SCEN.append(('worst case: battery -20%, radio +20%', dict(E0_REAL=NOM['E0_REAL'] * 0.8, P_RX=NOM['P_RX'] * 1.2,
                                                         P_TX=NOM['P_TX'] * 1.2, T_L=NOM['T_L'] * 1.2)))

# plans with nominal parameters, for each margin
cases = [i for i in intents if i['feasible'] and i['difficulty'] != 'ambiguous' and i['schema']['lifetime_days'] is not None]
MARGINS = (0.06, 0.15, 0.25)
set_params({})
nominal_life = {}
plans = {}
for eps in MARGINS:
    for it in cases:
        s = dict(it['schema'], missing=[])
        cands, _ = M.optimise(s, it['deploy'], margin=eps, k=5)
        chosen = None
        for cid, c, pr in cands:
            sim, viol = ver.check(it['deploy'], cid, s)
            if not viol:
                chosen = cid; break
        plans[(eps, it['id'])] = chosen
        if chosen is not None:
            nominal_life[(it['deploy'], chosen)] = M.predict(M.GRID[chosen], it['deploy'])['lifetime_days']


def cov_col(cov):
    cov = min(g.COVER, key=lambda c: abs(c - (cov or 1.0)))
    return f'life_c{int(cov * 100)}_days'


def NOMLIFE(dep, cid, _c={}):
    if (dep, cid) not in _c:
        cur = {k: getattr(g, k) for k in NOM}; set_params({}); _c[(dep, cid)] = M.predict(M.GRID[cid], dep)['lifetime_days']; set_params(cur)
    return _c[(dep, cid)]


rows = []
for name, over in SCEN:
    set_params(over)
    out = dict(scenario=name)
    for eps in MARGINS:
        ok = n = 0
        for it in cases:
            cid = plans[(eps, it['id'])]
            n += 1
            if cid is None:
                continue
            dep = it['deploy']; s = it['schema']
            ratio = M.predict(M.GRID[cid], dep)['lifetime_days'] / nominal_life[(dep, cid)]
            true_life = ver.row(dep, cid)[cov_col(s['coverage'])] * ratio
            ok += true_life >= s['lifetime_days']
        out[f'met_eps{int(eps * 100):02d}'] = round(100 * ok / n, 1)
    # recalibrated gateway: plans with the true parameters and verifies in the true network.
    # unsafe = configured but violates a constraint; refused = declared infeasible although a configuration meets it
    unsafe = refused = 0
    for it in cases:
        dep = it['deploy']; s = dict(it['schema'], missing=[])
        cands, _ = M.optimise(s, dep, margin=0.06, k=5)
        tl = lambda cid: ver.row(dep, cid)[cov_col(s['coverage'])] * M.predict(M.GRID[cid], dep)['lifetime_days'] / NOMLIFE(dep, cid)
        meets = lambda cid: tl(cid) >= s['lifetime_days'] and not M.violations(dict(ver.row(dep, cid), lifetime_days=1e9), s)
        if cands and any(meets(cid) for cid, _, _ in cands):
            continue
        if cands:
            unsafe += 1          # Algorithm 1 would deploy the best candidate flagged unverified
        elif any(meets(i) for i in range(len(M.GRID))):
            refused += 1
    out['recal_unsafe'] = round(100 * unsafe / len(cases), 1)
    out['recal_refused'] = round(100 * refused / len(cases), 1)
    rows.append(out)
set_params({})

# planned (not perturbed) cost of a larger margin: lifetime given up versus eps=0.06 and requests lost
for eps in MARGINS:
    lost = sum(plans[(eps, it['id'])] is None for it in cases)
    print(f'eps={eps}: {lost} of {len(cases)} feasible requests become unservable at this margin')

cols = list(rows[0].keys()); w = {c: max(len(c), *(len(str(r[c])) for r in rows)) for c in cols}
print('  '.join(c.ljust(w[c]) for c in cols))
for r in rows:
    print('  '.join(str(r[c]).ljust(w[c]) for c in cols))
dst = os.path.join(HERE, '..', 'results', 'sensitivity.csv')
with open(dst, 'w', newline='', encoding='utf-8') as f:
    wr = csv.DictWriter(f, fieldnames=cols); wr.writeheader(); wr.writerows(rows)
print('saved', dst, '| requests with a lifetime target:', len(cases))
