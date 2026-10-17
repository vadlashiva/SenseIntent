"""Shared constants and the configuration grid (standard library only).

Radio/packet constants mirror the published HCB-XL simulator (hcbxl.py, dict P); the simulator
itself is only read by gt_table.py and never modified.
"""
import itertools

# from hcbxl.py (P): battery and first-order radio model
E0_SIM, EST, EELEC, EFS, EDA, H, L = 5.0, 20e-6, 50e-9, 10e-12, 5e-9, 2000, 2000

E0_REAL = 20e3            # two AA cells, usable energy about 20 kJ
SCALE = E0_REAL / E0_SIM
P_SL = 15e-6              # sleep power (W) of a TelosB-class mote, about 5 uA at 3 V
CAP_DAYS = 10 * 365       # alkaline shelf life caps any lifetime at 10 years
COVER = (1.0, 0.9, 0.75, 0.5)
# Low-power-listening MAC (B-MAC/X-MAC style), CC2420-class radio
P_RX, P_TX, T_L = 59e-3, 52e-3, 2.5e-3   # receive/transmit power (W), channel-check time (s)

DEPLOY = {  # name: overrides of the simulator defaults
    'farm':     dict(N=100, M=100.0, bs=(50.0, 50.0)),
    'orchard':  dict(N=100, M=150.0, bs=(75.0, 75.0)),
    'building': dict(N=50,  M=50.0,  bs=(25.0, 25.0)),
}


def grid():
    for p, Tr, F, Tci in itertools.product((0.05, 0.1, 0.2), (30, 60, 300, 900, 3600), (1, 5, 10, 30),
                                           (0.125, 0.25, 0.5, 1.0, 2.0)):
        e = 'leach'
        yield dict(p=p, Tr=Tr, F=F, B=1, Tci=Tci, e=e, a=0)            # no buffering
        for B in (5, 10, 30):
            if B > F and B != 5:                                       # batches larger than F are identical
                continue
            for a in (0, 1):
                yield dict(p=p, Tr=Tr, F=F, B=B, Tci=Tci, e=e, a=a)
