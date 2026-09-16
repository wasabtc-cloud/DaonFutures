"""Label FIRST vs RELOAD pump lifecycle episodes for research.
Future prices are used only to construct retrospective labels, never live features.
"""
from pathlib import Path
import glob,pandas as pd,numpy as np
OUT=Path('results/first_reload');OUT.mkdir(parents=True,exist_ok=True);D=[]
for f in glob.glob('strategy_b_input/**/*.csv',recursive=True):
 try:
  d=pd.read_csv(f)
  if {'market','time','close','fwd_mfe_24h'}.issubset(d):D.append(d)
 except:pass
x=pd.concat(D,ignore_index=True).drop_duplicates(['market','time']);x.time=pd.to_datetime(x.time,utc=True);x=x.sort_values(['market','time'])
for c in ['close','fwd_mfe_24h','turn_ratio','turn_accel_6_24','ret_24h','ret_72h','range24','drawdown_30d']:x[c]=pd.to_numeric(x[c],errors='coerce')
rows=[]
for m,g in x.groupby('market'):
 g=g.reset_index(drop=True); prev=None
 for _,r in g[g.fwd_mfe_24h>=.20].iterrows():
  if prev is not None and (r.time-prev).total_seconds()<72*3600:continue
  pre=g[(g.time>=r.time-pd.Timedelta(hours=168))&(g.time<r.time)]
  prior_peak=pre.close.max() if len(pre) else np.nan; prior_low=pre.close.min() if len(pre) else np.nan
  had_prior_leg=bool(len(pre) and prior_low>0 and prior_peak/prior_low-1>=.20)
  pullback=prior_peak>0 and r.close/prior_peak-1<=-.05
  kind='RELOAD' if had_prior_leg and pullback else 'FIRST'
  rows.append({'market':m,'anchor':r.time,'kind':kind,'close':r.close,'prior7d_peak':prior_peak,'prior7d_low':prior_low,
               'turn_ratio':r.turn_ratio,'turn_accel_6_24':r.turn_accel_6_24,'ret24':r.ret_24h,'ret72':r.ret_72h,'range24':r.range24,'dd30':r.drawdown_30d})
  prev=r.time
z=pd.DataFrame(rows);z.to_csv(OUT/'first_reload_labels.csv',index=False);print(z.kind.value_counts());print(z.groupby('kind').median(numeric_only=True).to_string())
