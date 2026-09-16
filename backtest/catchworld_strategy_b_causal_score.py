import glob, os
import numpy as np
import pandas as pd

IN='strategy_b_input'; OUT='results/strategy_b_causal_score'; os.makedirs(OUT,exist_ok=True)
fs=glob.glob(f'{IN}/**/*.csv',recursive=True); ds=[]
for f in fs:
 try:
  d=pd.read_csv(f)
  if len(d): ds.append(d)
 except Exception as e: print('SKIP',f,e)
df=pd.concat(ds,ignore_index=True); df['time']=pd.to_datetime(df.time,utc=True,errors='coerce'); df=df.dropna(subset=['time']).sort_values(['time','market'])
# causal inputs only. No future columns are allowed in score.
for c in ['range24','range72','ret_6h','ret_12h','ret_24h','ret_72h','ret_168h','ret_336h','ret_720h','turn_ratio','turn_accel_6_24','drawdown_30d','turnover']:
 if c in df: df[c]=pd.to_numeric(df[c],errors='coerce')
# Outcome used only after signal creation for evaluation.
y=100*pd.to_numeric(df['fwd_mfe_24h'],errors='coerce')
# chronological 70/30 split; thresholds learned from DEV only
cut=df.time.quantile(.70); dev=df[df.time<=cut].copy(); hold=df[df.time>cut].copy(); print('CUT',cut,'DEV',len(dev),'HOLD',len(hold))
features=['range24','range72','turn_ratio','turn_accel_6_24','ret_6h','ret_12h','ret_24h','ret_72h','ret_168h','drawdown_30d']
qs={}
for c in features:
 if c in dev: qs[c]={q:dev[c].quantile(q) for q in [.25,.4,.5,.6,.7,.75,.8,.85,.9]}
# App-oriented staged score. Prefer activity before excessive price extension.
def score(x):
 s=np.zeros(len(x),dtype=float)
 # unusual turnover / acceleration
 if 'turn_ratio' in x:
  s += np.where(x.turn_ratio>=qs['turn_ratio'][.75],18,0); s += np.where(x.turn_ratio>=qs['turn_ratio'][.9],10,0)
 if 'turn_accel_6_24' in x: s += np.where(x.turn_accel_6_24>=qs['turn_accel_6_24'][.7],10,0)
 # expanding range, but avoid requiring an already huge return
 if 'range24' in x: s += np.where(x.range24>=qs['range24'][.7],12,0)
 if 'range72' in x: s += np.where(x.range72>=qs['range72'][.7],8,0)
 # early positive structure, not chase: 24h return between dev median and 85th percentile
 if 'ret_24h' in x:
  s += np.where((x.ret_24h>=qs['ret_24h'][.5])&(x.ret_24h<=qs['ret_24h'][.85]),12,0)
 if 'ret_72h' in x:
  s += np.where((x.ret_72h>=qs['ret_72h'][.5])&(x.ret_72h<=qs['ret_72h'][.85]),8,0)
 # base/accumulation context: still below 30d high
 if 'drawdown_30d' in x: s += np.where(x.drawdown_30d<=qs['drawdown_30d'][.5],12,0)
 return np.clip(s,0,100)
for x in [dev,hold]: x['score']=score(x)
# stage semantics for future app
bins=[-1,39,59,74,84,101]; labels=['WATCH','DETECT','READY','ENTRY_WAIT','HOT']
for x in [dev,hold]: x['stage']=pd.cut(x.score,bins=bins,labels=labels)
# Evaluate score without using future info in selection.
def report(x,name):
 yy=100*pd.to_numeric(x.fwd_mfe_24h,errors='coerce'); base=(yy>=20).mean(); rows=[]
 for th in [40,50,60,70,75,80,85,90]:
  m=x.score>=th; n=int(m.sum()); hit=int((yy[m]>=20).sum()) if n else 0
  rows.append({'set':name,'score_ge':th,'signals':n,'hit20':hit,'precision20':hit/n if n else np.nan,'recall20':hit/max(1,int((yy>=20).sum())),'lift_vs_base':(hit/n/base) if n and base else np.nan,'median_mfe24_pct':yy[m].median() if n else np.nan,'hit30':int((yy[m]>=30).sum()) if n else 0,'hit50':int((yy[m]>=50).sum()) if n else 0})
 return rows
res=pd.DataFrame(report(dev,'DEV')+report(hold,'HOLDOUT')); res.to_csv(f'{OUT}/threshold_validation.csv',index=False); print(res.to_string(index=False))
# state distribution and candidate examples
pd.concat([dev.assign(set='DEV'),hold.assign(set='HOLDOUT')]).groupby(['set','stage'],observed=True).size().rename('rows').reset_index().to_csv(f'{OUT}/stage_counts.csv',index=False)
cols=['market','time','score','stage','fwd_mfe_24h']+[c for c in features if c in hold]
hold.sort_values(['score','time'],ascending=[False,True])[cols].head(1000).to_csv(f'{OUT}/holdout_top_candidates.csv',index=False)
print('APP_STAGE: WATCH<40 DETECT40-59 READY60-74 ENTRY_WAIT75-84 HOT>=85')
