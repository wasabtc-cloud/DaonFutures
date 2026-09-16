"""Pre-ignition FIRST/RELOAD study.
Question: before price is already hot, which causal sequences separate future +20% movers?
Future MFE is label only. Threshold grid is fixed a priori and DEV/HOLD are reported separately.
"""
from pathlib import Path
import glob,pandas as pd,numpy as np
OUT=Path('results/preignition_first_reload');OUT.mkdir(parents=True,exist_ok=True);D=[]
for f in glob.glob('strategy_b_input/**/*.csv',recursive=True):
 try:
  d=pd.read_csv(f)
  req={'market','time','close','fwd_mfe_72h','turn_ratio','turnover','ret_6h','ret_24h'}
  if req.issubset(d):D.append(d)
 except:pass
x=pd.concat(D,ignore_index=True).drop_duplicates(['market','time']);x.time=pd.to_datetime(x.time,utc=True);x=x.sort_values(['market','time'])
for c in ['close','fwd_mfe_72h','turn_ratio','turn_accel_6_24','turnover','range24','range72','drawdown_30d','ret_6h','ret_12h','ret_24h','ret_72h']:
 if c in x:x[c]=pd.to_numeric(x[c],errors='coerce')
# Pre-ignition only: exclude already-hot 24h moves. Label remains future-only.
c=x[(x.ret_24h>=-.07)&(x.ret_24h<=.03)&(x.turn_ratio>=2)].copy();c['y']=(c.fwd_mfe_72h>=.20).astype(int)
cut=c.time.quantile(.70);c['split']=np.where(c.time<cut,'DEV','HOLD')
# Causal rolling history computed from full market timeline, then sampled at candidates.
feat=[]
for m,g in x.groupby('market'):
 g=g.sort_values('time').set_index('time'); q=g[['turn_ratio','turnover','ret_6h','ret_24h']].copy()
 q['flow2_h6']=q.turn_ratio.rolling('6h').apply(lambda s:(s>=2).sum(),raw=False)
 q['flow4_h6']=q.turn_ratio.rolling('6h').apply(lambda s:(s>=4).sum(),raw=False)
 q['flow2_h12']=q.turn_ratio.rolling('12h').apply(lambda s:(s>=2).sum(),raw=False)
 q['turn_med6']=q.turn_ratio.rolling('6h').median();q['turn_med12']=q.turn_ratio.rolling('12h').median()
 q['ret6_min12']=q.ret_6h.rolling('12h').min();q['ret6_max12']=q.ret_6h.rolling('12h').max();q=q.reset_index();q['market']=m;feat.append(q[['market','time','flow2_h6','flow4_h6','flow2_h12','turn_med6','turn_med12','ret6_min12','ret6_max12']])
f=pd.concat(feat,ignore_index=True);c=c.merge(f,on=['market','time'],how='left')
# Retrospective lifecycle label from prior 7d only; no future used for FIRST/RELOAD assignment.
def lifecycle(g):
 g=g.sort_values('time').copy(); close=g.close; g['hi7']=close.shift(1).rolling(168,min_periods=24).max();g['lo7']=close.shift(1).rolling(168,min_periods=24).min();
 g['prior_leg']=(g.hi7/g.lo7-1)>=.20;g['pullback']=(g.close/g.hi7-1)<=-.05;g['kind']=np.where(g.prior_leg&g.pullback,'RELOAD','FIRST');return g
c=c.groupby('market',group_keys=False).apply(lifecycle,include_groups=False).reset_index(drop=True)
# Fixed persistence views, not optimized.
rows=[]
for split in ['DEV','HOLD']:
 z=c[c.split==split]
 for kind in ['FIRST','RELOAD']:
  a=z[z.kind==kind]
  for name,mask in [('ALL',np.ones(len(a),dtype=bool)),('PERSIST2',a.flow2_h6>=3),('PERSIST4',a.flow4_h6>=2),('RESTRAINT',a.ret_24h.abs()<=.02),('PERSIST4_RESTRAINT',(a.flow4_h6>=2)&(a.ret_24h.abs()<=.02))]:
   b=a[mask];rows.append({'split':split,'kind':kind,'view':name,'n':len(b),'p20_72':b.y.mean() if len(b) else np.nan})
s=pd.DataFrame(rows);s.to_csv(OUT/'fixed_views.csv',index=False);c.to_csv(OUT/'preignition_candidates.csv',index=False)
print('CUT',cut,'CANDIDATES',len(c));print(s.to_string(index=False))
