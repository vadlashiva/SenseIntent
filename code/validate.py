"""Closed-form lifetime (Eq. life, with LPL terms) vs simulated HND/FND, battery-only, simulator energy units."""
import numpy as np, gt_table as g
q0=dict(g.P)
def Ebar(q,c):
    N,M,p,F,B,H,L,Tr,Tci=q['N'],q['M'],c['p'],c['F'],c['B'],q['H'],q['L'],c['Tr'],c['Tci']
    k=max(p*N,1); dch2=M**2/(2*np.pi*k); dbs2=M**2/6
    Est=q['Est']+g.P_TX*Tci/2; Eid=(g.P_SL+g.T_L/Tci*g.P_RX)*Tr
    cb=B>1; ntx=np.ceil(F/B) if cb else F; bm=ntx*H+F*L
    Em=Eid+ntx*Est+bm*(q['Eelec']+q['efs']*dch2)
    nch=1 if cb else F; bch=(H+F*L) if cb else F*(H+L)
    Ech=Eid+(1/p-1)*bm*q['Eelec']+(1/p)*F*L*q['EDA']+nch*Est+bch*(q['Eelec']+q['efs']*dbs2)
    return (1-p)*Em+p*Ech
cases=[dict(p=0.1,Tr=60,F=10,B=1,Tci=0.5),dict(p=0.1,Tr=60,F=10,B=10,Tci=0.5),dict(p=0.05,Tr=60,F=10,B=10,Tci=1.0),
       dict(p=0.2,Tr=300,F=30,B=30,Tci=1.0),dict(p=0.1,Tr=30,F=1,B=1,Tci=0.125),dict(p=0.1,Tr=900,F=5,B=5,Tci=2.0),
       dict(p=0.1,Tr=3600,F=30,B=30,Tci=2.0),dict(p=0.2,Tr=60,F=30,B=1,Tci=0.25)]
for c in cases:
    c.update(e='leach',a=0); q=dict(q0); q.update(g.DEPLOY['farm'])
    pred=q['E0']/Ebar(q,c)*c['Tr']*g.SCALE/86400
    sims=[g.job(('farm',0,c,s)) for s in range(10)]
    hnd=np.mean([r['life_c50_days'] for r in sims]); fnd=np.mean([r['life_c100_days'] for r in sims])
    print(c['p'],c['Tr'],c['F'],c['B'],c['Tci'],round(min(pred,g.CAP_DAYS)),round(fnd),round(hnd),round(min(pred,g.CAP_DAYS)/hnd,3))
