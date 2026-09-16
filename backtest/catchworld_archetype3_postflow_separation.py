import glob,os
import numpy as np,pandas as pd
OUT='results/archetype3_postflow_separation';os.makedirs(OUT,exist_ok=True)
fs=glob.glob('strategy_b_input/**/*.csv',recursive=True);d=pd.concat([pd.read_csv(f) for f in fs],ignore_index=True)
d.time=pd.to_datetime(d.time,utc=True,errors='coerce');d=d.dropna(subset=['time']).drop_duplicates(['market','time']).sort_values(['market','time'])
num=['turn_ratio','turn_accel_6_24','ret_6h','ret_12h','ret_24h','ret_72h','range24','range72','drawdown_30d','fwd_mfe_24h','fwd_mfe_72h']
for c in num:d[c]=pd.to_numeric(d[c],errors='coerce')
d['mfe24pct']=d.fwd_mfe_24h*100;d['mfe72pct']=d.fwd_mfe_72h*100
# Use prior validation's exact positive target logic, then 4x3 signal; controls same construction.
feat=['turn_ratio','turn_accel_6_24','range24','range72','drawdown_30d','ret_6h','ret_12h','ret_24h','ret_72h','ret_168h','ret_336h','ret_720h']
for c in feat:
 if c not in d:d[c]=np.nan
 d[c]=pd.to_numeric(d[c],errors='coerce')
cand=d[d.mfe24pct>=20].sort_values(['market','time']);ids=[];last={}
for i,r in cand.iterrows():
 if r.market not in last or (r.time-last[r.market]).total_seconds()>=72*3600:ids.append(i);last[r.market]=r.time
e=d.loc[ids,['market','time']+feat].copy();X=e[feat].replace([np.inf,-np.inf],np.nan);med=X.median();X=X.fillna(med);scale=(X.quantile(.75)-X.quantile(.25)).replace(0,1);Z=((X-med)/scale).clip(-8,8).to_numpy(float);rng=np.random.default_rng(42);C=Z[rng.choice(len(Z),3,replace=False)].copy()
for _ in range(80):
 ds=((Z[:,None,:]-C[None,:,:])**2).sum(2);lab=ds.argmin(1);N=np.vstack([Z[lab==j].mean(0) if np.any(lab==j) else C[j] for j in range(3)])
 if np.allclose(C,N,atol=1e-5):break
 C=N
e['cluster']=lab;target=e[e.cluster==2][['market','time']].rename(columns={'time':'anchor'})
by={m:g.set_index('time').sort_index() for m,g in d.groupby('market',sort=False)}
pump_times={m:np.array(g.time.values,dtype='datetime64[ns]') for m,g in e.groupby('market')}
def sig4(m,t):
 g=by[m].loc[(by[m].index>=t-pd.Timedelta(hours=48))&(by[m].index<t),['turn_ratio','turn_accel_6_24','ret_24h']]
 hit=((g.turn_ratio>=4)&(g.ret_24h<.10)).astype('int8');acc=(g.turn_accel_6_24>=1).astype('int8');ok=(hit.rolling('48h',min_periods=1).sum()>=3)&(acc.rolling('48h',min_periods=1).sum()>=1)
 return ok.index[np.flatnonzero(ok.to_numpy())[0]] if ok.any() else None
pos=[]
for ev in target.itertuples(index=False):
 s=sig4(ev.market,ev.anchor)
 if s is not None:pos.append((ev.market,ev.anchor,s,1))
controls=[]
for ev in target.itertuples(index=False):
 g=by[ev.market];c=g.loc[(g.index>=ev.anchor-pd.Timedelta(days=45))&(g.index<=ev.anchor+pd.Timedelta(days=45))&(g.mfe72pct<20)&g.turn_ratio.notna()]
 pts=pump_times.get(ev.market,np.array([],dtype='datetime64[ns]'))
 if len(c) and len(pts):
  tt=c.index.values.astype('datetime64[ns]');dist=np.min(np.abs(tt[:,None]-pts[None,:]),axis=1)/np.timedelta64(1,'h');c=c.iloc[np.where(dist>=96)[0]]
 if len(c)>5:c=c.iloc[np.linspace(0,len(c)-1,5).round().astype(int)]
 for t in c.index:
  s=sig4(ev.market,t)
  if s is not None:controls.append((ev.market,t,s,0))
controls=pd.DataFrame(controls,columns=['market','anchor','signal','label']).drop_duplicates(['market','anchor']);cases=pd.concat([pd.DataFrame(pos,columns=controls.columns),controls],ignore_index=True);print('POS',sum(cases.label==1),'FALSE',sum(cases.label==0))
# Compare only information AFTER the common 4x3 signal. Find when groups separate, not new strategy thresholds.
rows=[]
for z in cases.itertuples(index=False):
 g=by[z.market]
 for h in [1,3,6,12,24]:
  w=g.loc[(g.index>z.signal)&(g.index<=z.signal+pd.Timedelta(hours=h))]
  if not len(w):continue
  p0=float(g.loc[:z.signal].close.iloc[-1]);ret=float(w.close.iloc[-1]/p0-1);low=float(w.close.min()/p0-1);high=float(w.close.max()/p0-1)
  rows.append({'market':z.market,'signal':z.signal,'anchor':z.anchor,'label':z.label,'h':h,'ret':ret,'low_ret':low,'high_ret':high,'turn_ratio_med':w.turn_ratio.median(),'turn_ratio_last':w.turn_ratio.iloc[-1],'accel_med':w.turn_accel_6_24.median(),'ret24_last':w.ret_24h.iloc[-1],'range24_last':w.range24.iloc[-1],'defense':low,'expansion':high-low})
r=pd.DataFrame(rows);r.to_csv(OUT+'/post_signal_cases.csv',index=False)
s=[]
for h,g in r.groupby('h'):
 for c in ['ret','low_ret','high_ret','turn_ratio_med','turn_ratio_last','accel_med','ret24_last','range24_last','expansion']:
  a=g[g.label==1][c];b=g[g.label==0][c];s.append({'h':h,'feature':c,'positive_median':a.median(),'false_median':b.median(),'median_gap':a.median()-b.median(),'positive_q25':a.quantile(.25),'false_q25':b.quantile(.25),'positive_q75':a.quantile(.75),'false_q75':b.quantile(.75)})
pd.DataFrame(s).to_csv(OUT+'/separation_summary.csv',index=False);cases.to_csv(OUT+'/cases_4x3.csv',index=False)
# rank absolute robust median separation for description only
q=pd.DataFrame(s);q['scale']=(q.positive_q75-q.positive_q25).abs()+(q.false_q75-q.false_q25).abs();q['sep_score']=q.median_gap.abs()/(q['scale']/2).replace(0,np.nan);print(q.sort_values('sep_score',ascending=False).head(20).to_string(index=False))
