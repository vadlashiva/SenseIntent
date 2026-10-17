"""Closed-form energy/lifetime/latency model, configuration grid and optimiser for SensIntent.

Mirrors Eqs. (2)-(9) of the paper. Constants come from gt_table.py so that the closed form
and the simulator use identical parameters.
"""
import math
import config as g

GRID = list(g.grid())                      # cid = index in this list (same order as gt_table.csv)
OPTIONS = dict(p=[0.05, 0.1, 0.2], Tr=[30, 60, 300, 900, 3600], F=[1, 5, 10, 30],
               B=[1, 5, 10, 30], Tci=[0.125, 0.25, 0.5, 1.0, 2.0], a=[0, 1])
DEFAULT = dict(p=0.1, Tr=60, F=10, B=1, Tci=0.5, e='leach', a=0)


def ebar(c, dep):
    """Expected energy per node per round (J, simulator battery scale)."""
    q = dict(g.DEPLOY[dep]); N, M, H, L = q['N'], q['M'], g.H, g.L
    p, F, B, Tr, Tci = c['p'], c['F'], c['B'], c['Tr'], c['Tci']
    k = max(p * N, 1); dch2 = M ** 2 / (2 * math.pi * k); dbs2 = M ** 2 / 6
    est = g.EST + g.P_TX * Tci / 2; p0 = g.P_SL + g.T_L / Tci * g.P_RX
    cb = B > 1; nm = math.ceil(F / B) if cb else F; bm = nm * H + F * L
    em = p0 * Tr + nm * est + bm * (g.EELEC + g.EFS * dch2)
    nc = 1 if cb else F; bc = (H + F * L) if cb else F * (H + L)
    ec = p0 * Tr + (1 / p - 1) * bm * g.EELEC + (1 / p) * F * L * g.EDA + nc * est + bc * (g.EELEC + g.EFS * dbs2)
    return (1 - p) * em + p * ec


def predict(c, dep):
    """Closed-form lifetime (days, real battery), worst-case latency (s) and sampling period (s)."""
    life = min(g.E0_SIM / ebar(c, dep) * c['Tr'] * g.SCALE / 86400.0, g.CAP_DAYS)
    return dict(lifetime_days=float(life), latency_max_s=(1 + c['a']) * c['Tr'] + 2 * c['Tci'],
                sampling_s=c['Tr'] / c['F'])


def snap(c):
    """Map any proposed configuration to the nearest grid configuration; return (cid, config)."""
    c = dict(DEFAULT, **{k: v for k, v in c.items() if v is not None})
    for k, opts in OPTIONS.items():
        try:
            v = float(c[k])
        except (TypeError, ValueError):
            v = DEFAULT[k]
        c[k] = min(opts, key=lambda o: abs(math.log(max(o, 1e-3)) - math.log(max(v, 1e-3))) if k not in ('a',) else abs(o - v))
    c['a'] = int(c['a']); c['e'] = 'leach'
    if c['B'] > c['F'] and c['B'] != 5:            # grid keeps only B<=F (plus B=5)
        c['B'] = 5 if c['F'] < 5 else max(b for b in OPTIONS['B'] if b <= c['F'])
    if c['B'] == 1:
        c['a'] = 0
    for i, x in enumerate(GRID):
        if all(x[k] == c[k] for k in ('p', 'Tr', 'F', 'B', 'Tci', 'a')):
            return i, x
    raise ValueError(f'config not in grid: {c}')


def violations(pred, s, margin=0.0):
    """List of (constraint, required, predicted) that the prediction violates."""
    v = []
    if s.get('lifetime_days') is not None and pred['lifetime_days'] < s['lifetime_days'] * (1 + margin):
        v.append(('lifetime_days', s['lifetime_days'], round(pred['lifetime_days'], 1)))
    if s.get('latency_max_s') is not None and pred['latency_max_s'] > s['latency_max_s']:
        v.append(('latency_max_s', s['latency_max_s'], pred['latency_max_s']))
    if s.get('sampling_max_s') is not None and pred['sampling_s'] > s['sampling_max_s']:
        v.append(('sampling_max_s', s['sampling_max_s'], pred['sampling_s']))
    return v


def relaxation(pred, s):
    """Relative relaxation each stated constraint needs, Eq. (relax); returns (rho, binding, parts)."""
    rel = {}
    if s.get('lifetime_days') is not None: rel['lifetime'] = max(s['lifetime_days'] / max(pred['lifetime_days'], 1e-9) - 1, 0)
    if s.get('latency_max_s') is not None: rel['latency'] = max(pred['latency_max_s'] / s['latency_max_s'] - 1, 0)
    if s.get('sampling_max_s') is not None: rel['sampling'] = max(pred['sampling_s'] / s['sampling_max_s'] - 1, 0)
    if not rel:
        return 0.0, None, rel
    return max(rel.values()), max(rel, key=rel.get), rel


def closest_ranked(s, dep, k=5):
    """The k grid configurations with the smallest closed-form worst-case relaxation, best first."""
    rows = []
    for i, c in enumerate(GRID):
        pr = predict(c, dep); rho, bind, _ = relaxation(pr, s)
        rows.append((rho, i, c, pr, bind))
    rows.sort(key=lambda r: r[0])
    return rows[:k]


def optimise(s, dep, margin=0.06, k=5):
    """Rank grid configurations that satisfy the schema by predicted lifetime (closed form).

    Returns (candidates, closest): candidates is a list of (cid, config, pred) that satisfy all
    constraints with the safety margin; if empty, closest is the configuration needing the
    smallest worst-case relative relaxation, with the binding constraint.
    """
    rows = []
    for i, c in enumerate(GRID):
        pr = predict(c, dep); rows.append((i, c, pr))
    ok = [r for r in rows if not violations(r[2], s, margin)]
    ok.sort(key=lambda r: -r[2]['lifetime_days'])
    if ok:
        return ok[:k], None
    best = None
    for i, c, pr in rows:
        rel = {}
        if s.get('lifetime_days') is not None: rel['lifetime'] = max(s['lifetime_days'] / max(pr['lifetime_days'], 1e-9) - 1, 0)
        if s.get('latency_max_s') is not None: rel['latency'] = max(pr['latency_max_s'] / s['latency_max_s'] - 1, 0)
        if s.get('sampling_max_s') is not None: rel['sampling'] = max(pr['sampling_s'] / s['sampling_max_s'] - 1, 0)
        w = max(rel.values()) if rel else 0
        if best is None or w < best[0]:
            best = (w, i, c, pr, max(rel, key=rel.get) if rel else None)
    return [], dict(cid=best[1], config=best[2], pred=best[3], binding=best[4], relaxation=round(best[0], 3))
