import glob, os
import numpy as np
import pandas as pd

OUT='results/archetype3_timeline'; os.makedirs(OUT,exist_ok=True)
fs=glob.glob('strategy_b_input/**/*.csv',recursive=True)
d=pd.concat([pd.read_csv(f) for f in fs],ignore_index=True)
d['time']=pd.to_datetime(d['time'],utc=True,errors='coerce')
d=d.dropna(subset=['time']).drop_duplicates(['market','time']).sort_values(['market','time'])
num=['turn_ratio','turn_accel_6_24','range24','range72','drawdown_30d','ret_6h','ret_12h','ret_24h','ret_72h','ret_168h','ret_336h','ret_720h','fwd_mfe_24h','fwd_mfe_72h']
for c in num:d[c]=pd.to_numeric(d[c],errors='coerce')
for c in ['fwd_mfe_24h','fwd_mfe_72h']:d[c]*=100
feat=['turn_ratio','turn_accel_6_24','range24','range72','drawdown_30d','ret_6h','ret_12h','ret_24h','ret_72h','ret_168h','ret_336h','ret_720h']
# Reproduce pump episodes and exact deterministic clustering from archetype discovery.
cand=d[d.fwd_mfe_24h>=20].sort_values(['market','time']); ids=[]; last={}
for i,r in cand.iterrows():
    if r.market not in last or (r.time-last[r.market]).total_seconds()>=72*3600:
        ids.append(i); last[r.market]=r.time
e=d.loc[ids,['market','time']+feat+['fwd_mfe_24h','fwd_mfe_72h']].copy()
X=e[feat].replace([np.inf,-np.inf],np.nan); med=X.median(); X=X.fillna(med); q1=X.quantile(.25); q3=X.quantile(.75); scale=(q3-q1).replace(0,1); Z=((X-med)/scale).clip(-8,8).to_numpy(float)
rng=np.random.default_rng(42)
def km(Z,k,it=80):
    C=Z[rng.choice(len(Z),k,replace=False)].copy()
    for _ in range(it):
        ds=((Z[:,None,:]-C[None,:,:])**2).sum(2); lab=ds.argmin(1)
        N=np.vstack([Z[lab==j].mean(0) if np.any(lab==j) else C[j] for j in range(k)])
        if np.allclose(C,N,atol=1e-5):break
        C=N
    return lab,C
lab,C=km(Z,3); e['cluster']=lab
# cluster 2 is the 128-event strong-flow archetype from the frozen discovery run.
target=e[e.cluster==2][['market','time','fwd_mfe_24h','fwd_mfe_72h']].copy().rename(columns={'time':'event_time'})
print('TARGET_EVENTS',len(target),'MARKETS',target.market.nunique())
# Inspect causal snapshots before the event anchor. No future labels used in snapshots.
offsets=[720,336,168,72,48,24,12,6,3,1,0]
rows=[]
by={m:g.set_index('time').sort_index() for m,g in d.groupby('market')}
for _,ev in target.iterrows():
    g=by[ev.market]
    for h in offsets:
        t=ev.event_time-pd.Timedelta(hours=h)
        pos=g.index.searchsorted(t,side='right')-1
        if pos<0:continue
        r=g.iloc[pos]
        rows.append({'market':ev.market,'event_time':ev.event_time,'hours_before':h,'snapshot_time':g.index[pos],
                     'turn_ratio':r.turn_ratio,'turn_accel_6_24':r.turn_accel_6_24,'range24':r.range24,'range72':r.range72,
                     'drawdown_30d':r.drawdown_30d,'ret_6h':r.ret_6h,'ret_24h':r.ret_24h,'ret_72h':r.ret_72h,
                     'ret_168h':r.ret_168h,'ret_336h':r.ret_336h,'ret_720h':r.ret_720h})
s=pd.DataFrame(rows)
summary=s.groupby('hours_before').agg(events=('market','size'),markets=('market','nunique'),turn_ratio_med=('turn_ratio','median'),turn_ratio_q75=('turn_ratio',lambda x:x.quantile(.75)),accel_med=('turn_accel_6_24','median'),range24_med=('range24','median'),range72_med=('range72','median'),ret6_med=('ret_6h','median'),ret24_med=('ret_24h','median'),ret72_med=('ret_72h','median'),dd30_med=('drawdown_30d','median')).reset_index().sort_values('hours_before',ascending=False)
# First causal warning time: first observation in prior 30d where turnover is elevated but 24h price is not yet >10%.
warn=[]
for _,ev in target.iterrows():
    g=by[ev.market]; w=g[(g.index>=ev.event_time-pd.Timedelta(days=30))&(g.index<=ev.event_time)].copy()
    cond=(w.turn_ratio>=2)&(w.turn_accel_6_24>=1)&(w.ret_24h<0.10)
    z=w[cond]
    if len(z):
        t=z.index[0]; rr=z.iloc[0]
        warn.append({'market':ev.market,'event_time':ev.event_time,'first_warning':t,'lead_hours':(ev.event_time-t).total_seconds()/3600,'turn_ratio':rr.turn_ratio,'ret24':rr.ret_24h})
w=pd.DataFrame(warn)
summary.to_csv(OUT+'/timeline_summary.csv',index=False); s.to_csv(OUT+'/event_snapshots.csv',index=False); target.to_csv(OUT+'/target_128.csv',index=False); w.to_csv(OUT+'/first_warning.csv',index=False)
print('\nTIMELINE\n',summary.to_string(index=False))
if len(w):
    print('\nEARLY WARNING',len(w),'of',len(target),'median lead hours',w.lead_hours.median(),'q25',w.lead_hours.quantile(.25),'q75',w.lead_hours.quantile(.75))
    print('lead >=24h', (w.lead_hours>=24).mean(),'lead >=72h',(w.lead_hours>=72).mean(),'lead >=168h',(w.lead_hours>=168).mean())
