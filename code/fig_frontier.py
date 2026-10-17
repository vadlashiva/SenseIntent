import pandas as pd, numpy as np, matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
df=pd.read_csv('../data/gt_table.csv'); keys=['deploy','cid','latency_max_s','sampling_s']
T=df.groupby(keys,as_index=False)['life_c100_days'].min(); f=T[T.deploy=='farm']
D=np.array([35,65,125,305,605,905,1805,3605,7205])
plt.rcParams.update({'font.family':'DejaVu Serif','font.size':8})
fig,ax=plt.subplots(figsize=(3.5,2.4),dpi=300)
series=[(10,'sampling ≤ 10 s','#2a78d6'),(60,'sampling ≤ 1 min','#eb6834'),(900,'sampling ≤ 15 min','#1baf7a')]
for S,lab,col in series:
    y=[f[(f.latency_max_s<=d)&(f.sampling_s<=S)].life_c100_days.max()/365 for d in D]
    ax.plot(D/60,y,'-o',color=col,lw=1.5,ms=3.5,label=lab)
ax.set_xscale('log'); ax.set_xticks([1,2,5,10,30,60,120]); ax.set_xticklabels(['1','2','5','10','30','60','120'])
ax.set_xlabel('Maximum reporting latency (min)'); ax.set_ylabel('Best achievable lifetime (years)')
ax.grid(True,which='major',color='#e3e2dc',lw=0.6); ax.set_axisbelow(True)
for s in ('top','right'): ax.spines[s].set_visible(False)
ax.legend(frameon=False,loc='upper left'); fig.tight_layout(); fig.savefig('../figures/fig_frontier.png'); print('ok')
