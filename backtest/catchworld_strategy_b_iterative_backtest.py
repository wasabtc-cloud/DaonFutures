import glob, os, itertools
import numpy as np, pandas as pd
IN='strategy_b_input'; OUT='results/strategy_b_iterative'; os.makedirs(OUT,exist_ok=True)
parts=[]
for f in glob.glob(IN+'/**/*.csv',recursive=True):
 try:
  d=pd.read_csv(f)
  if len(d): parts.append(d)
 except: pass
df=pd.concat(parts,ignore_index=True); df.time=pd.to_datetime(df.time,utc=True,errors='coerce'); df=df.dropna(subset=['time']).drop_duplicates(['market','time']).sort_values(['time','market'])
# normalize fwd MFE decimal -> percent only for evaluation, never signal
for c in ['fwd_mfe_6h','fwd_mfe_12h','fwd_mfe_24h','fwd_mfe_48h','fwd_mfe_72h']:
 df[c]=100*pd.to_numeric(df[c],errors='coerce')
cut=df.time.quantile(.70); dev=df[df.time<=cut].copy(); hold=df[df.time>cut].copy(); print('ROWS',len(df),'CUT',cut,'DEV',len(dev),'HOLD',len(hold))
cols=['turn_ratio','turn_accel_6_24','range24','range72','ret_6h','ret_24h','ret_72h','ret_168h','drawdown_30d']
for c in cols: dev[c]=pd.to_numeric(dev[c],errors='coerce'); hold[c]=pd.to_numeric(hold[c],errors='coerce')
# Quantiles are learned from DEV only.
Q={c:{q:dev[c].quantile(q) for q in [.35,.4,.5,.6,.65,.7,.75,.8,.85,.9]} for c in cols}
# Four causal archetypes, multiple variants. Avoid already-exploded 24h returns.
def masks(x):
 r={}
 for tq in [.65,.75,.8,.85,.9]:
  for rq in [.5,.6,.7,.8]:
   # latent/base: drawdown + turnover waking while price not extended
   r[f'BASE_t{tq}_r{rq}']=(x.turn_ratio>=Q['turn_ratio'][tq])&(x.drawdown_30d<=Q['drawdown_30d'][.5])&(x.range24>=Q['range24'][rq])&(x.ret_24h<=Q['ret_24h'][.8])
   # flow lead: turnover ratio + acceleration + modest 24h return
   r[f'FLOW_t{tq}_r{rq}']=(x.turn_ratio>=Q['turn_ratio'][tq])&(x.turn_accel_6_24>=Q['turn_accel_6_24'][.65])&(x.range24>=Q['range24'][rq])&(x.ret_24h>=Q['ret_24h'][.4])&(x.ret_24h<=Q['ret_24h'][.8])
   # early breakout: positive structure but capped extension
   r[f'EARLY_t{tq}_r{rq}']=(x.turn_ratio>=Q['turn_ratio'][tq])&(x.ret_6h>=Q['ret_6h'][.5])&(x.ret_24h>=Q['ret_24h'][.5])&(x.ret_24h<=Q['ret_24h'][.85])&(x.range72>=Q['range72'][rq])
   # reaccumulation: prior 7d strength, 24h cooled, flow renewed
   r[f'REACC_t{tq}_r{rq}']=(x.turn_ratio>=Q['turn_ratio'][tq])&(x.ret_168h>=Q['ret_168h'][.65])&(x.ret_24h<=Q['ret_24h'][.6])&(x.turn_accel_6_24>=Q['turn_accel_6_24'][.65])&(x.range72>=Q['range72'][rq])
 return r

def dedup(x,m,cool=24):
 z=x.loc[m,['market','time','fwd_mfe_24h','fwd_mfe_72h']].sort_values('time'); keep=[]; last={}
 for i,a in z.iterrows():
  if a.market not in last or (a.time-last[a.market]).total_seconds()>=cool*3600: keep.append(i); last[a.market]=a.time
 return x.loc[keep]
def stats(x,m,name):
 z=dedup(x,m); n=len(z)
 if not n:return None
 y=z.fwd_mfe_24h
 return dict(name=name,signals=n,p20=(y>=20).mean(),p30=(y>=30).mean(),p50=(y>=50).mean(),med24=y.median(),mean24=y.mean(),p20_72=(z.fwd_mfe_72h>=20).mean(),p50_72=(z.fwd_mfe_72h>=50).mean())
rows=[]
for name,m in masks(dev).items():
 s=stats(dev,m,name)
 if s: rows.append(s)
r=pd.DataFrame(rows); base=(dev.fwd_mfe_24h>=20).mean(); r['lift20']=r.p20/base
# Development selection balances precision, lift, enough opportunities and tail capture.
r['objective']=r.p20*2+r.p50*3+np.minimum(r.signals,300)/300*.03
r=r[(r.signals>=40)].sort_values('objective',ascending=False); r.to_csv(OUT+'/dev_variants.csv',index=False)
print('DEV TOP');print(r.head(20).to_string(index=False))
# Freeze top diverse variants then one-shot holdout.
chosen=[]
for typ in ['BASE','FLOW','EARLY','REACC']:
 q=r[r.name.str.startswith(typ)].head(2); chosen+=q.name.tolist()
hm=masks(hold); out=[]
for n in chosen:
 s=stats(hold,hm[n],n)
 if s: out.append(s)
o=pd.DataFrame(out); hbase=(hold.fwd_mfe_24h>=20).mean(); o['lift20']=o.p20/hbase; o.to_csv(OUT+'/holdout_frozen.csv',index=False)
print('HOLDOUT FROZEN');print(o.to_string(index=False))
# Candidate app rules: report only, no tuning on holdout.
with open(OUT+'/selected.txt','w') as f:
 f.write('DEV_ONLY_SELECTION\n'+ '\n'.join(chosen)+'\nCUT='+str(cut)+'\n')
