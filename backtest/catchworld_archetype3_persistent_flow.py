import glob,os
import numpy as np,pandas as pd
OUT='results/archetype3_persistent_flow';os.makedirs(OUT,exist_ok=True)
fs=glob.glob('strategy_b_input/**/*.csv',recursive=True);d=pd.concat([pd.read_csv(f) for f in fs],ignore_index=True)
d.time=pd.to_datetime(d.time,utc=True,errors='coerce');d=d.dropna(subset=['time']).drop_duplicates(['market','time']).sort_values(['market','time'])
cols=['turn_ratio','turn_accel_6_24','ret_24h','ret_6h','fwd_mfe_24h','fwd_mfe_72h']
for c in cols:d[c]=pd.to_numeric(d[c],errors='coerce')
for c in ['fwd_mfe_24h','fwd_mfe_72h']:d[c]*=100
feat=['turn_ratio','turn_accel_6_24','range24','range72','drawdown_30d','ret_6h','ret_12h','ret_24h','ret_72h','ret_168h','ret_336h','ret_720h']
for c in feat:d[c]=pd.to_numeric(d[c],errors='coerce')
# exact frozen 3-cluster reconstruction
cand=d[d.fwd_mfe_24h>=20].sort_values(['market','time']);ids=[];last={}
for i,r in cand.iterrows():
 if r.market not in last or (r.time-last[r.market]).total_seconds()>=72*3600:ids.append(i);last[r.market]=r.time
e=d.loc[ids,['market','time']+feat].copy();X=e[feat].replace([np.inf,-np.inf],np.nan);med=X.median();X=X.fillna(med);scale=(X.quantile(.75)-X.quantile(.25)).replace(0,1);Z=((X-med)/scale).clip(-8,8).to_numpy(float);rng=np.random.default_rng(42);C=Z[rng.choice(len(Z),3,replace=False)].copy()
for _ in range(80):
 ds=((Z[:,None,:]-C[None,:,:])**2).sum(2);lab=ds.argmin(1);N=np.vstack([Z[lab==j].mean(0) if np.any(lab==j) else C[j] for j in range(3)])
 if np.allclose(C,N,atol=1e-5):break
 C=N
e['cluster']=lab;target=e[e.cluster==2][['market','time']].rename(columns={'time':'event_time'})
# Cache each market once and slice only the 48h event windows once.
by_market={m:g.set_index('time').sort_index() for m,g in d.groupby('market',sort=False)}
event_windows=[]
for ev in target.itertuples(index=False):
 g=by_market.get(ev.market)
 if g is None:continue
 w=g.loc[(g.index>=ev.event_time-pd.Timedelta(hours=48))&(g.index<ev.event_time),['turn_ratio','turn_accel_6_24','ret_24h']].copy()
 event_windows.append((ev.market,ev.event_time,w))
rows=[];detail=[]
for tr in [2,3,4]:
 for min_hits in [3,6,12]:
  for span in [12,24,48]:
   caught=0;leads=[]
   for market,event_time,g in event_windows:
    if g.empty:continue
    hit=((g.turn_ratio>=tr)&(g.ret_24h<.10)).astype('int8')
    accel=(g.turn_accel_6_24>=1).astype('int8')
    # Hourly data: rolling window implements the same persistence test without nested dataframe filtering.
    hp=hit.rolling(f'{span}h',min_periods=1).sum();ap=accel.rolling(f'{span}h',min_periods=1).sum()
    ok=(hp>=min_hits)&(ap>=1)
    if ok.any():
     found=ok.index[np.flatnonzero(ok.to_numpy())[0]];caught+=1;lead=(event_time-found).total_seconds()/3600;leads.append(lead);detail.append({'tr':tr,'min_hits':min_hits,'span':span,'market':market,'event_time':event_time,'signal_time':found,'lead_hours':lead})
   a=np.asarray(leads)
   rows.append({'turn_ratio_min':tr,'min_hits':min_hits,'window_hours':span,'caught':caught,'recall_128':caught/len(target),'median_lead_h':np.median(a) if len(a) else np.nan,'lead_ge_6h':np.mean(a>=6) if len(a) else np.nan,'lead_ge_12h':np.mean(a>=12) if len(a) else np.nan,'lead_ge_24h':np.mean(a>=24) if len(a) else np.nan})
r=pd.DataFrame(rows).sort_values(['recall_128','median_lead_h'],ascending=False);q=pd.DataFrame(detail)
r.to_csv(OUT+'/persistent_flow_rules.csv',index=False);q.to_csv(OUT+'/signals.csv',index=False);target.to_csv(OUT+'/target_128.csv',index=False)
print('TARGET',len(target));print(r.to_string(index=False))
