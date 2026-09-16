"""Pre-ignition FIRST/RELOAD study v2: true causal prior-168h lifecycle.
Future MFE is label only; DEV/HOLD reported separately.
"""
from pathlib import Path
import glob,pandas as pd,numpy as np
OUT=Path('results/preignition_first_reload');OUT.mkdir(parents=True,exist_ok=True);D=[]
for f in glob.glob('strategy_b_input/**/*.csv',recursive=True):
 try:
  d=pd.read_csv(f);req={'market','time','close','fwd_mfe_72h','turn_ratio','turnover','ret_6h','ret_24h'}
  if req.issubset(d):D.append(d)
 except:pass
x=pd.concat(D,ignore_index=True).drop_duplicates(['market','time']);x.time=pd.to_datetime(x.time,utc=True);x=x.sort_values(['market','time'])
for k in ['close','fwd_mfe_72h','turn_ratio','turn_accel_6_24','turnover','range24','range72','drawdown_30d','ret_6h','ret_12h','ret_24h','ret_72h']:
 if k in x:x[k]=pd.to_numeric(x[k],errors='coerce')
# Build every causal rolling feature on FULL hourly timeline before candidate sampling.
feat=[]
for m,g in x.groupby('market'):
 g=g.sort_values('time').set_index('time');q=g[['close','turn_ratio','turnover','ret_6h','ret_24h']].copy()
 q['flow2_h6']=q.turn_ratio.rolling('6h').apply(lambda s:(s>=2).sum(),raw=False);q['flow4_h6']=q.turn_ratio.rolling('6h').apply(lambda s:(s>=4).sum(),raw=False);q['flow2_h12']=q.turn_ratio.rolling('12h').apply(lambda s:(s>=2).sum(),raw=False)
 q['turn_med6']=q.turn_ratio.rolling('6h').median();q['turn_med12']=q.turn_ratio.rolling('12h').median();q['ret6_min12']=q.ret_6h.rolling('12h').min();q['ret6_max12']=q.ret_6h.rolling('12h').max()
 # Exact prior calendar 168h, excluding current observation.
 q['hi7']=q.close.shift(1).rolling('168h',min_periods=24).max();q['lo7']=q.close.shift(1).rolling('168h',min_periods=24).min();q=q.reset_index();q['market']=m
 feat.append(q[['market','time','flow2_h6','flow4_h6','flow2_h12','turn_med6','turn_med12','ret6_min12','ret6_max12','hi7','lo7']])
f=pd.concat(feat,ignore_index=True)
c=x[(x.ret_24h>=-.07)&(x.ret_24h<=.03)&(x.turn_ratio>=2)].copy();c['y']=(c.fwd_mfe_72h>=.20).astype(int);c=c.merge(f,on=['market','time'],how='left')
c['prior_leg']=(c.hi7/c.lo7-1)>=.20;c['pullback']=(c.close/c.hi7-1)<=-.05;c['kind']=np.where(c.prior_leg&c.pullback,'RELOAD','FIRST')
cut=c.time.quantile(.70);c['split']=np.where(c.time<cut,'DEV','HOLD')
rows=[]
for split in ['DEV','HOLD']:
 z=c[c.split==split]
 for kind in ['FIRST','RELOAD']:
  a=z[z.kind==kind]
  views=[('ALL',np.ones(len(a),dtype=bool)),('PERSIST2',a.flow2_h6>=3),('PERSIST4',a.flow4_h6>=2),('RESTRAINT',a.ret_24h.abs()<=.02),('PERSIST4_RESTRAINT',(a.flow4_h6>=2)&(a.ret_24h.abs()<=.02))]
  for name,mask in views:
   b=a[mask];rows.append({'split':split,'kind':kind,'view':name,'n':len(b),'p20_72':b.y.mean() if len(b) else np.nan})
s=pd.DataFrame(rows);s.to_csv(OUT/'fixed_views.csv',index=False);c.to_csv(OUT/'preignition_candidates.csv',index=False)
print('VERSION TRUE_168H');print('CUT',cut,'CANDIDATES',len(c));print(s.to_string(index=False))
