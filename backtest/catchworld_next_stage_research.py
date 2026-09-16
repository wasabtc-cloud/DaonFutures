"""CatchWorld next-stage research.
Runs FIRST/RELOAD retrospective labels plus chronological causal candidate validation.
Future MFE is label only. No capital simulation and no threshold optimization to target returns.
"""
from pathlib import Path
import glob, pandas as pd, numpy as np
OUT=Path('results/next_stage'); OUT.mkdir(parents=True,exist_ok=True)
D=[]
for f in glob.glob('strategy_b_input/**/*.csv',recursive=True):
 try:
  d=pd.read_csv(f)
  if {'market','time','close','fwd_mfe_24h','fwd_mfe_72h','turn_ratio','turnover','ret_24h'}.issubset(d): D.append(d)
 except Exception: pass
x=pd.concat(D,ignore_index=True).drop_duplicates(['market','time']); x.time=pd.to_datetime(x.time,utc=True); x=x.sort_values(['market','time'])
cols=['close','fwd_mfe_24h','fwd_mfe_72h','turn_ratio','turn_accel_6_24','turnover','range24','range72','drawdown_30d','ret_6h','ret_12h','ret_24h','ret_72h']
for c in cols:
 if c in x: x[c]=pd.to_numeric(x[c],errors='coerce')
# Retrospective pump anchors and FIRST/RELOAD labels.
labels=[]
for m,g in x.groupby('market'):
 g=g.reset_index(drop=True); last=None
 for _,r in g[g.fwd_mfe_24h>=.20].iterrows():
  if last is not None and (r.time-last).total_seconds()<72*3600: continue
  pre=g[(g.time>=r.time-pd.Timedelta(hours=168))&(g.time<r.time)]
  if len(pre):
   hi=pre.close.max(); lo=pre.close.min(); prior_leg=(hi/lo-1)>=.20 if lo>0 else False; pull=(r.close/hi-1)<=-.05 if hi>0 else False
  else: hi=lo=np.nan; prior_leg=pull=False
  labels.append({'market':m,'anchor':r.time,'kind':'RELOAD' if prior_leg and pull else 'FIRST','prior_hi':hi,'prior_lo':lo})
  last=r.time
lab=pd.DataFrame(labels); lab.to_csv(OUT/'first_reload.csv',index=False)
# Causal candidate population: activity elevated, price not already >10% in prior 24h.
c=x[(x.turn_ratio>=2)&(x.ret_24h<.10)].copy(); c['y20_72']=(c.fwd_mfe_72h>=.20).astype(int)
# Chronological 70/30 holdout, untouched by candidate definition.
cut=c.time.quantile(.70); c['split']=np.where(c.time<cut,'DEV','HOLD')
# Descriptive causal feature bins learned independently per split, no winner selection.
c['flow_bin']=pd.cut(c.turn_ratio,[-np.inf,2,4,8,np.inf],labels=['2-4','4-8','8+','X'],right=False)
c['price_state']=pd.cut(c.ret_24h,[-np.inf,-.07,-.01,.03,.07,.10],labels=['DROP','SOFT','FLAT','RISING','HOT'],right=False)
summary=c.groupby(['split','flow_bin','price_state'],observed=True).y20_72.agg(['count','mean']).reset_index(); summary.to_csv(OUT/'causal_bins.csv',index=False)
# Sequence persistence using only past 6 hours.
parts=[]
for m,g in c.groupby('market'):
 g=g.sort_values('time').copy(); g['flow2_hits_prev6']=g.set_index('time').turn_ratio.rolling('6h').apply(lambda s:(s>=2).sum(),raw=False).to_numpy(); parts.append(g)
c=pd.concat(parts).sort_values(['market','time']); c[['market','time','split','turn_ratio','ret_24h','flow2_hits_prev6','y20_72']].to_csv(OUT/'candidate_sequence.csv',index=False)
persist=c.groupby(['split','flow2_hits_prev6']).y20_72.agg(['count','mean']).reset_index(); persist.to_csv(OUT/'persistence.csv',index=False)
print('CUT',cut,'ANCHORS',len(lab),lab.kind.value_counts().to_dict()); print('CANDIDATES',len(c)); print(summary[summary['count']>=100].sort_values(['split','mean'],ascending=[True,False]).head(30).to_string(index=False))
