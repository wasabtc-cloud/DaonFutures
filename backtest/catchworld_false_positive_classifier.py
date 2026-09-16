"""CatchWorld false-positive diagnostics.
Rule-based descriptive buckets for controls; not a fitted strategy and not BUY logic.
Uses only contemporaneous/prior scout features to explain common failure modes.
"""
from pathlib import Path
import pandas as pd, glob, numpy as np
OUT=Path('results/false_positive_diagnostics');OUT.mkdir(parents=True,exist_ok=True)
D=[]
for f in glob.glob('strategy_b_input/**/*.csv',recursive=True):
 try:
  d=pd.read_csv(f)
  if {'market','time','fwd_mfe_72h','turn_ratio','ret_24h'}.issubset(d):D.append(d)
 except:pass
x=pd.concat(D,ignore_index=True).drop_duplicates(['market','time']);x.time=pd.to_datetime(x.time,utc=True)
for c in ['turn_ratio','turn_accel_6_24','range24','range72','drawdown_30d','ret_6h','ret_24h','ret_72h','fwd_mfe_72h']:x[c]=pd.to_numeric(x[c],errors='coerce')
# Candidate activity only; future label solely decides success/failure after candidate exists.
c=x[(x.turn_ratio>=2)&(x.ret_24h.abs()<.10)].copy();c['success']=c.fwd_mfe_72h>=.20
# Diagnostic tags are deliberately broad; quantify rather than optimize them.
def tag(r):
 z=[]
 if r.range24>=.15:z.append('ALREADY_VOLATILE')
 if r.ret_24h>=.07:z.append('ALREADY_RISING')
 if r.ret_24h<=-.07:z.append('FALLING_KNIFE')
 if r.drawdown_30d<=-.45:z.append('DEEP_DRAWDOWN')
 if r.turn_accel_6_24>=2 and r.turn_ratio<4:z.append('ONE_SHOT_ACCEL')
 if abs(r.ret_6h)<.01 and r.turn_ratio>=4:z.append('HIGH_FLOW_NO_RESPONSE')
 if not z:z.append('UNCLASSIFIED')
 return '|'.join(z)
c['diagnostic']=c.apply(tag,axis=1);c.to_csv(OUT/'candidate_diagnostics.csv',index=False)
q=c.assign(tag=c.diagnostic.str.split('|')).explode('tag').groupby('tag').success.agg(['count','mean']).sort_values('count',ascending=False);q.to_csv(OUT/'diagnostic_summary.csv')
print('CANDIDATES',len(c),'SUCCESS_RATE',c.success.mean());print(q.to_string())
