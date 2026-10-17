"""Generate WSN-IntentBench: natural-language operator intents with ground-truth labels.

Each intent is drawn as a typed record (lifetime L*, coverage c, latency D*, sampling S*),
rendered into English from varied templates, and labelled against the simulated table:
  feasible / infeasible, the set of satisfying configurations, the best one, and, for
  infeasible intents, the closest feasible configuration and the binding constraint.
Ambiguous intents (missing a number) are labelled with the field the agent must ask about.

Usage: python gen_intents.py gt_table.csv intents.jsonl [n_per_deploy] [seed]
"""
import sys, json, random
import pandas as pd, numpy as np

table, outp = sys.argv[1], sys.argv[2]
NPER = int(sys.argv[3]) if len(sys.argv) > 3 else 100
rng = random.Random(int(sys.argv[4]) if len(sys.argv) > 4 else 7)

df = pd.read_csv(table)
keys = ['deploy', 'cid', 'p', 'Tr', 'F', 'B', 'Tci', 'e', 'a', 'latency_max_s', 'sampling_s']
life_cols = [c for c in df.columns if c.startswith('life_c')]
T = df.groupby(keys, as_index=False)[life_cols].min()      # worst seed: a label must hold for every seed

DEPLOY_TXT = {
    'farm': ['our farm network of 100 soil-moisture sensors on a 1-hectare plot',
             'the 100-node crop-monitoring network in the 100 m x 100 m field'],
    'orchard': ['the orchard deployment, 100 sensors spread over 150 m x 150 m',
                'our 100-node orchard network covering a 150 m square'],
    'building': ['the 50 environmental sensors on this 50 m x 50 m factory floor',
                 'our building network of 50 temperature and humidity nodes'],
}
COVER_TXT = {1.0: ['every sensor', 'all nodes', 'no sensor at all'],
             0.9: ['at least 90% of the sensors', 'nine out of ten nodes'],
             0.75: ['three quarters of the nodes', 'at least 75% of the sensors'],
             0.5: ['at least half of the network', 'half the nodes or more']}
LIFE_DAYS = [90, 180, 365, 540, 730, 1095, 1825]
LAT_S = [60, 120, 300, 600, 900, 1800, 3600, 7200]
SAMP_S = [10, 30, 60, 300, 600, 900, 1800]

