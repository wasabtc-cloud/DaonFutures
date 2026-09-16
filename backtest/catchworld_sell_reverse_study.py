"""CatchWorld SELL reverse study.
Independent of entry logic. For pump anchors, locate subsequent 72h peak using future prices only
for research alignment, then inspect PRIOR snapshots leading into peak. Do not use as live signal.
"""
from pathlib import Path
import glob,pandas as pd,numpy as np
OUT=Path('results/sell_reverse');OUT.mkdir(parents=True,exist_ok=True)
D=[]
for f in glob.glob('strategy_b_input/**/*.csv',recursive=True):
 try:
  d=pd.read_csv(f)
  if {'market','time','close','fwd_mfe_24h'}.issubset(d):D.append(d)
 except:pass
x=pd.concat(D,ignore_index=True).drop_duplicates(['market','time']);x.time=pd.to_datetime(x.time,utc=True);x=x.sort_values(['market','time'])
for c in ['close','turn_ratio','turn_accel_6_24','turnover','range24','range72','ret_6h','ret_12h','ret_24h','ret_72h','fwd_mfe_24h']:x[c]=pd.to_numeric(x[c],errors='coerce')
rows=[]
for m,g in x.groupby('market'):
 g=g.reset_index(drop=True); last=None
 for i,r in g[g.fwd_mfe_24h>=.20].iterrows():
  if last is not None and (r.time-last).total_seconds()<72*3600:continue
  last=r.time; future=g[(g.time>=r.time)&(g.time<=r.time+pd.Timedelta(hours=72))]
  if future.empty:continue
  peak=future.loc[future.close.idxmax()]; pt=peak.time; pp=peak.close
  for h in [12,6,3,1,0,-1,-3,-6,-12]:
   target=pt-pd.Timedelta(hours=h) if h>=0 else pt+pd.Timedelta(hours=-h)
   q=g[g.time<=target]
   if q.empty:continue
   z=q.iloc[-1]; rows.append({'market':m,'anchor':r.time,'peak_time':pt,'peak_price':pp,'relative_peak_h':h,
    'close':z.close,'ret_from_peak':z.close/pp-1,'turn_ratio':z.turn_ratio,'turn_accel_6_24':z.turn_accel_6_24,'turnover':z.turnover,
    'range24':z.range24,'range72':z.range72,'ret_6h':z.ret_6h,'ret_12h':z.ret_12h,'ret_24h':z.ret_24h,'ret_72h':z.ret_72h})
r=pd.DataFrame(rows);r.to_csv(OUT/'sell_peak_timeline.csv',index=False)
s=r.groupby('relative_peak_h').median(numeric_only=True).reset_index();s.to_csv(OUT/'sell_peak_medians.csv',index=False)
print('EVENTS',r[['market','anchor']].drop_duplicates().shape[0]);print(s.to_string(index=False))
