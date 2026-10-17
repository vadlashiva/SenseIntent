"""Build the ground-truth table for WSN-IntentBench.

Every configuration theta = (p, Tr, F, B, e, a) is simulated once per deployment and seed
with the HCB-XL simulator (battery-only). Lifetime is computed at several coverage levels c
(time until the alive fraction first drops below c) and scaled from the simulated battery
E0_SIM to a real battery E0_REAL. The scaling is exact for battery-only LEACH/DEEC because
per-round consumption does not depend on residual energy and election weights use E/E0.

Usage: python gt_table.py [seeds] [out.csv]
"""
import sys, csv, itertools, re
import numpy as np
from multiprocessing import Pool

import os
# Path to the published HCB-XL simulator; it is only read, never modified.
HCB = os.environ.get('HCBXL_PATH', os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'HCB-XL', 'hcbxl.py'))
src = open(HCB, encoding='utf-8').read()
src = src.replace("alive=h[::60].tolist()", "alive=h.tolist()")   # keep the full alive curve
src = src.split('if __name__=="__main__":')[0]
ns = {}
exec(compile(src, 'hcbxl_patched', 'exec'), ns)
run, P, CFG = ns['run'], ns['P'], ns['CFG']

from config import (E0_REAL, P_SL, CAP_DAYS, COVER, P_RX, P_TX, T_L, DEPLOY, grid)
E0_SIM = P['E0']          # 5 J in the simulator
SCALE = E0_REAL / E0_SIM

def cfg_name(c):
    name = f"{c['e']}-cb{int(c['B'] > 1)}-a{c['a']}"
    CFG[name] = (0, 0, int(c['B'] > 1), c['e'], c['a'])
    return name

def job(args):
    dep, cid, c, seed = args
    name = cfg_name(c)
    over = dict(DEPLOY[dep]); over.update(p=c['p'], Tr=float(c['Tr']), F=c['F'], B=max(c['B'], 1),
                                       Eidle=(P_SL + T_L / c['Tci'] * P_RX) * c['Tr'],
                                       Est=P['Est'] + P_TX * c['Tci'] / 2, Rmax=10**7)
    r = run((name, seed, over))
    h = np.array(r['alive']); N = over['N']
    out = dict(deploy=dep, cid=cid, seed=seed, **c)
    for cv in COVER:
        k = np.where(h < cv * N)[0]
        rounds = int(k[0]) if len(k) else len(h)
        out[f'life_c{int(cv*100)}_days'] = min(rounds * c['Tr'] * SCALE / 86400.0, CAP_DAYS)
    out['delay_s'] = r['delay']; out['latency_max_s'] = (1 + c['a']) * c['Tr'] + 2 * c['Tci']; out['sampling_s'] = c['Tr'] / c['F']
    return out

if __name__ == '__main__':
    seeds = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    outp = sys.argv[2] if len(sys.argv) > 2 else 'gt_table.csv'
    cfgs = list(grid())
    jobs = [(d, i, c, s) for d in DEPLOY for i, c in enumerate(cfgs) for s in range(seeds)]
    print(len(cfgs), 'configs,', len(jobs), 'runs', flush=True)
    with Pool() as pl:
        rows = pl.map(job, jobs, chunksize=8)
    with open(outp, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    print('wrote', outp, len(rows))