def months(d):
    m = round(d / 30.4)
    if m % 12 == 0: return f"{m//12} year" + ("s" if m//12 > 1 else "")
    return f"{m} months"

def mins(s):
    if s < 60: return f"{int(s)} seconds"
    m = int(s // 60)
    if m >= 60 and m % 60 == 0: return f"{m//60} hour" + ("s" if m//60 > 1 else "")
    return f"{m} minute" + ("s" if m > 1 else "")

def life_phrase(L, c):
    cov = rng.choice(COVER_TXT[c])
    if c == 1.0 and cov == 'no sensor at all':
        return rng.choice([f"no sensor should die for {months(L)}", f"no sensor at all may run flat within {months(L)}"])
    return rng.choice([f"keep {cov} running for {months(L)}", f"{cov} must stay alive for {months(L)}",
                       f"the batteries should last {months(L)} for {cov}"])

def lat_phrase(D):
    return rng.choice([f"readings must reach the gateway within {mins(D)}", f"report any change within {mins(D)}",
                       f"alerts must arrive in under {mins(D)}"])

def samp_phrase(S):
    return rng.choice([f"take a reading at least every {mins(S)}", f"sample every {mins(S)} or faster",
                       f"we need one measurement per {mins(S)}"])

def render(dep, rec):
    parts = []
    if rec['L'] is not None: parts.append(life_phrase(rec['L'], rec['c']))
    if rec['D'] is not None: parts.append(lat_phrase(rec['D']))
    if rec['S'] is not None: parts.append(samp_phrase(rec['S']))
    rng.shuffle(parts)
    body = parts[0] if len(parts) == 1 else ', '.join(parts[:-1]) + ' and ' + parts[-1]
    lead = rng.choice(['For {d}, {b}.', 'Configure {d} so that {b}.', '{B} -- this is for {d}.'])
    return lead.format(d=rng.choice(DEPLOY_TXT[dep]), b=body, B=body[0].upper() + body[1:])

def satisfy(sub, rec):
    m = np.ones(len(sub), bool)
    if rec['L'] is not None: m &= sub[f"life_c{int(rec['c']*100)}_days"].values >= rec['L']
    if rec['D'] is not None: m &= sub['latency_max_s'].values <= rec['D']
    if rec['S'] is not None: m &= sub['sampling_s'].values <= rec['S']
    return m

def relax(sub, rec):
    """Smallest relative relaxation needed per config, and which constraint binds."""
    parts = {}
    if rec['L'] is not None: parts['lifetime'] = np.maximum(rec['L'] / sub[f"life_c{int(rec['c']*100)}_days"].values - 1, 0)
    if rec['D'] is not None: parts['latency'] = np.maximum(sub['latency_max_s'].values / rec['D'] - 1, 0)
    if rec['S'] is not None: parts['sampling'] = np.maximum(sub['sampling_s'].values / rec['S'] - 1, 0)
    R = np.vstack(list(parts.values())); worst = R.max(0); k = int(worst.argmin())
    return k, list(parts)[int(R[:, k].argmax())], float(worst[k])

def draw(level):
    c = rng.choice([1.0, 0.9, 0.75, 0.5])
    L, D, S = rng.choice(LIFE_DAYS), rng.choice(LAT_S), rng.choice(SAMP_S)
    if level == 'easy':
        keep = rng.choice(['L', 'D', 'S'])
        return dict(L=L if keep == 'L' else None, c=c, D=D if keep == 'D' else None, S=S if keep == 'S' else None)
    if level == 'medium':
        drop = rng.choice(['L', 'D', 'S'])
        return dict(L=None if drop == 'L' else L, c=c, D=None if drop == 'D' else D, S=None if drop == 'S' else S)
    return dict(L=L, c=c, D=D, S=S)

AMBIG = [  # text, field the agent must ask about
    ("keep {d} running as long as possible and report quickly", 'latency'),
    ("make the batteries in {d} last a long time", 'lifetime'),
    ("{d} needs near real-time data but should not die soon", 'lifetime'),
    ("sample {d} often enough and keep it alive for the season", 'sampling'),
]

def row(i, dep, level, rec, text, sub):
    m = satisfy(sub, rec); out = dict(id=f"WIB-{i:04d}", deploy=dep, difficulty=level, text=text,
        schema=dict(lifetime_days=rec['L'], coverage=rec['c'] if rec['L'] is not None else None,
                    latency_max_s=rec['D'], sampling_max_s=rec['S']),
        feasible=bool(m.any()), n_feasible=int(m.sum()))
    if m.any():
        s = sub[m]
        best = s.iloc[int(np.argmax(s[f"life_c{int(rec['c']*100)}_days"].values))] if rec['L'] is not None else s.iloc[0]
        out['best_cid'] = int(best['cid']); out['feasible_cids'] = [int(x) for x in s['cid']]
    else:
        k, bind, r = relax(sub, rec)
        out['closest_cid'] = int(sub.iloc[k]['cid']); out['binding_constraint'] = bind; out['relaxation_needed'] = round(r, 3)
    return out

def main():
    rows = []; i = 0
    mix = ['easy'] * 20 + ['medium'] * 30 + ['hard'] * 30 + ['infeasible'] * 12 + ['ambiguous'] * 8
    for dep in DEPLOY_TXT:
        sub = T[T.deploy == dep].reset_index(drop=True)
        for _ in range(NPER):
            level = rng.choice(mix)
            if level == 'ambiguous':
                t, field = rng.choice(AMBIG); text = t.format(d=rng.choice(DEPLOY_TXT[dep]))
                rows.append(dict(id=f"WIB-{i:04d}", deploy=dep, difficulty='ambiguous', text=text[0].upper() + text[1:],
                                 schema=None, feasible=None, must_ask=field)); i += 1; continue
            for _try in range(500):
                rec = draw('hard' if level == 'infeasible' else level)
                f = satisfy(sub, rec).any()
                if (level == 'infeasible') != f: break
            rows.append(row(i, dep, level, rec, render(dep, rec), sub)); i += 1
    with open(outp, 'w') as fh:
        for r in rows: fh.write(json.dumps(r) + '\n')
    lv = pd.Series([r['difficulty'] for r in rows]).value_counts().to_dict()
    print('wrote', len(rows), 'intents', lv, 'feasible:', sum(1 for r in rows if r.get('feasible')))

if __name__ == '__main__':
    main()
