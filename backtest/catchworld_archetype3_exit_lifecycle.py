import glob,os
import numpy as np,pandas as pd
OUT='results/archetype3_exit_lifecycle';os.makedirs(OUT,exist_ok=True)
fs=glob.glob('strategy_b_input/**/*.csv',recursive=True);d=pd.concat([pd.read_csv(f) for f in fs],ignore_index=True)
d.time=pd.to_datetime(d.time,utc=True,errors='coerce');d=d.dropna(subset=['time']).drop_duplicates(['market','time']).sort_values(['market','time'])
cols=['turn_ratio','turn_accel_6_24','range24','range72','drawdown_30d','ret_6h','ret_12h','ret_24h','ret_72h','ret_168h','ret_336h','ret_720h','fwd_mfe_24h']
for c in cols:d[c]=pd.to_numeric(d[c],errors='coerce')
d['mfe24pct']=d.fwd_mfe_24h*100
# same frozen event/cluster reconstruction used in prior validations
cand=d[d.mfe24pct>=20].sort_values(['market','time']);ids=[];last={}
for i,r in cand.iterrows():
 if r.market not in last or (r.time-last[r.market]).total_seconds()>=72*3600:ids.append(i);last[r.market]=r.time
feat=['turn_ratio','turn_accel_6_24','range24','range72','drawdown_30d','ret_6h','ret_12h','ret_24h','ret_72h','ret_168h','ret_336h','ret_720h']
e=d.loc[ids,['market','time']+feat].copy();X=e[feat].replace([np.inf,-np.inf],np.nan);med=X.median();X=X.fillna(med);scale=(X.quantile(.75)-X.quantile(.25)).replace(0,1);Z=((X-med)/scale).clip(-8,8).to_numpy(float);rng=np.random.default_rng(42);C=Z[rng.choice(len(Z),3,replace=False)].copy()
for _ in range(80):
 ds=((Z[:,None,:]-C[None,:,:])**2).sum(2);lab=ds.argmin(1);N=np.vstack([Z[lab==j].mean(0) if np.any(lab==j) else C[j] for j in range(3)])
 if np.allclose(C,N,atol=1e-5):break
 C=N
e['cluster']=lab;target=e[e.cluster==2][['market','time']].rename(columns={'time':'anchor'});print('TARGET',len(target))
by={m:g.set_index('time').sort_index() for m,g in d.groupby('market',sort=False)}
# Anchor is predictive label point, not exact pump onset. Analyze relative lifecycle after anchor using hourly closes.
rows=[];paths=[]
for ev in target.itertuples(index=False):
 g=by[ev.market];w=g.loc[(g.index>=ev.anchor)&(g.index<=ev.anchor+pd.Timedelta(hours=72)),['close','turnover','turn_ratio','turn_accel_6_24']].copy()
 if len(w)<2:continue
 p0=float(w.close.iloc[0]);w['ret']=w.close/p0-1;peak_t=w.ret.idxmax();peak=float(w.ret.max());peak_h=(peak_t-ev.anchor).total_seconds()/3600
 # drawdown from running peak; recovery/reload if a new high occurs >=6h after first +10% touch
 runmax=w.close.cummax();w['dd_from_peak']=w.close/runmax-1
 first10=w.index[w.ret>=.10];reload_flag=0
 if len(first10):
  t10=first10[0]; later=w.loc[w.index>=t10+pd.Timedelta(hours=6)]
  if len(later) and later.ret.max()>w.loc[:t10].ret.max()+.03:reload_flag=1
 # candidate trailing exits, evaluated from anchor with no lookahead in rule itself
 ex={}
 for dd in [.05,.08,.10,.15,.20]:
  hit=w.index[w.dd_from_peak<=-dd]
  if len(hit):t=hit[0];r=float(w.loc[t,'ret'])
  else:t=w.index[-1];r=float(w.ret.iloc[-1])
  ex[f'trail_{int(dd*100)}_ret']=r;ex[f'trail_{int(dd*100)}_capture']=r/peak if peak>0 else np.nan
 # flow deterioration + 8% drawdown: ratio below 1 or accel below .8, after a 10% runup
 cond=(w.dd_from_peak<=-.08)&((w.turn_ratio<1)|(w.turn_accel_6_24<.8))&(runmax/p0-1>=.10)
 hit=w.index[cond.fillna(False)]
 if len(hit):t=hit[0];fr=float(w.loc[t,'ret'])
 else:t=w.index[-1];fr=float(w.ret.iloc[-1])
 rows.append({'market':ev.market,'anchor':ev.anchor,'peak_ret':peak,'peak_h':peak_h,'ret72':float(w.ret.iloc[-1]),'max_dd_after_running_peak':float(w.dd_from_peak.min()),'reload_flag':reload_flag,'flow8_ret':fr,'flow8_capture':fr/peak if peak>0 else np.nan,**ex})
 for h in [0,1,3,6,12,24,36,48,72]:
  z=w.loc[w.index<=ev.anchor+pd.Timedelta(hours=h)]
  if len(z):q=z.iloc[-1];paths.append({'market':ev.market,'anchor':ev.anchor,'h':h,'ret':q.ret,'turn_ratio':q.turn_ratio,'accel':q.turn_accel_6_24,'dd_from_peak':q.dd_from_peak})
r=pd.DataFrame(rows);r.to_csv(OUT+'/event_exit_metrics.csv',index=False);pd.DataFrame(paths).to_csv(OUT+'/lifecycle_snapshots.csv',index=False)
summary={'events':len(r),'peak_ret_median':r.peak_ret.median(),'peak_h_median':r.peak_h.median(),'peak_h_q25':r.peak_h.quantile(.25),'peak_h_q75':r.peak_h.quantile(.75),'ret72_median':r.ret72.median(),'reload_rate':r.reload_flag.mean()}
for k in [5,8,10,15,20]:summary[f'trail{k}_ret_med']=r[f'trail_{k}_ret'].median();summary[f'trail{k}_capture_med']=r[f'trail_{k}_capture'].median()
summary['flow8_ret_med']=r.flow8_ret.median();summary['flow8_capture_med']=r.flow8_capture.median();pd.DataFrame([summary]).to_csv(OUT+'/exit_summary.csv',index=False)
print(pd.DataFrame([summary]).to_string(index=False))
