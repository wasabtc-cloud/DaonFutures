import glob,os
import numpy as np,pandas as pd
OUT='results/pre_pump_30d_reverse';os.makedirs(OUT,exist_ok=True)
fs=glob.glob('strategy_b_input/**/*.csv',recursive=True)
d=pd.concat([pd.read_csv(f) for f in fs],ignore_index=True)
d.time=pd.to_datetime(d.time,utc=True,errors='coerce');d=d.dropna(subset=['time']).drop_duplicates(['market','time']).sort_values(['market','time'])
cols=['turnover','turn_ratio','turn_accel_6_24','range24','range72','drawdown_30d','ret_6h','ret_12h','ret_24h','ret_72h','ret_168h','ret_336h','ret_720h','fwd_mfe_24h','fwd_mfe_72h']
for c in cols:d[c]=pd.to_numeric(d[c],errors='coerce')
# Pump anchors: first hour whose next-24h MFE reaches +20%, 72h cooldown. Future field is LABEL ONLY.
cand=d[d.fwd_mfe_24h>=.20].sort_values(['market','time']); anchors=[]; last={}
for i,r in cand.iterrows():
 if r.market not in last or (r.time-last[r.market]).total_seconds()>=72*3600:
  anchors.append((r.market,r.time));last[r.market]=r.time
print('PUMP_ANCHORS',len(anchors),'MARKETS',len(set(x[0] for x in anchors)))
# Matched controls: same market, outside +/-96h of any pump anchor, and no +20% MFE in next72h.
byanchors={}
for m,t in anchors:byanchors.setdefault(m,[]).append(t)
rng=np.random.default_rng(20260917); controls=[]
for m,ats in byanchors.items():
 g=d[d.market==m]
 ok=g[g.fwd_mfe_72h<.20].copy()
 if len(ok)==0:continue
 mask=np.ones(len(ok),dtype=bool)
 tt=ok.time
 for a in ats: mask &= ((tt-a).abs().dt.total_seconds()>=96*3600).to_numpy()
 ok=ok[mask]
 if len(ok):
  n=min(len(ats)*3,len(ok)); pick=rng.choice(ok.index.to_numpy(),n,replace=False)
  controls += [(m,d.loc[i,'time']) for i in pick]
print('CONTROLS',len(controls))
# Look backwards from each anchor. Focus on money arriving while price is still restrained.
look=[720,336,168,72,24,12,6,1]
features=['turn_ratio','turn_accel_6_24','turnover','range24','range72','drawdown_30d','ret_24h','ret_72h','ret_168h','ret_336h','ret_720h']
def snap(events,label):
 out=[]
 for m,a in events:
  g=d[d.market==m]
  for h in look:
   target=a-pd.Timedelta(hours=h)
   z=g[g.time<=target].tail(1)
   if z.empty:continue
   r=z.iloc[0]; row={'label':label,'market':m,'anchor':a,'lookback_h':h,'sample_time':r.time}
   for c in features:row[c]=r[c]
   # causal proxy: abnormal turnover while price has not already run away
   row['quiet_flow']=int(pd.notna(r.turn_ratio) and r.turn_ratio>=2 and pd.notna(r.ret_24h) and abs(r.ret_24h)<.05)
   row['strong_quiet_flow']=int(pd.notna(r.turn_ratio) and r.turn_ratio>=4 and pd.notna(r.ret_24h) and abs(r.ret_24h)<.05)
   out.append(row)
 return out
S=pd.DataFrame(snap(anchors,'PUMP')+snap(controls,'CONTROL'))
S.to_csv(OUT+'/snapshots.csv',index=False)
rows=[]
for h,g in S.groupby('lookback_h'):
 p=g[g.label=='PUMP'];c=g[g.label=='CONTROL'];r={'lookback_h':h,'pump_n':len(p),'control_n':len(c)}
 for f in features:
  r[f+'_pump_med']=p[f].median();r[f+'_ctrl_med']=c[f].median()
 r['quiet_flow_pump']=p.quiet_flow.mean();r['quiet_flow_ctrl']=c.quiet_flow.mean();r['quiet_flow_lift']=r['quiet_flow_pump']/max(r['quiet_flow_ctrl'],1e-9)
 r['strong_quiet_flow_pump']=p.strong_quiet_flow.mean();r['strong_quiet_flow_ctrl']=c.strong_quiet_flow.mean();r['strong_quiet_flow_lift']=r['strong_quiet_flow_pump']/max(r['strong_quiet_flow_ctrl'],1e-9)
 rows.append(r)
T=pd.DataFrame(rows).sort_values('lookback_h',ascending=False);T.to_csv(OUT+'/timeline_comparison.csv',index=False)
# Earliest quiet-flow occurrence within the 30d pre-anchor path, sampled hourly from source rows.
early=[]
for label,events in [('PUMP',anchors),('CONTROL',controls)]:
 for m,a in events:
  g=d[(d.market==m)&(d.time>=a-pd.Timedelta(hours=720))&(d.time<a)].copy()
  q=g[(g.turn_ratio>=2)&(g.ret_24h.abs()<.05)]
  q4=g[(g.turn_ratio>=4)&(g.ret_24h.abs()<.05)]
  early.append({'label':label,'market':m,'anchor':a,'q2_any':len(q)>0,'q4_any':len(q4)>0,'q2_first_lead_h':(a-q.time.iloc[0]).total_seconds()/3600 if len(q) else np.nan,'q4_first_lead_h':(a-q4.time.iloc[0]).total_seconds()/3600 if len(q4) else np.nan,'q2_hours':len(q),'q4_hours':len(q4)})
E=pd.DataFrame(early);E.to_csv(OUT+'/quiet_flow_30d_events.csv',index=False)
print('\nTIMELINE PUMP vs CONTROL\n',T.to_string(index=False))
print('\n30D QUIET FLOW SUMMARY\n',E.groupby('label')[['q2_any','q4_any','q2_first_lead_h','q4_first_lead_h','q2_hours','q4_hours']].agg(['mean','median']).to_string())
